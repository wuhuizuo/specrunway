"""FileRunStore: locked JSON state, atomic writes, ownership, operation intents."""

from __future__ import annotations

import errno
import fcntl
import json
import os
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

HUB_API_VERSION = "hub/v1"
RUNS_DIR = "runs"
LOCK_FILE = ".lock"
ACTIVE_FILE = "active.json"


class RunStoreError(RuntimeError):
    """RunStore misuse with a stable machine code."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class ExecutionConflictError(RunStoreError):
    def __init__(self, message: str):
        super().__init__("execution-conflict", message)


class RevisionConflictError(RunStoreError):
    def __init__(self, message: str):
        super().__init__("revision-conflict", message)


class StateCorruptError(RunStoreError):
    def __init__(self, message: str):
        super().__init__("state-corrupt", message)


class LockTimeoutError(RunStoreError):
    def __init__(self, message: str):
        super().__init__("lock-timeout", message)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class FileRunStore:
    """Single-writer local state root: ``<hub_root>/runs/<execution_id>/``.

    One control/Store checkout hosts one active execution. All mutating calls
    must hold the checkout lock (``lock``); readers may run without it.
    """

    def __init__(self, hub_root: Path):
        self.hub_root = Path(hub_root)
        self.runs_root = self.hub_root / RUNS_DIR
        self.lock_path = self.hub_root / LOCK_FILE

    # ------------------------------------------------------------------ locking
    @contextmanager
    def lock(self, timeout: float = 10.0, blocking: bool = True) -> Iterator:
        self.hub_root.mkdir(parents=True, exist_ok=True)
        handle = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            try:
                if blocking:
                    _flock_deadline(handle, timeout)
                else:
                    _flock_once(handle)
            except OSError as exc:
                if exc.errno in (errno.EAGAIN, errno.EACCES):
                    raise LockTimeoutError(
                        f"control checkout is locked by another hub process ({self.lock_path})"
                    ) from exc
                raise
            yield
        finally:
            try:
                fcntl.flock(handle, fcntl.LOCK_UN)
            finally:
                os.close(handle)

    # ----------------------------------------------------------------- ownership
    def active_owner(self) -> dict | None:
        path = self._active_path()
        data = _read_json_or_none(path)
        if not data:
            return None
        execution_id = data.get("execution_id")
        if not isinstance(execution_id, str) or not execution_id:
            raise StateCorruptError(f"{path} lacks execution_id")
        return data

    def claim_activity(self, execution_id: str, pid: int | None = None) -> dict:
        """Attach the active-owner record; refuses a different active execution."""
        owner = self.active_owner()
        if owner and owner["execution_id"] != execution_id:
            raise ExecutionConflictError(
                f"{owner['execution_id']} is active on this checkout; refuse to claim {execution_id}"
            )
        if owner:
            return owner
        record = {
            "api_version": HUB_API_VERSION,
            "execution_id": execution_id,
            "pid": pid if pid is not None else os.getpid(),
            "started_at": _now(),
        }
        self._active_path().parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self._active_path(), record)
        return record

    def release_activity(self, execution_id: str) -> None:
        owner = self.active_owner()
        if owner and owner["execution_id"] != execution_id:
            raise ExecutionConflictError(
                f"active owner is {owner['execution_id']}; refusing release on behalf of {execution_id}"
            )
        path = self._active_path()
        if path.is_file():
            path.unlink()

    def _active_path(self) -> Path:
        return self.hub_root / ACTIVE_FILE

    # ---------------------------------------------------------------- run state
    def run_dir(self, execution_id: str) -> Path:
        return self.runs_root / execution_id

    def ensure_run(self, execution_id: str, change_id: str) -> Path:
        path = self.run_dir(execution_id)
        (path / "operations").mkdir(parents=True, exist_ok=True)
        state_path = path / "state.json"
        if not state_path.exists():
            state = {
                "api_version": HUB_API_VERSION,
                "execution_id": execution_id,
                "change_id": change_id,
                "phase": "planning",
                "revision": 1,
                "native_run_id": None,
                "created_at": _now(),
                "updated_at": _now(),
                "budgets": {},
                "approvals": {},
                "results": {},
                "operations": {},
            }
            atomic_write_json(state_path, state)
        return path

    def read_state(self, execution_id: str) -> dict:
        path = self.run_dir(execution_id) / "state.json"
        data = _read_json_or_none(path)
        if data is None:
            if not path.is_file():
                raise RunStoreError(
                    "no-execution", f"no state.json for execution {execution_id}"
                )
            raise StateCorruptError(f"{path} is not parseable JSON")
        for key in ("execution_id", "revision", "phase"):
            if key not in data:
                raise StateCorruptError(f"{path} missing {key}")
        if data["execution_id"] != execution_id:
            raise StateCorruptError(
                f"{path} names execution_id={data['execution_id']!r}; expected {execution_id!r}"
            )
        return data

    def update_state(self, execution_id: str, mutate, expected_revision: int) -> dict:
        """
        Mutate state under a compare-and-swap on ``revision``.

        Returns the new state. Mutators must not write the revision.
        """
        path = self.run_dir(execution_id) / "state.json"
        current = self.read_state(execution_id)
        if current["revision"] != expected_revision:
            raise RevisionConflictError(
                f"{path} was written by another writer (revision {current['revision']} "
                f"!= expected {expected_revision})"
            )
        next_state = dict(current)
        mutate(next_state)
        next_state.pop("revision", None)
        next_state["revision"] = current["revision"] + 1
        next_state["updated_at"] = _now()
        for immutable in ("execution_id", "created_at"):
            next_state[immutable] = current[immutable]
        atomic_write_json(path, next_state)
        return next_state

    # ---------------------------------------------------------------- operations
    def _op_path(self, execution_id: str, operation_key: str) -> Path:
        """Stable on-disk name; keys use : and / separators that must flatten."""
        safe = operation_key.replace(":", "_").replace("/", "__")
        return self.run_dir(execution_id) / "operations" / f"{safe}.json"

    def write_intent(self, execution_id: str, operation: dict) -> dict:
        """Persist intent BEFORE the external side effect (status → pending)."""
        before = operation.get("status")
        if before and before != "pending":
            raise RunStoreError("intent-first", "write_intent requires a pending operation")
        record = dict(operation)
        record.setdefault("status", "pending")
        record.setdefault("started_at", _now())
        operation_key = str(record["operation_key"])
        path = self._op_path(execution_id, operation_key)
        if path.exists():
            existing = _read_json_or_none(path) or {}
            if existing.get("status") not in (None, "reconciled"):
                raise RunStoreError(
                    "operation-key-reuse",
                    f"non-terminated operation {operation_key} still open under {path}",
                )
        atomic_write_json(path, record)
        return record

    def record_receipt(self, execution_id: str, operation_key: str, after: dict) -> dict:
        """Attach after-evidence and mark recorded for a successful side effect."""
        path = self._op_path(execution_id, operation_key)
        record = _read_json_or_none(path)
        if record is None:
            raise RunStoreError(
                "no-intent", f"no operation {operation_key} was written before its receipt"
            )
        record["after"] = after
        record["status"] = "recorded"
        record["finished_at"] = _now()
        atomic_write_json(path, record)
        self._index_operation(execution_id, record)
        return record

    def mark_uncertain(self, execution_id: str, operation_key: str, findings: dict) -> dict:
        path = self._op_path(execution_id, operation_key)
        record = _read_json_or_none(path)
        if record is None:
            raise RunStoreError("no-intent", f"missing operation {operation_key}")
        record["after"] = findings
        record["status"] = "uncertain"
        record["finished_at"] = _now()
        atomic_write_json(path, record)
        self._index_operation(execution_id, record)
        return record

    def reconcile(self, execution_id: str, operation_key: str, outcome: dict) -> dict:
        path = self._op_path(execution_id, operation_key)
        record = _read_json_or_none(path)
        if record is None:
            raise RunStoreError("no-intent", f"missing operation {operation_key}")
        if record.get("status") != "uncertain":
            raise RunStoreError(
                "reconcile-terminal",
                f"operation {operation_key} is {record.get('status')!r}, not uncertain",
            )
        record["after"] = outcome
        record["status"] = "reconciled"
        atomic_write_json(path, record)
        self._index_operation(execution_id, record)
        return record

    def _index_operation(self, execution_id: str, record: dict) -> None:
        for _retry in range(5, 0, -1):
            try:
                state = self.read_state(execution_id)
            except StateCorruptError:
                return
            operations = dict(state.get("operations") or {})
            operations[record["operation_key"]] = {
                "status": record["status"],
                "after": record.get("after"),
            }
            revision = state["revision"]

            def mutate(next_state: dict, *, ops=operations) -> None:
                next_state["operations"] = ops

            try:
                self.update_state(execution_id, mutate, expected_revision=revision)
                return
            except RevisionConflictError:
                continue
        raise RunStoreError(
            "index-conflict", f"cannot index operation {record['operation_key']}"
        )

    def operations(self, execution_id: str) -> list:
        directory = self.run_dir(execution_id) / "operations"
        if not directory.is_dir():
            return []
        rows = []
        for path in sorted(directory.glob("*.json")):
            data = _read_json_or_none(path)
            if data:
                rows.append(data)
        return rows


def _flock_once(handle: int) -> None:
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _flock_deadline(handle: int, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            _flock_once(handle)
            return
        except OSError as exc:
            if exc.errno not in (errno.EAGAIN, errno.EACCES):
                raise
            if time.monotonic() >= deadline:
                raise LockTimeoutError(f"lock wait exceeded {timeout:.1f}s") from exc
            time.sleep(0.05)


def _read_json_or_none(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        if not path.is_file():
            return None
        raise StateCorruptError(f"{path} is not parseable JSON: {exc}") from exc
    return data if isinstance(data, dict) else None


def atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON via tmp file in the same directory + fsync + atomic replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    data = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)
    handle = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(handle, data.encode("utf-8"))
        os.fsync(handle)
    finally:
        os.close(handle)
    os.replace(tmp, path)
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def connect(hub_root: Path) -> FileRunStore:
    return FileRunStore(Path(hub_root))


__all__ = [
    "HUB_API_VERSION",
    "ExecutionConflictError",
    "FileRunStore",
    "LockTimeoutError",
    "RevisionConflictError",
    "RunStoreError",
    "StateCorruptError",
    "atomic_write_json",
    "connect",
]
