"""Operator visibility: step detail, follows, log discovery, and execution lists."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from specrunway.runstore import FileRunStore, RunStoreError, _read_json_or_none

#: Phases that need no further progress from a running workflow.
TERMINAL_PHASES = {"ready_for_review", "archived", "blocked"}
SETTLED_PHASES = TERMINAL_PHASES | {
    "awaiting_plan_review",
    "awaiting_implementation_review",
    "failed",
    "interrupted",
}
ACTIVE_PHASES = {"planning", "implementing"}

LOG_KINDS = ("agent", "test", "native")


class ObservabilityError(RuntimeError):
    """Read-only observability refusal with a stable machine code."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


def _parse_ts(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _elapsed(start: datetime | None, end: datetime | None = None, now=None) -> float | None:
    if start is None:
        return None
    finish = end or now or datetime.now(UTC)
    return round(max(0.0, (finish - start).total_seconds()), 3)


def native_log_path(control_root: Path, run_id: str | None) -> Path | None:
    if not run_id:
        return None
    return (
        Path(control_root) / ".specify" / "workflows" / "runs" / str(run_id) / "log.jsonl"
    )


def native_run_ids(state: dict) -> list:
    """Current native run first, then preserved runs without duplicates."""
    rows = []
    current = state.get("native_run_id")
    if current:
        rows.append(str(current))
    for row in state.get("native_runs") or []:
        if isinstance(row, dict) and row.get("run_id"):
            candidate = str(row["run_id"])
            if candidate not in rows:
                rows.append(candidate)
    return rows


def read_native_events(path: Path | None) -> list:
    if path is None or not Path(path).is_file():
        return []
    events = []
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _step_summaries(events: list) -> tuple[list, dict]:
    """Pair step_started/step_completed events; keep still-open steps."""
    open_steps: dict = {}
    summaries: list = []
    for event in events:
        kind = event.get("event")
        step_id = str(event.get("step_id") or "")
        if kind == "step_started" and step_id:
            open_steps[step_id] = {
                "step_id": step_id,
                "step_type": event.get("type"),
                "started_at": event.get("timestamp"),
            }
        elif kind == "step_completed" and step_id:
            started = open_steps.pop(step_id, None)
            start_ts = _parse_ts((started or {}).get("started_at"))
            end_ts = _parse_ts(event.get("timestamp"))
            summaries.append(
                {
                    "step_id": step_id,
                    "step_type": (started or {}).get("step_type"),
                    "status": str(event.get("status") or "completed"),
                    "started_at": (started or {}).get("started_at"),
                    "finished_at": event.get("timestamp"),
                    "elapsed_seconds": _elapsed(start_ts, end_ts),
                }
            )
    return summaries, open_steps


def current_step(
    control_root: Path,
    execution_id: str,
    state: dict,
    now: datetime | None = None,
) -> dict:
    """The step that is running, or the most recent step that settled."""
    run_id = state.get("native_run_id")
    path = native_log_path(control_root, run_id)
    events = read_native_events(path)
    summaries, open_steps = _step_summaries(events)
    log_path = str(path) if path is not None and path.is_file() else None
    failure = state.get("last_failure") or {}

    if open_steps:
        latest = list(open_steps.values())[-1]
        start_ts = _parse_ts(latest.get("started_at"))
        step = {
            "step_id": latest["step_id"],
            "step_type": latest.get("step_type"),
            "status": "running",
            "started_at": latest.get("started_at"),
            "finished_at": None,
            "elapsed_seconds": _elapsed(start_ts, None, now),
            "log_path": log_path,
        }
        if failure.get("step_id") == latest["step_id"]:
            end_ts = _parse_ts(failure.get("recorded_at"))
            step["status"] = "failed"
            step["finished_at"] = failure.get("recorded_at")
            step["elapsed_seconds"] = _elapsed(start_ts, end_ts)
            step["log_path"] = failure.get("log_path") or log_path
        return step

    if summaries:
        latest = summaries[-1]
        step = {
            "step_id": latest["step_id"],
            "step_type": latest.get("step_type"),
            "status": latest["status"],
            "started_at": latest.get("started_at"),
            "finished_at": latest.get("finished_at"),
            "elapsed_seconds": latest.get("elapsed_seconds"),
            "log_path": log_path,
        }
    else:
        step = {
            "step_id": state.get("current_step_id"),
            "step_type": None,
            "status": None,
            "started_at": None,
            "finished_at": None,
            "elapsed_seconds": None,
            "log_path": log_path,
        }

    if failure and (
        not step.get("step_id") or failure.get("step_id") == step.get("step_id")
    ):
        step["status"] = "failed"
        if failure.get("recorded_at") and not step.get("finished_at"):
            step["finished_at"] = failure.get("recorded_at")
        if failure.get("log_path"):
            step["log_path"] = failure.get("log_path")
    return step


def _default_status(control_root: Path, execution_id: str) -> dict:
    from specrunway.recovery import execution_status

    return execution_status(Path(control_root), execution_id)


def iter_status_transitions(
    control_root: Path,
    execution_id: str,
    *,
    poll_interval: float = 0.5,
    max_seconds: float | None = None,
    sleep=time.sleep,
):
    """Yield a row whenever the phase or current step changes.

    Stops when no step is running any more (completed, paused, failed) or the
    caller set a bound. The operator can still interrupt the consumer.
    """
    started = time.monotonic()
    previous = None
    while True:
        status = _default_status(Path(control_root), execution_id)
        step = status.get("current_step") or {}
        key = (
            status.get("phase"),
            status.get("pending_gate"),
            step.get("step_id"),
            step.get("status"),
        )
        if key != previous:
            previous = key
            yield {
                "execution_id": execution_id,
                "change_id": status.get("change_id"),
                "phase": status.get("phase"),
                "pending_gate": status.get("pending_gate"),
                "step": step,
            }
        if step.get("status") != "running":
            return
        if status.get("phase") in TERMINAL_PHASES or status.get("last_failure"):
            return
        if max_seconds is not None and time.monotonic() - started >= max_seconds:
            return
        sleep(poll_interval)


def format_status_transition(event: dict) -> str:
    step = event.get("step") or {}
    elapsed = step.get("elapsed_seconds")
    duration = f" in {elapsed:.1f}s" if isinstance(elapsed, (int, float)) else ""
    gate = f" pending_gate={event['pending_gate']}" if event.get("pending_gate") else ""
    log = f" log {step['log_path']}" if step.get("log_path") else ""
    return (
        f"status {event.get('phase')}: {step.get('step_id') or 'unknown'} "
        f"{step.get('status') or 'unknown'}{duration}{gate}{log}"
    )


def list_executions(control_root: Path) -> list:
    """All executions ordered newest first, including their pending gate."""
    root = Path(control_root) / ".specrunway"
    runs_root = root / "runs"
    if not runs_root.is_dir():
        return []
    active = None
    try:
        active = FileRunStore(root).active_owner()
    except RunStoreError:
        active = None
    active_id = (active or {}).get("execution_id")
    rows = []
    for state_path in sorted(runs_root.glob("*/state.json")):
        state = _read_json_or_none(state_path)
        if state is None:
            continue
        run_dir = state_path.parent
        snapshot = _read_json_or_none(run_dir / "snapshot.json") or {}
        execution_id = str(state.get("execution_id") or run_dir.name)
        rows.append(
            {
                "execution_id": execution_id,
                "change_id": snapshot.get("change_id") or state.get("change_id"),
                "phase": state.get("phase"),
                "pending_gate": state.get("pending_gate"),
                "revision": state.get("revision"),
                "native_run_id": state.get("native_run_id"),
                "created_at": state.get("created_at"),
                "updated_at": state.get("updated_at"),
                "active_owner": execution_id == active_id,
                "last_failure": state.get("last_failure"),
            }
        )
    rows.sort(key=lambda row: (str(row.get("created_at") or ""), row["execution_id"]), reverse=True)
    return rows


def pending_executions(control_root: Path) -> list:
    rows = [
        row
        for row in list_executions(control_root)
        if row.get("pending_gate") and row.get("phase") not in TERMINAL_PHASES
    ]
    return [row for row in rows if row.get("phase") != "archived"]


def resolve_pending_execution(control_root: Path) -> dict:
    pending = pending_executions(control_root)
    if not pending:
        raise ObservabilityError(
            "no-pending-execution", "no execution is waiting at an approval gate"
        )
    if len(pending) > 1:
        names = ", ".join(row["execution_id"] for row in pending)
        raise ObservabilityError(
            "pending-execution-conflict",
            f"several executions wait at a gate ({names}); pass --execution explicitly",
        )
    return pending[0]


def _attempt_number(path: Path) -> int:
    try:
        return int(path.name)
    except ValueError:
        return 0


def enumerate_logs(
    control_root: Path,
    execution_id: str,
    *,
    kind: str | None = None,
    repo_id: str | None = None,
    attempt: int | None = None,
) -> list:
    """Locate agent, test, and native logs without exposing the layout."""
    store = FileRunStore(Path(control_root) / ".specrunway")
    state = store.read_state(execution_id)
    run_dir = store.run_dir(execution_id)
    wanted = "all" if not kind else kind
    rows = []
    if wanted in ("all", "agent", "test"):
        logs_root = run_dir / "logs"
        if logs_root.is_dir():
            for repo_dir in sorted(p for p in logs_root.iterdir() if p.is_dir()):
                if repo_id and repo_dir.name != repo_id:
                    continue
                for attempt_dir in sorted(
                    (p for p in repo_dir.iterdir() if p.is_dir()), key=_attempt_number
                ):
                    attempt_number = _attempt_number(attempt_dir)
                    if attempt is not None and attempt_number != attempt:
                        continue
                    for name, log_kind in (("agent.log", "agent"), ("tests.log", "test")):
                        if wanted not in ("all", log_kind):
                            continue
                        path = attempt_dir / name
                        if path.is_file():
                            rows.append(
                                {
                                    "kind": log_kind,
                                    "repo_id": repo_dir.name,
                                    "attempt": attempt_number,
                                    "path": str(path),
                                    "size": path.stat().st_size,
                                }
                            )
    if wanted in ("all", "native"):
        for index, run_id in enumerate(native_run_ids(state), start=1):
            if attempt is not None and index != attempt:
                continue
            path = native_log_path(control_root, run_id)
            if path is not None and path.is_file():
                rows.append(
                    {
                        "kind": "native",
                        "repo_id": None,
                        "attempt": index,
                        "run_id": run_id,
                        "path": str(path),
                        "size": path.stat().st_size,
                    }
                )
    return rows


def _settled(control_root: Path, execution_id: str) -> bool:
    try:
        state = FileRunStore(Path(control_root) / ".specrunway").read_state(execution_id)
    except RunStoreError:
        return True
    return str(state.get("phase")) not in ACTIVE_PHASES


def iter_log_chunks(
    control_root: Path,
    execution_id: str,
    *,
    kind: str | None = None,
    repo_id: str | None = None,
    attempt: int | None = None,
    poll_interval: float = 0.5,
    max_seconds: float | None = None,
    sleep=time.sleep,
):
    """Tail every matching log from the beginning, then follow appended bytes."""
    offsets: dict = {}
    announced: set = set()
    started = time.monotonic()
    settled_passes = 0
    while True:
        rows = enumerate_logs(
            control_root,
            execution_id,
            kind=kind,
            repo_id=repo_id,
            attempt=attempt,
        )
        produced = False
        for row in rows:
            key = str(row["path"])
            path = Path(row["path"])
            offset = offsets.get(key, 0)
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size < offset:
                offset = 0
            if size == offset:
                continue
            if key not in announced:
                announced.add(key)
                scope = row.get("repo_id") or "native"
                yield f"==> {row['kind']} {scope}/{row.get('attempt')} {key} <==\n"
            try:
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    handle.seek(offset)
                    chunk = handle.read()
                    offsets[key] = handle.tell()
            except OSError:
                continue
            if chunk:
                yield chunk if chunk.endswith("\n") else chunk + "\n"
                produced = True
        if _settled(control_root, execution_id):
            settled_passes = 0 if produced else settled_passes + 1
            if not produced and settled_passes >= 1:
                return
        if max_seconds is not None and time.monotonic() - started >= max_seconds:
            return
        sleep(poll_interval)


class NativeProgressWatcher:
    """Follow the native workflow log of a just-started run and print transitions."""

    def __init__(self, control_root: Path, stream, known: set | None = None):
        self.runs_root = Path(control_root) / ".specify" / "workflows" / "runs"
        self.stream = stream
        self._offsets = {}
        self._buffers: dict = {}
        self._starts: dict = {}
        for path in known or ():
            path = Path(path)
            try:
                self._offsets[str(path)] = path.stat().st_size
            except OSError:
                self._offsets[str(path)] = 0

    def poll(self) -> None:
        if not self.runs_root.is_dir():
            return
        for path in sorted(self.runs_root.glob("*/log.jsonl")):
            key = str(path)
            offset = self._offsets.get(key, 0)
            try:
                with path.open("rb") as handle:
                    handle.seek(offset)
                    data = handle.read()
            except OSError:
                continue
            if not data:
                continue
            self._offsets[key] = offset + len(data)
            buffered = self._buffers.get(key, b"") + data
            lines = buffered.split(b"\n")
            self._buffers[key] = lines.pop()
            for raw in lines:
                self._consume(raw)

    def _consume(self, raw: bytes) -> None:
        if not raw.strip():
            return
        try:
            event = json.loads(raw.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return
        if not isinstance(event, dict):
            return
        line = format_native_event(event, self._starts)
        if line:
            self.stream.write(line + "\n")
            try:
                self.stream.flush()
            except (AttributeError, ValueError):
                pass


def format_native_event(event: dict, starts: dict | None = None) -> str | None:
    starts = starts if starts is not None else {}
    kind = event.get("event")
    step_id = event.get("step_id")
    if kind == "step_started" and step_id:
        starts[step_id] = event.get("timestamp")
        return f"[native] {step_id} started"
    if kind == "step_completed" and step_id:
        start = _parse_ts(starts.pop(step_id, None))
        end = _parse_ts(event.get("timestamp"))
        elapsed = _elapsed(start, end)
        duration = f" in {elapsed:.1f}s" if elapsed is not None else ""
        return f"[native] {step_id} {event.get('status') or 'completed'}{duration}"
    if kind == "step_failed" and step_id:
        return f"[native] {step_id} failed: {event.get('error') or 'step failed'}"
    if kind == "workflow_finished":
        return f"[native] workflow {event.get('status') or 'finished'}"
    return None


__all__ = [
    "ACTIVE_PHASES",
    "LOG_KINDS",
    "SETTLED_PHASES",
    "TERMINAL_PHASES",
    "NativeProgressWatcher",
    "ObservabilityError",
    "current_step",
    "enumerate_logs",
    "format_native_event",
    "format_status_transition",
    "iter_log_chunks",
    "iter_status_transitions",
    "list_executions",
    "native_log_path",
    "native_run_ids",
    "pending_executions",
    "read_native_events",
    "resolve_pending_execution",
]
