"""Normal resume, orphan-running recovery, and execution status (L13)."""

from __future__ import annotations

import os
from pathlib import Path

from hubcoord.approvals import GateError, require_gate
from hubcoord.freezer import compute_planning_digest
from hubcoord.models import load_local_config
from hubcoord.models.common import ValidationError
from hubcoord.runstore import FileRunStore, _read_json_or_none
from hubcoord.worktrees import is_ancestor


class RecoveryError(ValidationError):
    """Recovery refusal with a stable error code."""


def _snapshot(store: FileRunStore, execution_id: str) -> dict:
    data = _read_json_or_none(store.run_dir(execution_id) / "snapshot.json")
    if data is None:
        raise RecoveryError("snapshot-missing", f"no frozen snapshot for {execution_id}")
    return data


def _process_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def native_status(control_root: Path, run_id: str) -> dict:
    from hubcoord.runner import _specify_workflow

    try:
        return _specify_workflow(
            ["workflow", "status", str(run_id)],
            Path(control_root),
            allowed_statuses={"completed", "paused", "failed", "running"},
        )
    except ValidationError as exc:
        raise RecoveryError(exc.code, str(exc)) from exc


def execution_status(control_root: Path, execution_id: str) -> dict:
    store = FileRunStore(Path(control_root) / ".hub")
    snapshot = _snapshot(store, execution_id)
    state = store.read_state(execution_id)
    owner = store.active_owner()
    return {
        "execution_id": execution_id,
        "phase": state.get("phase"),
        "pending_gate": state.get("pending_gate"),
        "native_run_id": state.get("native_run_id"),
        "native_runs": state.get("native_runs") or [],
        "revision": state.get("revision"),
        "active_owner": owner,
        "budgets": state.get("budgets") or {},
        "results": state.get("results") or {},
        "verification": state.get("verification") or {},
        "approvals": state.get("approvals") or {},
        "change_id": snapshot["change_id"],
        "repo_order": snapshot["manifest"]["repo_order"],
        "operations": [
            {
                "operation_key": op.get("operation_key"),
                "status": op.get("status"),
                "kind": op.get("kind") or op.get("action"),
            }
            for op in store.operations(execution_id)
        ],
    }


def reusable_result(
    store: FileRunStore, snapshot: dict, repo_id: str, repos_cfg: dict
) -> dict | None:
    """Reuse only when the stored result bytes, commit, and receipt still match."""
    from hubcoord.results import compute_result_digest

    state = store.read_state(snapshot["execution_id"])
    accepted = (state.get("results") or {}).get(repo_id) or {}
    if not accepted.get("passed"):
        return None
    ref = accepted.get("result_ref")
    if not ref:
        return None
    result_file = Path(ref)
    if not result_file.is_file():
        return None
    result = _read_json_or_none(result_file)
    if result is None:
        return None
    if compute_result_digest(result) != result.get("result_digest"):
        raise RecoveryError(
            "evidence-conflict",
            f"stored result for {repo_id} no longer matches its digest; refuse reuse",
        )
    if result.get("result_digest") != accepted.get("result_digest"):
        raise RecoveryError(
            "evidence-conflict",
            f"stored result digest for {repo_id} differs from run state; refuse reuse",
        )
    repo_path = Path((repos_cfg.get(repo_id) or {}).get("path") or "")
    base_oid = snapshot["repos"][repo_id]["base_oid"]
    head = result["head_commit"]
    if not repo_path.is_dir() or not head:
        return None
    if not is_ancestor(repo_path, base_oid, head):
        raise RecoveryError(
            "evidence-conflict",
            f"accepted commit {head[:12]} for {repo_id} is gone or not a descendant",
        )
    receipt = _read_json_or_none(
        store.run_dir(snapshot["execution_id"])
        / "tests_receipts"
        / repo_id
        / f"{result['attempt']}.json"
    )
    if receipt is None or receipt.get("status") != "passed":
        raise RecoveryError(
            "evidence-conflict",
            f"trusted test receipt for {repo_id} attempt {result['attempt']} is missing or failed",
        )
    worktree = store.run_dir(snapshot["execution_id"]) / "worktrees" / repo_id
    if not worktree.is_dir():
        return None
    return {
        "repo_id": repo_id,
        "task_ids": [row["task_id"] for row in result.get("tasks") or []],
        "passed": True,
        "attempt": result["attempt"],
        "result_ref": str(result_file),
        "head_commit": head,
        "reused": True,
    }


def _verify_live_plan(control_root: Path, snapshot: dict) -> None:
    config = load_local_config(Path(control_root))
    change_path = Path(config["store"]["path"]) / "openspec" / "changes" / snapshot["change_id"]
    if not change_path.is_dir():
        raise RecoveryError(
            "change-missing",
            f"approved plan input {change_path} disappeared; approval is stale",
        )
    live = compute_planning_digest(change_path, snapshot["manifest"])
    if live != snapshot["planning_digest"]:
        raise RecoveryError(
            "approval-stale",
            "planning content changed since freeze; the recorded approval no longer binds",
        )


def _preserve_native_run(
    store: FileRunStore, execution_id: str, payload: dict, status: str
) -> None:

    state = store.read_state(execution_id)

    def mutate(next_state: dict) -> None:
        rows = list(next_state.get("native_runs") or [])
        rows.append(
            {
                "run_id": payload.get("run_id") or next_state.get("native_run_id"),
                "status": status,
                "current_step_id": payload.get("current_step_id"),
            }
        )
        next_state["native_runs"] = rows

    store.update_state(execution_id, mutate, state["revision"])


def _resume_native(control_root: Path, store: FileRunStore, execution_id: str) -> dict:
    from hubcoord.runner import (
        _record_pause,
        _specify_workflow,
        continue_execution,
    )

    state = store.read_state(execution_id)
    native_run_id = state.get("native_run_id")
    if not native_run_id:
        raise RecoveryError("run-not-started", "execution has no native run to resume")
    status = native_status(control_root, native_run_id)
    native = str(status.get("status"))
    if native == "running":
        raise RecoveryError(
            "orphan-running",
            "native run still reports running; use `hub recover` to confirm termination",
        )
    if native == "completed":
        return status
    if state.get("pending_gate"):
        return continue_execution(control_root, execution_id)
    if state.get("phase") == "blocked":
        raise RecoveryError(
            "execution-blocked",
            f"execution blocked: {state.get('blocked_reason') or 'budget/no-progress stop'}",
        )
    payload = _specify_workflow(["workflow", "resume", str(native_run_id)], Path(control_root))
    with store.lock(timeout=5.0):
        _record_pause(store, execution_id, payload)
    return payload


def resume_execution(control_root: Path, execution_id: str) -> dict:
    """Resume a paused/failed run without rerunning verified completed work."""
    control_root = Path(control_root)
    from hubcoord.runner import _require_specify_init

    _require_specify_init(control_root)
    store = FileRunStore(control_root / ".hub")
    snapshot = _snapshot(store, execution_id)
    _verify_live_plan(control_root, snapshot)
    state = store.read_state(execution_id)
    pending = state.get("pending_gate")
    if pending:
        try:
            require_gate(store, execution_id, pending)
        except GateError as exc:
            raise RecoveryError(exc.code, exc.message) from exc
    with store.lock(timeout=5.0):
        store.claim_activity(execution_id)
    return _resume_native(control_root, store, execution_id)


def recover_execution(control_root: Path, execution_id: str) -> dict:
    """Reconcile an interrupted run; never edit the native run's private state."""
    control_root = Path(control_root)
    from hubcoord.archive import reconcile_pending_archive
    from hubcoord.runner import _require_specify_init, start_execution

    _require_specify_init(control_root)
    store = FileRunStore(control_root / ".hub")
    snapshot = _snapshot(store, execution_id)

    reconciled = reconcile_pending_archive(store, execution_id, snapshot)
    if reconciled.get("outcome") == "archived":
        return {"status": "completed", "reconciled_archive": True, "phase": "archived"}

    state = store.read_state(execution_id)
    native_run_id = state.get("native_run_id")
    if not native_run_id:
        raise RecoveryError("run-not-started", "execution has no native run")
    status = native_status(control_root, native_run_id)
    native = str(status.get("status"))
    if native == "running":
        owner = store.active_owner()
        pid = int((owner or {}).get("pid") or 0)
        if _process_alive(pid):
            raise RecoveryError(
                "orphan-alive",
                f"process {pid} still owns the checkout; confirm it stopped before recover",
            )

        with store.lock(timeout=5.0):
            _preserve_native_run(store, execution_id, status, "abandoned-running")

        def mutate(next_state: dict) -> None:
            next_state["phase"] = "interrupted"

        current = store.read_state(execution_id)
        store.update_state(execution_id, mutate, current["revision"])
        return start_execution(control_root, execution_id)
    if native == "paused" or native == "failed":
        _verify_live_plan(control_root, snapshot)
        return _resume_native(control_root, store, execution_id)
    return status


__all__ = [
    "RecoveryError",
    "execution_status",
    "native_status",
    "recover_execution",
    "resume_execution",
    "reusable_result",
]
