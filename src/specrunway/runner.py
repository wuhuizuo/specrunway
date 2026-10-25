"""Run controller: freeze an execution, drive the native workflow, finalize."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

from specrunway.approvals import GateError, require_gate
from specrunway.bridge.workflow import build_workflow_yaml, workflow_id_for
from specrunway.freezer import freeze_execution, new_execution_id
from specrunway.models import load_local_config, validate_manifest
from specrunway.models.common import ValidationError
from specrunway.runstore import FileRunStore, _read_json_or_none, atomic_write_json
from specrunway.toolresolvers import resolve_tool_bin


class RunError(ValidationError):
    """Run-start refusal with a stable error code."""


def _tool_versions(control_root: Path, agent_profile: str) -> dict:
    openspec = "unknown"
    spec_kit = "unknown"
    lock_file = Path(control_root) / "toolchain.lock.json"
    if lock_file.is_file():
        lock = _read_json_or_none(lock_file) or {}
        openspec = str((lock.get("openspec") or {}).get("version") or openspec)
        spec_kit = str((lock.get("specify") or {}).get("version") or spec_kit)
    return {"openspec": openspec, "spec_kit": spec_kit, "agent_profile": agent_profile}


def _snapshot(store: FileRunStore, execution_id: str) -> dict:
    data = _read_json_or_none(store.run_dir(execution_id) / "snapshot.json")
    if data is None:
        raise RunError(
            "snapshot-missing", f"no frozen snapshot.json for execution {execution_id}"
        )
    return data


def _set_phase(store: FileRunStore, execution_id: str, phase: str) -> None:
    current = store.read_state(execution_id)

    def mutate(next_state: dict) -> None:
        next_state["phase"] = phase

    store.update_state(execution_id, mutate, current["revision"])


def prepare_execution(control_root: Path, change_id: str) -> dict:
    """Freeze plan bytes, base commits, test profiles, and optional integration."""
    from specrunway.integration import resolve_integration_profile

    control_root = Path(control_root)
    plan_file = control_root / ".specrunway" / "plans" / change_id / "manifest.yaml"
    if not plan_file.is_file():
        raise RunError(
            "manifest-missing",
            f"no accepted plan manifest for {change_id}; run `specrunway plan` first",
        )
    manifest = validate_manifest(yaml.safe_load(plan_file.read_text(encoding="utf-8")))
    config = load_local_config(control_root)
    store_path = Path(config["store"]["path"])
    change_path = store_path / "openspec" / "changes" / change_id
    if not change_path.is_dir():
        raise RunError("change-missing", f"Store has no change directory at {change_path}")
    repos_cfg = {}
    for repo_id in manifest["repo_order"]:
        entry = (config["repos"] or {}).get(repo_id) or {}
        if not entry.get("path"):
            raise RunError(
                "repo-unconfigured",
                f"repo {repo_id!r} from the manifest has no local.yaml entry",
            )
        repos_cfg[repo_id] = {
            "path": entry["path"],
            "remote_identity": entry.get("remote_identity", ""),
        }
    from specrunway.testprofiles import freeze_test_profiles

    integration = (
        resolve_integration_profile(config, manifest)
        if manifest.get("integration_profile")
        else None
    )
    frozen_profiles = freeze_test_profiles(manifest, config.get("test_profiles"))
    execution_id = new_execution_id()
    store = FileRunStore(control_root / ".specrunway")
    with store.lock(timeout=5.0):
        store.ensure_run(execution_id, change_id)
        store.claim_activity(execution_id)
        snapshot = freeze_execution(
            execution_id,
            change_path,
            manifest,
            repos_cfg,
            _tool_versions(control_root, config["agent_profile"]),
            integration,
            frozen_profiles,
        )
        atomic_write_json(store.run_dir(execution_id) / "snapshot.json", snapshot)
        _set_phase(store, execution_id, "awaiting_plan_review")
    return {"execution_id": execution_id, "snapshot": snapshot, "store": store}


def _require_specify_init(control_root: Path) -> None:
    if not (Path(control_root) / ".specify").is_dir():
        raise RunError(
            "specify-not-initialized",
            "initialize the control checkout first: `specify init --here --force "
            "--non-interactive --ignore-agent-tools` and install the specrunway step",
        )


def _write_workflow(control_root: Path, execution_id: str, snapshot: dict) -> Path:
    workflows = Path(control_root) / ".specify" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    target = workflows / f"{workflow_id_for(execution_id)}.yaml"
    target.write_text(
        build_workflow_yaml(
            execution_id,
            snapshot["change_id"],
            has_integration=bool(snapshot.get("integration")),
        ),
        encoding="utf-8",
    )
    return target


def _specify_workflow(
    args: list[str],
    control_root: Path,
    allowed_statuses: set | None = None,
) -> dict:
    specify_bin = resolve_tool_bin(control_root, None, "specify")
    process = subprocess.run(
        [specify_bin, *args, "--json"],
        cwd=str(control_root),
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    combined = (process.stdout or "") + (process.stderr or "")
    payload = None
    for candidate in (
        combined.strip(),
        combined[combined.find("{") :] if "{" in combined else "",
    ):
        if not candidate:
            continue
        try:
            payload, _end = json.JSONDecoder().raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        break
    if payload is None:
        raise RunError(
            "workflow-output",
            f"cannot parse `specify workflow {args[0]}` output: {combined[-500:]}",
        )
    allowed = allowed_statuses or {"completed", "paused"}
    if process.returncode != 0 or payload.get("status") not in allowed:
        detail = combined.strip().splitlines()
        tail = " | ".join(line.strip() for line in detail[-4:] if line.strip())
        raise RunError(
            "workflow-failed",
            f"native workflow {args[0]} did not succeed "
            f"(exit {process.returncode}, status {payload.get('status')!r}): {tail[-600:]}",
        )
    return payload


def _remember_native_run(store: FileRunStore, execution_id: str, payload: dict) -> None:
    current = store.read_state(execution_id)

    def mutate(next_state: dict) -> None:
        next_state["native_run_id"] = payload.get("run_id") or next_state.get("native_run_id")

    store.update_state(execution_id, mutate, current["revision"])


_GATE_KINDS = {"plan-gate": "plan", "implementation-gate": "implementation"}


def _record_pause(store: FileRunStore, execution_id: str, payload: dict) -> None:
    _remember_native_run(store, execution_id, payload)
    step_id = payload.get("current_step_id")
    kind = _GATE_KINDS.get(str(step_id))
    current = store.read_state(execution_id)
    if payload.get("status") == "completed":
        phase = "ready_for_review"
    elif kind == "plan":
        phase = "awaiting_plan_review"
    else:
        phase = "awaiting_implementation_review"

    def mutate(next_state: dict) -> None:
        next_state["phase"] = phase
        next_state["pending_gate"] = kind

    store.update_state(execution_id, mutate, current["revision"])


def start_execution(control_root: Path, execution_id: str) -> dict:
    """Start the native workflow; native gates pause for approval receipts."""
    control_root = Path(control_root)
    _require_specify_init(control_root)
    store = FileRunStore(control_root / ".specrunway")
    snapshot = _snapshot(store, execution_id)
    with store.lock(timeout=5.0):
        store.claim_activity(execution_id)
        _set_phase(store, execution_id, "implementing")
    workflow_file = _write_workflow(control_root, execution_id, snapshot)
    payload = _specify_workflow(
        [
            "workflow",
            "run",
            str(workflow_file),
            "--input",
            f"execution={execution_id}",
            "--input",
            f"control_root={control_root}",
        ],
        control_root,
    )
    with store.lock(timeout=5.0):
        _record_pause(store, execution_id, payload)
    return payload


def continue_execution(control_root: Path, execution_id: str) -> dict:
    """Resume a paused run once the matching approval receipt exists."""
    control_root = Path(control_root)
    _require_specify_init(control_root)
    store = FileRunStore(control_root / ".specrunway")
    _snapshot(store, execution_id)
    state = store.read_state(execution_id)
    kind = state.get("pending_gate") or "implementation"
    try:
        require_gate(store, execution_id, kind)
    except GateError as exc:
        raise RunError(exc.code, exc.message) from exc
    native_run_id = state.get("native_run_id")
    if not native_run_id:
        raise RunError(
            "run-not-started",
            f"execution {execution_id} has no native run to resume",
        )
    verdict_input = "plan_verdict" if kind == "plan" else "implementation_verdict"
    with store.lock(timeout=5.0):
        store.claim_activity(execution_id)
        _set_phase(
            store,
            execution_id,
            "implementing" if kind == "plan" else "awaiting_implementation_review",
        )
    payload = _specify_workflow(
        [
            "workflow",
            "resume",
            str(native_run_id),
            "--input",
            f"{verdict_input}=approve",
        ],
        control_root,
    )
    with store.lock(timeout=5.0):
        _record_pause(store, execution_id, payload)
    return payload


__all__ = [
    "RunError",
    "continue_execution",
    "prepare_execution",
    "start_execution",
]
