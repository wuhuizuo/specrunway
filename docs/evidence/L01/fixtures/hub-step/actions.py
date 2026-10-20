"""Harmless local actions exercised by the L01 probe workflows.

Every action returns a hub/v1-style envelope so the probe proves the shared
output contract: ``api_version``, ``action``, ``ok``, business IDs, ``data``,
``evidence``, and ``warnings``.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any


def envelope(
    action: str,
    ok: bool,
    data: dict,
    evidence: list = None,
    warnings: list = None,
    store_uid: str = "",
    change_uid: str = "",
    execution_id: str = "",
):
    result = {
        "api_version": "hub/v1",
        "action": action,
        "ok": bool(ok),
        "store_uid": store_uid,
        "change_uid": change_uid,
        "execution_id": execution_id,
        "data": data,
        "evidence": list(evidence or []),
        "warnings": list(warnings or []),
    }
    if not ok:
        result["error"] = {"code": "probe-failure", "message": "probe failed on demand",
                           "retryable": True, "details": {}}
    return result


class _FailedAction(Exception):
    def __init__(self, message: str, output: dict):
        super().__init__(message)
        self.message = message
        self.output = output


def _scratch(config: dict) -> Path:
    return Path(str(config.get("scratch") or "probe-log.ndjson"))


def _append_event(scratch: Path, event: str, payload: dict) -> None:
    record = {"event": event, "time": time.time(), **payload}
    with scratch.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _read_events(scratch: Path, event: str) -> list:
    if not scratch.exists():
        return []
    matches = []
    for line in scratch.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parsed = json.loads(line)
        if parsed.get("event") == event:
            matches.append(parsed)
    return matches


def action_prepare(config: dict, context: Any) -> dict:
    repos = config.get("repos") or []
    execution = str(config.get("execution") or "")
    return envelope(
        "prepare",
        True,
        {"repos": list(repos), "execution_id": execution},
        store_uid=str(config.get("store_uid") or ""),
        change_uid=str(config.get("change_uid") or ""),
        execution_id=execution,
    )


def action_note(config: dict, context: Any) -> dict:
    scratch = _scratch(config)
    label = str(config.get("label") or "note")
    extra = config.get("value")
    history = _read_events(scratch, "note")
    _append_event(scratch, "note", {"label": label, "value": extra,
                                    "execution_id": str(config.get("execution") or "")})
    result = envelope(
        "note",
        True,
        {"label": label, "prior_note_count": len(history)},
        execution_id=str(config.get("execution") or ""),
    )
    return result


def action_wait(config: dict, context: Any) -> dict:
    seconds = float(config.get("seconds") or 0)
    scratch = _scratch(config)
    _append_event(scratch, "wait", {"seconds": seconds})
    if seconds > 0:
        time.sleep(seconds)
    return envelope("wait", True, {"seconds": seconds})


def action_run_repo(config: dict, context: Any) -> dict:
    scratch = _scratch(config)
    repo_id = str(config.get("repo") or context.item)
    _append_event(scratch, "run-repo", {"repo_id": repo_id})
    return envelope(
        "run-repo",
        True,
        {
            "repo_id": repo_id,
            "task_ids": list(config.get("task_ids") or []),
            "passed": True,
            "result_ref": f"artifact:repo-result-{repo_id}",
        },
        evidence=["artifact:probe-unit-tests"],
    )


def action_verify_round(config: dict, context: Any) -> dict:
    scratch = _scratch(config)
    threshold = int(config.get("repair_threshold") or 0)
    prior = _read_events(scratch, "verify-round")
    current = len(prior) + 1
    _append_event(scratch, "verify-round", {"round": current})
    needs_repair = current < threshold
    return envelope(
        "verify-round",
        True,
        {"round": current, "needs_repair": needs_repair, "threshold": threshold},
    )


def action_collect_count(config: dict, context: Any) -> dict:
    joined = config.get("value")
    count = len(joined) if isinstance(joined, list) else -1
    return envelope("collect-summary", True, {"item_count": count})


def action_failed_when(config: dict, context: Any) -> dict:
    scratch = _scratch(config)
    label = str(config.get("label") or "target")
    prior = _read_events(scratch, f"attempt-{label}")
    execution = str(config.get("execution") or "")
    envelope_ok = envelope("failed-when", True, {"round": len(prior) + 1},
                           execution_id=execution)
    if config.get("fail_now") is True:
        _append_event(scratch, f"attempt-{label}", {"round": len(prior) + 1})
        raise _FailedAction(
            "probe simulation: failing on demand (fail_now=true)",
            envelope_ok,
        )
    _append_event(scratch, f"attempt-{label}", {"round": len(prior) + 1})
    return envelope_ok


def action_spawn_children(config: dict, context: Any) -> dict:
    seconds = int(config.get("seconds") or 240)
    scratch = _scratch(config)
    procs = []
    pids = []
    for _ in range(2):
        proc = subprocess.Popen(
            ["sleep", str(seconds)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        pids.append(proc.pid)
        procs.append(proc)
    _append_event(scratch, "spawn-children", {"pids": pids, "seconds": seconds})
    return envelope("spawn-children", True, {"pids": pids, "seconds": seconds})


_DISPATCH = {
    "prepare": action_prepare,
    "note": action_note,
    "wait": action_wait,
    "run-repo": action_run_repo,
    "verify-round": action_verify_round,
    "collect-summary": action_collect_count,
    "failed-when": action_failed_when,
    "spawn-children": action_spawn_children,
}


def dispatch_action(action: str, config: dict, context: Any) -> dict:
    handler = _DISPATCH.get(action)
    if handler is None:
        raise _FailedAction(
            f"Unknown hub probe action {action!r}",
            envelope(action, False, {}),
        )
    return handler(config, context)
