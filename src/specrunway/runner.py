"""Run controller: freeze an execution, drive the native workflow, finalize."""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path

import yaml

from specrunway.approvals import GateError, require_gate
from specrunway.bridge.workflow import build_workflow_yaml, workflow_id_for
from specrunway.freezer import freeze_execution, new_execution_id
from specrunway.models import load_local_config, validate_manifest
from specrunway.models.common import ValidationError
from specrunway.runstore import (
    FileRunStore,
    RevisionConflictError,
    RunStoreError,
    _now,
    _read_json_or_none,
    atomic_write_json,
)
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


def _run_with_progress(
    argv: list,
    control_root: Path,
    progress_stream,
    progress_poll: float,
) -> tuple[int, str, str]:
    """Run a native workflow while forwarding its step log to stderr.

    stdout/stderr go to temporary files (not pipes) so a slow operator stream
    can never deadlock the native process, and the JSON body stays intact.
    """
    from specrunway.observability import NativeProgressWatcher

    runs_root = Path(control_root) / ".specify" / "workflows" / "runs"
    known = set(runs_root.glob("*/log.jsonl")) if runs_root.is_dir() else set()
    watcher = NativeProgressWatcher(Path(control_root), progress_stream, known=known)
    with tempfile.TemporaryFile() as out_file, tempfile.TemporaryFile() as err_file:
        process = subprocess.Popen(
            argv,
            cwd=str(control_root),
            stdout=out_file,
            stderr=err_file,
            stdin=subprocess.DEVNULL,
            shell=False,
        )
        while process.poll() is None:
            watcher.poll()
            time.sleep(progress_poll)
        watcher.poll()
        out_file.seek(0)
        err_file.seek(0)
        stdout = out_file.read().decode("utf-8", errors="replace")
        stderr = err_file.read().decode("utf-8", errors="replace")
        return int(process.returncode or 0), stdout, stderr


def _specify_workflow(
    args: list[str],
    control_root: Path,
    allowed_statuses: set | None = None,
    progress_stream=None,
    progress_poll: float = 0.2,
) -> dict:
    specify_bin = resolve_tool_bin(control_root, None, "specify")
    argv = [specify_bin, *args, "--json"]
    if progress_stream is None:
        process = subprocess.run(
            argv,
            cwd=str(control_root),
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        returncode = process.returncode
        stdout = process.stdout or ""
        stderr = process.stderr or ""
    else:
        returncode, stdout, stderr = _run_with_progress(
            argv, Path(control_root), progress_stream, progress_poll
        )
    combined = stdout + stderr
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
    if returncode != 0 or payload.get("status") not in allowed:
        detail = combined.strip().splitlines()
        tail = " | ".join(line.strip() for line in detail[-4:] if line.strip())
        raise RunError(
            "workflow-failed",
            f"native workflow {args[0]} did not succeed "
            f"(exit {returncode}, status {payload.get('status')!r}): {tail[-600:]}",
        )
    return payload


def _native_state_paths(control_root: Path) -> list:
    runs_root = Path(control_root) / ".specify" / "workflows" / "runs"
    if not runs_root.is_dir():
        return []
    rows = []
    for state_path in runs_root.glob("*/state.json"):
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            rows.append((state_path, payload))
    return rows


def _native_run_state(
    control_root: Path, execution_id: str, native_run_id: str | None
) -> dict | None:
    """Read (never write) the native run state that recorded a failed step."""
    wanted = workflow_id_for(execution_id)
    candidates = []
    for state_path, payload in _native_state_paths(control_root):
        if payload.get("workflow_id") != wanted:
            continue
        if native_run_id and payload.get("run_id") == native_run_id:
            return payload
        candidates.append((str(payload.get("updated_at") or ""), state_path.stat().st_mtime, payload))
    if not candidates:
        return None
    return max(candidates, key=lambda row: (row[0], row[1]))[2]


def _find_log_path(payload) -> str | None:
    """First ``log_path`` or ``*.log`` evidence string inside a step output."""
    if isinstance(payload, dict):
        candidate = payload.get("log_path")
        if isinstance(candidate, str) and candidate:
            return candidate
        evidence = payload.get("evidence")
        if isinstance(evidence, list):
            for item in evidence:
                if isinstance(item, str) and item.endswith(".log"):
                    return item
        for value in payload.values():
            found = _find_log_path(value)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_log_path(item)
            if found:
                return found
    return None


def _failed_step(state: dict) -> tuple | None:
    results = state.get("step_results") or {}
    failed = [
        (step_id, row)
        for step_id, row in results.items()
        if isinstance(row, dict) and str(row.get("status")) == "failed"
    ]
    if not failed:
        return None
    current = state.get("current_step_id")
    for step_id, row in failed:
        if step_id == current:
            return step_id, row
    return failed[-1]


def _log_path_fallback(
    store: FileRunStore, execution_id: str, state: dict, step_id: str | None
) -> str | None:
    """Derive the repo attempt log for a fan-out failure without step evidence."""
    if not step_id or not step_id.startswith("implement:repo:"):
        return None
    snapshot = _read_json_or_none(store.run_dir(execution_id) / "snapshot.json") or {}
    repo_order = (snapshot.get("manifest") or {}).get("repo_order") or []
    try:
        repo_id = repo_order[int(step_id.rsplit(":", 1)[1])]
    except (ValueError, IndexError):
        return None
    attempt = int(((state.get("budgets") or {}).get(repo_id) or {}).get("attempts_used") or 0)
    if attempt <= 0:
        return None
    log_dir = store.run_dir(execution_id) / "logs" / repo_id / str(attempt)
    for name in ("agent.log", "tests.log"):
        if (log_dir / name).is_file():
            return str(log_dir / name)
    return None


def record_native_failure(
    store: FileRunStore,
    execution_id: str,
    control_root: Path,
    exc: Exception,
    native_run_id: str | None = None,
) -> dict | None:
    """Persist the native step that failed so ``status`` can explain the stop."""
    try:
        state = store.read_state(execution_id)
    except RunStoreError:
        return None
    native = _native_run_state(
        Path(control_root), execution_id, native_run_id or state.get("native_run_id")
    )
    failure: dict = {}
    step = _failed_step(native) if native else None
    if step is not None:
        step_id, row = step
        output = row.get("output") if isinstance(row.get("output"), dict) else {}
        error = output.get("error") if isinstance(output.get("error"), dict) else {}
        failure = {
            "step_id": step_id,
            "code": str(error.get("code") or "step-failed"),
            "message": str(row.get("error") or error.get("message") or "step failed"),
            "log_path": _find_log_path(output),
            "native_run_id": (native or {}).get("run_id"),
        }
    if not failure:
        failure = {
            "step_id": None,
            "code": str(getattr(exc, "code", None) or "workflow-failed"),
            "message": str(exc),
            "log_path": None,
            "native_run_id": (native or {}).get("run_id") or native_run_id,
        }
    if not failure.get("log_path"):
        failure["log_path"] = _log_path_fallback(
            store, execution_id, state, failure.get("step_id")
        )
    failure["recorded_at"] = _now()
    for _attempt in range(3):
        current = store.read_state(execution_id)

        def mutate(next_state: dict, *, row=failure) -> None:
            next_state["last_failure"] = row

        try:
            store.update_state(execution_id, mutate, current["revision"])
            break
        except RevisionConflictError:
            continue
    return failure


def run_workflow(
    store: FileRunStore,
    execution_id: str,
    control_root: Path,
    args: list,
    allowed_statuses: set | None = None,
    progress_stream=None,
) -> dict:
    """Run/pause/resume the native workflow and record any failed step first."""
    try:
        return _specify_workflow(
            args,
            Path(control_root),
            allowed_statuses=allowed_statuses,
            progress_stream=progress_stream,
        )
    except RunError as exc:
        record_native_failure(store, execution_id, Path(control_root), exc)
        raise


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
        # A run that paused or completed again is no longer a failed attempt.
        next_state["last_failure"] = None

    store.update_state(execution_id, mutate, current["revision"])


def start_execution(
    control_root: Path, execution_id: str, progress_stream=None
) -> dict:
    """Start the native workflow; native gates pause for approval receipts."""
    control_root = Path(control_root)
    _require_specify_init(control_root)
    store = FileRunStore(control_root / ".specrunway")
    snapshot = _snapshot(store, execution_id)
    with store.lock(timeout=5.0):
        store.claim_activity(execution_id)
        _set_phase(store, execution_id, "implementing")
    workflow_file = _write_workflow(control_root, execution_id, snapshot)
    payload = run_workflow(
        store,
        execution_id,
        control_root,
        [
            "workflow",
            "run",
            str(workflow_file),
            "--input",
            f"execution={execution_id}",
            "--input",
            f"control_root={control_root}",
        ],
        progress_stream=progress_stream,
    )
    with store.lock(timeout=5.0):
        _record_pause(store, execution_id, payload)
    return payload


def continue_execution(
    control_root: Path, execution_id: str, progress_stream=None
) -> dict:
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
    payload = run_workflow(
        store,
        execution_id,
        control_root,
        [
            "workflow",
            "resume",
            str(native_run_id),
            "--input",
            f"{verdict_input}=approve",
        ],
        progress_stream=progress_stream,
    )
    with store.lock(timeout=5.0):
        _record_pause(store, execution_id, payload)
    return payload


__all__ = [
    "RunError",
    "continue_execution",
    "prepare_execution",
    "record_native_failure",
    "run_workflow",
    "start_execution",
]
