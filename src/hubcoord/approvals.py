"""Local self_asserted approvals bound to frozen subject digests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hubcoord.models.common import ValidationError
from hubcoord.models.records import validate_approval
from hubcoord.runstore import FileRunStore

#: Directory under a run dir that holds one approval file per kind.
APPROVALS_DIR = "approvals"


class GateError(RuntimeError):
    """Review gate cannot advance; carries a stable machine code."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def approval_path(hub_root: Path, execution_id: str, kind: str) -> Path:
    return hub_root / "runs" / execution_id / APPROVALS_DIR / f"{kind}.json"


def _subject_for_kind(kind: str, snapshot: dict, result: dict | None) -> str:
    """Approve always recomputes the binding digest from frozen content."""
    if kind == "plan":
        return snapshot["planning_digest"]
    if kind == "implementation":
        if not result:
            raise ValidationError(
                "result-required",
                "implementation approval requires a validated result.json",
            )
        return result["result_digest"]
    if kind == "archive":
        return snapshot.get("completion_digest") or snapshot["context_digest"]
    raise ValidationError("approval-kind", f"unsupported approval kind {kind!r}")


def scope_for_kind(kind: str, snapshot: dict) -> str:
    change_id = snapshot["change_id"]
    if kind == "plan":
        return f"planning_snapshot:{change_id}"
    if kind == "implementation":
        return f"implementation:{change_id}"
    return f"archive:{change_id}"


def record_approval(
    store: FileRunStore,
    execution_id: str,
    kind: str,
    snapshot: dict,
    actor: str,
    decision: str = "approve",
    result: dict | None = None,
) -> dict:
    """Record the operator's own confirmation; v1 is always self_asserted."""
    subject_digest = _subject_for_kind(kind, snapshot, result)
    record = {
        "api_version": "hub/v1",
        "execution_id": execution_id,
        "kind": kind,
        "decision": decision,
        "subject_digest": subject_digest,
        "scope": scope_for_kind(kind, snapshot),
        "actor": actor,
        "auth_level": "self_asserted",
        "timestamp": _now(),
    }
    validate_approval(record)
    target = approval_path(store.hub_root, execution_id, kind)
    target.parent.mkdir(parents=True, exist_ok=True)
    from hubcoord.runstore import atomic_write_json

    atomic_write_json(target, record)

    state = store.read_state(execution_id)
    revision = state["revision"]
    approvals = dict(state.get("approvals") or {})

    def mutate(next_state: dict, *, rows=approvals) -> None:
        rows[kind] = {
            "decision": decision,
            "subject_digest": subject_digest,
            "actor": actor,
            "scope": record["scope"],
            "timestamp": record["timestamp"],
        }
        next_state["approvals"] = rows

    store.update_state(execution_id, mutate, expected_revision=revision)
    return record


def load_approval(store: FileRunStore, execution_id: str, kind: str) -> dict | None:
    path = approval_path(store.hub_root, execution_id, kind)
    if not path.is_file():
        return None
    from hubcoord.runstore import _read_json_or_none

    data = _read_json_or_none(path)
    if data is None:
        raise GateError("approval-corrupt", f"{path} is missing or not parseable")
    return data


def require_gate(
    store: FileRunStore,
    execution_id: str,
    kind: str,
    expected_subject_digest: str | None = None,
) -> dict:
    """Gate advance check: a recorded receipt must match kind + frozen subject.

    Refuses to advance without a receipt (injected verdict refusal).
    """
    from hubcoord.runstore import _read_json_or_none

    snapshot = _read_json_or_none(store.run_dir(execution_id) / "snapshot.json")
    if snapshot is None:
        raise GateError("snapshot-missing", "no frozen snapshot for this execution")
    approval = load_approval(store, execution_id, kind)
    if approval is None:
        raise GateError(
            "no-approval",
            f"no {kind} approval receipt; the gate refuses to advance",
        )
    validate_approval(approval)
    if approval["decision"] != "approve":
        raise GateError(
            "approval-rejected",
            f"{kind} approval recorded decision {approval['decision']!r}",
        )
    recomputed = _subject_for_kind(kind, snapshot, _load_result(store, execution_id, kind))
    matching = (
        expected_subject_digest is None or approval["subject_digest"] == expected_subject_digest
    )
    if not matching or approval["subject_digest"] != recomputed:
        raise GateError(
            "approval-mismatch",
            f"{kind} approval subject_digest does not bind the frozen {kind} content",
        )
    return approval


def verify_frozen_approval(
    store: FileRunStore,
    execution_id: str,
    kind: str,
    recomputed_subject_digest: str,
    result: dict | None = None,
) -> dict:
    """Changed approved input: recompute the digest from live content; must match."""
    approval = load_approval(store, execution_id, kind)
    if approval is None:
        raise GateError("no-approval", f"no {kind} approval receipt gate check")
    validate_approval(approval)
    if approval["subject_digest"] != recomputed_subject_digest:
        raise GateError(
            "approval-stale",
            f"stored approval ({kind}) binds different content than the current input",
        )
    return approval


def _load_result(store: FileRunStore, execution_id: str, kind: str) -> dict | None:
    from hubcoord.runstore import _read_json_or_none

    if kind != "implementation":
        return None
    return _read_json_or_none(store.run_dir(execution_id) / "result.json")


__all__ = [
    "APPROVALS_DIR",
    "GateError",
    "load_approval",
    "record_approval",
    "require_gate",
    "scope_for_kind",
    "verify_frozen_approval",
]
