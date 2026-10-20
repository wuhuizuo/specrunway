"""FileRunStore: locking, atomic state, revisions, ownership, effect-first receipts."""

from __future__ import annotations

import json
import threading
from multiprocessing import Process

import pytest

from hubcoord.runstore import (
    ExecutionConflictError,
    FileRunStore,
    LockTimeoutError,
    RevisionConflictError,
    StateCorruptError,
    atomic_write_json,
)


def _lock_and_release(store_path: str) -> None:
    holder = FileRunStore(store_path)
    with holder.lock():
        pass


@pytest.fixture
def store(tmp_path) -> FileRunStore:
    return FileRunStore(tmp_path / "control" / ".hub")


EXEC = "0d1f8d02-01d4-4d5d-8df5-ecda48c01001"
OTHER = "0d1f8d02-01d4-4d5d-8df5-ecda48c01002"


# ------------------------------------------------------------------------------ atomic writes
def test_atomic_write_json_roundtrip(tmp_path):
    target = tmp_path / "data" / "state.json"
    atomic_write_json(target, {"phase": "implementing"})
    assert json.loads(target.read_text())["phase"] == "implementing"
    leftovers = [p for p in target.parent.glob("*.tmp")]
    assert leftovers == []


def test_atomic_write_existing_state_updated_in_one_step(tmp_path):
    target = tmp_path / "state.json"
    atomic_write_json(target, {"rev": 1})
    atomic_write_json(target, {"rev": 2})
    assert json.loads(target.read_text()) == {"rev": 2}
    # interrupted-write probe: payload larger, replaced atomically under load readers
    payload = {"rev": 3, "blob": "x" * 200_000}
    atomic_write_json(target, payload)
    assert json.loads(target.read_text()) == payload


def test_interrupted_state_write_detected(tmp_path, store):
    store.ensure_run(EXEC, "change-x")
    state_path = store.run_dir(EXEC) / "state.json"
    state_path.write_text('{"phase": "blocked", ')  # simulated torn write
    with pytest.raises(StateCorruptError):
        store.read_state(EXEC)


def test_state_renamed_execution_id_rejected(store):
    store.ensure_run(EXEC, "change-x")
    state_path = store.run_dir(EXEC) / "state.json"
    payload = json.loads(state_path.read_text())
    payload["execution_id"] = OTHER
    state_path.write_text(json.dumps(payload))
    with pytest.raises(StateCorruptError) as excinfo:
        store.read_state(EXEC)
    assert "names execution_id" in str(excinfo.value)


# ------------------------------------------------------------------------------ revisions
def test_revision_cas_happy_path(store):
    store.ensure_run(EXEC, "change-x")
    state = store.read_state(EXEC)
    assert state["revision"] == 1

    def mutate(next_state):
        next_state["phase"] = "implementing"

    updated = store.update_state(EXEC, mutate, expected_revision=1)
    assert updated["phase"] == "implementing"
    assert updated["revision"] == 2


def test_revision_conflict_detected(store):
    store.ensure_run(EXEC, "change-x")

    def first(next_state):
        next_state["phase"] = "implementing"

    def second(next_state):
        next_state["phase"] = "verifying"

    store.update_state(EXEC, first, expected_revision=1)
    with pytest.raises(RevisionConflictError):
        store.update_state(EXEC, second, expected_revision=1)


def test_immutable_fields_survive_update(store):
    store.ensure_run(EXEC, "change-x")
    created = store.read_state(EXEC)["created_at"]

    def mutate(next_state):
        next_state["created_at"] = "2020-01-01T00:00:00Z"
        next_state["execution_id"] = OTHER

    updated = store.update_state(EXEC, mutate, expected_revision=1)
    assert updated["created_at"] == created
    assert updated["execution_id"] == EXEC


# ------------------------------------------------------------------------------ ownership
def test_active_owner_claim_conflict(store):
    store.ensure_run(EXEC, "change-x")
    store.claim_activity(EXEC)
    with pytest.raises(ExecutionConflictError):
        store.claim_activity(OTHER)
    owner = store.active_owner()
    assert owner["execution_id"] == EXEC
    store.release_activity(EXEC)
    assert store.active_owner() is None


def test_claim_same_execution_is_idempotent(store):
    store.ensure_run(EXEC, "change-x")
    first = store.claim_activity(EXEC)
    second = store.claim_activity(EXEC)
    assert first["execution_id"] == second["execution_id"]


def test_release_refuses_other_execution(store):
    store.claim_activity(EXEC)
    with pytest.raises(ExecutionConflictError):
        store.release_activity(OTHER)


# ------------------------------------------------------------------------------ lock
def test_lock_excludes_other_writer(store):
    entered = threading.Event()
    leave = threading.Event()
    holder_handoff: list = []

    def hold():
        with store.lock():
            holder_handoff.append("acquired")
            entered.set()
            leave.wait(5)

    thread = threading.Thread(target=hold)
    thread.start()
    entered.wait(2)
    with pytest.raises(LockTimeoutError), store.lock(timeout=0.15):
        pass  # non-existing exclusive take
    with pytest.raises(LockTimeoutError) as once:
        store.lock(timeout=0.05, blocking=False).__enter__()
    assert "locked by another hub process" in str(once.value)
    leave.set()
    thread.join()
    assert holder_handoff == ["acquired"]


def test_lock_reusable_after_holder_exits(tmp_path):
    store_path = tmp_path / "control" / ".hub"
    proc = Process(target=_lock_and_release, args=(str(store_path),))
    proc.start()
    proc.join()
    assert proc.exitcode == 0
    third = FileRunStore(store_path)
    with third.lock():
        pass


# ------------------------------------------------------------------------------ operations
def test_intent_before_receipt(store):
    store.ensure_run(EXEC, "change-x")
    intent = store.write_intent(
        EXEC,
        {
            "api_version": "hub/v1",
            "operation_key": f"{EXEC}:checkbox:repo-a/T001:1:deadbeef",
            "action": "checkbox-update",
            "scope": {"repo_id": "repo-a", "task_id": "T001", "attempt": 1},
            "intent": {"input_digest": "a" * 64},
        },
    )
    assert intent["status"] == "pending"
    assert store.record_receipt(
        EXEC, f"{EXEC}:checkbox:repo-a/T001:1:deadbeef", after={"diff": "ok"}
    )


def test_receipt_without_intent_rejected(store):
    store.ensure_run(EXEC, "change-x")
    from hubcoord.runstore import RunStoreError

    with pytest.raises(RunStoreError) as excinfo:
        store.record_receipt(EXEC, f"{EXEC}:checkbox:repo-a/T001:1:deadbeef", after={})
    assert "no-intent" in str(excinfo.value)


def test_intent_requires_pending(store):
    store.ensure_run(EXEC, "change-x")
    from hubcoord.runstore import RunStoreError

    with pytest.raises(RunStoreError) as excinfo:
        store.write_intent(
            EXEC,
            {
                "operation_key": f"{EXEC}:x:1:a",
                "status": "recorded",
                "intent": {"input_digest": "b" * 64},
            },
        )
    assert "intent-first" in str(excinfo.value)


def test_uncertain_then_reconcile(store):
    store.ensure_run(EXEC, "change-x")
    key = f"{EXEC}:archive:store:1:deadbeef"
    store.write_intent(EXEC, {"operation_key": key, "intent": {"input_digest": "c" * 64}})
    uncertain = store.mark_uncertain(EXEC, key, findings={"probe": "git-head"})
    assert uncertain["status"] == "uncertain"
    reconciled = store.reconcile(EXEC, key, outcome={"resolved": True})
    assert reconciled["status"] == "reconciled"
    operations = {row["operation_key"]: row for row in store.operations(EXEC)}
    assert operations[key]["status"] == "reconciled"
    state = store.read_state(EXEC)
    assert state["operations"][key]["status"] == "reconciled"


def test_interruption_between_intent_and_receipt_visible(store):
    """Simulated crash after intent, before any receipt: pending intent survives."""
    store.ensure_run(EXEC, "change-x")
    key = f"{EXEC}:checkbox:repo-a/T001:1:deadbeef"
    store.write_intent(EXEC, {"operation_key": key, "intent": {"input_digest": "d" * 64}})
    rows = store.operations(EXEC)
    assert [row["status"] for row in rows] == ["pending"]


def test_uncertain_operation_key_reuse_rejected(store):
    store.ensure_run(EXEC, "change-x")
    key = f"{EXEC}:w:1:e"
    store.write_intent(EXEC, {"operation_key": key, "intent": {"input_digest": "e" * 64}})
    from hubcoord.runstore import RunStoreError

    with pytest.raises(RunStoreError) as excinfo:
        store.write_intent(EXEC, {"operation_key": key, "intent": {"input_digest": "e" * 64}})
    assert "operation-key-reuse" in str(excinfo.value)
