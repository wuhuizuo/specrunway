"""Typed argv adapter for the pinned OpenSpec CLI (store routing, shell=False)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from shutil import which

PROTOCOL = {
    "setup": {"store", "registry"},
    "new_change": {"change", "root"},
    "status": {"changeName", "artifactPaths", "root"},
    "instructions": {"progress", "tasks"},
    "validate": {"items", "summary"},
    "archive": {"archive", "root"},
}
ERROR_SHAPES = ("error", "status")


class OpenSpecCommandError(RuntimeError):
    """Upstream command failed; exit_code and a stable code describe it."""

    def __init__(self, *, command: list, exit_code: int, code: str, message: str):
        self.command = command
        self.exit_code = exit_code
        self.code = code
        self.message = message
        super().__init__(
            f"openspec {command[0]}.. failed (exit {exit_code}): [{code}] {message}"
        )


class OpenSpecProtocolError(RuntimeError):
    """Payload shape/keys the adapter cannot safely interpret."""

    def __init__(self, *, command: list, message: str, payload=None):
        self.command = command
        self.message = message
        self.payload = payload
        super().__init__(f"unsupported OpenSpec protocol data after {command[0]}: {message}")


@dataclass
class OpenSpecAdapter:
    """Typed adapter; one instance per planning Store path."""

    store_path: Path
    store_id: str
    openspec_bin: str | None = None

    def __post_init__(self) -> None:
        self.store_path = Path(self.store_path).resolve()
        if self.openspec_bin is None:
            resolved = which("openspec")
            self.openspec_bin = resolved or "openspec"

    def _argv(self, *args: str) -> list:
        return [self.openspec_bin or "openspec", *args]

    def _run(self, args: list, expect_json: bool = True, parse_on_error: bool = False) -> dict:
        try:
            proc = subprocess.run(
                args,
                cwd=str(self.store_path),
                capture_output=True,
                text=True,
                shell=False,
                check=False,
                timeout=300,
            )
        except FileNotFoundError as exc:
            raise OpenSpecCommandError(
                command=args,
                exit_code=-1,
                code="tool-missing",
                message=f"openspec executable not found: {exc}",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise OpenSpecCommandError(
                command=args, exit_code=-1, code="timeout", message=str(exc)
            ) from exc
        if proc.returncode != 0:
            if parse_on_error and proc.stdout.strip().startswith("{"):
                try:
                    payload = self._parse_json(args, proc.stdout)
                except OpenSpecProtocolError:
                    payload = None
                if payload is not None and self._is_failure_result(payload):
                    return payload
            raise self._as_error(args, proc)
        if not expect_json:
            return {"stdout": proc.stdout}
        return self._parse_json(args, proc.stdout)

    def _is_failure_result(self, payload: dict) -> bool:
        """True for structured failure reports that carry per-item results."""
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            return False
        return all(isinstance(item, dict) and "valid" in item for item in items)

    def _as_error(self, args: list, proc: subprocess.CompletedProcess) -> OpenSpecCommandError:
        for text in (proc.stdout, proc.stderr):
            try:
                parsed = json.loads(text) if text.strip().startswith("{") else None
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                for shape in ERROR_SHAPES:
                    entries = parsed.get(shape)
                    rows = (
                        entries
                        if isinstance(entries, list)
                        else ([entries] if isinstance(entries, dict) else [])
                    )
                    for row in rows:
                        if isinstance(row, dict) and row.get("code"):
                            return OpenSpecCommandError(
                                command=args,
                                exit_code=proc.returncode,
                                code=str(row["code"]),
                                message=str(row.get("message", "")),
                            )
        stderr_tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        message = stderr_tail[-1] if stderr_tail else f"exit code {proc.returncode}"
        return OpenSpecCommandError(
            command=args, exit_code=proc.returncode, code="upstream-error", message=message
        )

    def _parse_json(self, args: list, stdout: str) -> dict:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise OpenSpecProtocolError(
                command=args,
                message=f"expected JSON on stdout: {exc}",
                payload=stdout[:400],
            ) from exc
        if not isinstance(payload, dict):
            raise OpenSpecProtocolError(
                command=args, message="expected a JSON object", payload=payload
            )
        return payload

    def _require_keys(self, command_name: str, payload: dict, required: set) -> None:
        missing = required - set(payload)
        if missing:
            raise OpenSpecProtocolError(
                command=[command_name],
                message=f"missing required keys {sorted(missing)}",
                payload=payload,
            )

    def store_setup(self) -> dict:
        """Register/create this store's OpenSpec planning home (idempotent upstream)."""
        args = self._argv(
            "store", "setup", self.store_id, "--path", str(self.store_path), "--json"
        )
        payload = self._run(args)
        self._require_keys("store setup", payload, PROTOCOL["setup"])
        return payload

    def new_change(self, change_id: str) -> dict:
        args = self._argv("new", "change", change_id, "--store", self.store_id, "--json")
        try:
            payload = self._run(args)
        except OpenSpecCommandError as exc:
            if exc.code == "upstream-error" and "already exists" in exc.message:
                exc.code = "change-exists"
            raise
        self._require_keys("new change", payload, PROTOCOL["new_change"])
        change = payload["change"]
        if not isinstance(change, dict) or not isinstance(change.get("id"), str):
            raise OpenSpecProtocolError(
                command=args, message="change.id missing", payload=payload
            )
        return {
            "change_id": change["id"],
            "change_path": change.get("path"),
            "schema": change.get("schema"),
            "root": payload["root"],
        }

    def status(self, change_id: str) -> dict:
        args = self._argv("status", "--change", change_id, "--store", self.store_id, "--json")
        payload = self._run(args)
        self._require_keys("status", payload, PROTOCOL["status"])
        root = payload.get("root") or {}
        if root.get("source") != "store" or root.get("store_id") != self.store_id:
            raise OpenSpecProtocolError(
                command=args,
                message=(
                    f"status resolved root source={root.get('source')!r} "
                    f"store_id={root.get('store_id')!r}; expected store {self.store_id!r}"
                ),
                payload=payload,
            )
        artifact_name: dict = {}
        for artifact, paths in payload["artifactPaths"].items():
            if isinstance(paths, dict):
                artifact_name[artifact] = paths.get("existingOutputPaths") or []
        return {
            "change_name": payload["changeName"],
            "schema": payload.get("schemaName"),
            "planning_complete": bool(payload.get("isPlanningComplete")),
            "is_complete": bool(payload.get("isComplete")),
            "artifacts": artifact_name,
            "root": root,
        }

    def instructions_apply(self, change_id: str) -> dict:
        args = self._argv(
            "instructions", "apply", "--change", change_id, "--store", self.store_id, "--json"
        )
        payload = self._run(args)
        self._require_keys("instructions apply", payload, PROTOCOL["instructions"])
        progress = payload["progress"]
        tasks = payload["tasks"]
        if not isinstance(progress, dict) or not isinstance(tasks, list):
            raise OpenSpecProtocolError(
                command=args,
                message="progress/tasks have unexpected types",
                payload=payload,
            )
        rows: list = []
        for row in tasks:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                raise OpenSpecProtocolError(
                    command=args, message="task row missing id", payload=payload
                )
            rows.append(
                {
                    "task_id": row["id"],
                    "description": row.get("description", ""),
                    "done": bool(row.get("done")),
                    "source_path": row.get("sourcePath"),
                    "line": row.get("line"),
                }
            )
        return {
            "progress": {
                "total": int(progress.get("total", 0)),
                "complete": int(progress.get("complete", 0)),
                "remaining": int(progress.get("remaining", 0)),
            },
            "tasks": rows,
            "state": payload.get("state"),
            "missing_artifacts": payload.get("missingArtifacts") or [],
            "missing_prerequisites": payload.get("missingPrerequisites") or [],
            "root": payload.get("root"),
        }

    def validate(self, change_id: str, strict: bool = True) -> dict:
        args = self._argv(
            "validate",
            change_id,
            "--store",
            self.store_id,
            *(["--strict"] if strict else []),
            "--json",
        )
        payload = self._run(args, parse_on_error=True)
        self._require_keys("validate", payload, PROTOCOL["validate"])
        items = payload["items"]
        if not isinstance(items, list) or not items:
            raise OpenSpecProtocolError(command=args, message="items empty", payload=payload)
        target = items[0]
        if not isinstance(target, dict) or not isinstance(target.get("valid"), bool):
            raise OpenSpecProtocolError(
                command=args, message="items[0].valid missing", payload=payload
            )
        issues: list = []
        for issue in target.get("issues") or []:
            if isinstance(issue, dict):
                issues.append(
                    {
                        "level": issue.get("level"),
                        "path": issue.get("path"),
                        "message": issue.get("message", ""),
                    }
                )
        return {"change_id": target.get("id"), "valid": target["valid"], "issues": issues}

    def archive(self, change_id: str, *, assume_yes: bool = True) -> dict:
        args = self._argv(
            "archive",
            change_id,
            "--store",
            self.store_id,
            *(["--yes"] if assume_yes else []),
            "--json",
        )
        payload = self._run(args)
        self._require_keys("archive", payload, PROTOCOL["archive"])
        result = payload["archive"]
        if not isinstance(result, dict):
            raise OpenSpecProtocolError(
                command=args, message="archive payload missing", payload=payload
            )
        return {
            "archived_as": result.get("archivedAs"),
            "path": result.get("path"),
            "specs_updated": bool(result.get("specsUpdated")),
            "totals": result.get("totals"),
            "root": payload["root"],
        }


__all__ = [
    "OpenSpecAdapter",
    "OpenSpecCommandError",
    "OpenSpecProtocolError",
]
