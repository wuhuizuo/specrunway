"""Trusted test runner: configured argv against the recorded commit, not agent claims."""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from specrunway.models.common import ValidationError, json_digest

DEFAULT_TIMEOUT_SECONDS = 900.0


@dataclass(frozen=True)
class TestProfile:
    name: str
    argv: tuple
    cwd: str = ""
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def command(self) -> list:
        argv: list = []
        for part in self.argv:
            if part == "python":
                argv.append(sys.executable)
            else:
                argv.append(part)
        return argv

    def frozen(self) -> dict:
        payload = {
            "command": list(self.argv),
            "cwd": self.cwd,
            "timeout_seconds": int(self.timeout_seconds),
        }
        payload["config_digest"] = json_digest(payload)
        return payload


#: Built-in fallback registry (commands come from the trusted package, never
#: from agent output). Control configuration may override a name or add new
#: profiles; see ``freeze_test_profiles``.
TEST_PROFILES: dict = {
    "unit": TestProfile(name="unit", argv=("python", "-m", "pytest", "-q")),
}


def _is_safe_relative(cwd: str) -> bool:
    if not cwd:
        return True
    if cwd.startswith(("/", "\\")):
        return False
    parts = [part for part in cwd.replace("\\", "/").split("/") if part not in ("", ".")]
    return ".." not in parts


def _profile_from_entry(name: str, entry: dict) -> TestProfile:
    command = entry.get("command")
    if not (isinstance(command, list) and command and all(isinstance(p, str) for p in command)):
        raise ValidationError(
            "test-command", f"test profile {name!r} command must be a non-empty argv list"
        )
    cwd = str(entry.get("cwd") or "")
    if not _is_safe_relative(cwd):
        raise ValidationError(
            "test-cwd",
            f"test profile {name!r} cwd must stay inside the worktree: {cwd!r}",
        )
    timeout = entry.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS
    return TestProfile(
        name=name,
        argv=tuple(command),
        cwd=cwd.strip("/"),
        timeout_seconds=float(timeout),
    )


def resolve_test_profile(name: str, configured: dict | None = None) -> TestProfile:
    if configured and name in configured:
        return _profile_from_entry(name, configured[name])
    profile = TEST_PROFILES.get(name)
    if profile is None:
        known = sorted(set(TEST_PROFILES) | set(configured or {}))
        raise ValidationError(
            "unknown-profile",
            f"unknown test profile {name!r}; known: {known}",
        )
    return profile


def freeze_test_profiles(manifest: dict, configured: dict | None = None) -> dict:
    """Freeze every profile referenced by the manifest with a stable digest."""
    frozen: dict = {}
    for repo in manifest["repos"]:
        name = repo.get("test_profile") or "unit"
        if name in frozen:
            continue
        profile = resolve_test_profile(name, configured)
        frozen[name] = profile.frozen()
    return frozen


def profile_for_repo(snapshot: dict, repo_entry: dict) -> TestProfile:
    """Prefer the frozen profile; fall back to built-ins for legacy snapshots."""
    name = repo_entry.get("test_profile") or "unit"
    frozen = (snapshot.get("test_profiles") or {}).get(name)
    if not frozen:
        return resolve_test_profile(name)
    return TestProfile(
        name=name,
        argv=tuple(frozen["command"]),
        cwd=str(frozen.get("cwd") or ""),
        timeout_seconds=float(frozen.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS),
    )


def profile_cwd(worktree: Path, profile: TestProfile) -> Path:
    worktree = Path(worktree)
    return worktree / profile.cwd if profile.cwd else worktree


def run_test_command(
    argv: list,
    cwd: Path,
    log_path: Path,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    env: dict | None = None,
) -> dict:
    """Run tests synchronously; the receipt is evidence the runner produced."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        with log_path.open("w", encoding="utf-8") as log:
            done = subprocess.run(
                argv,
                cwd=str(cwd),
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
                check=False,
                env=env,
            )
        status = "passed" if done.returncode == 0 else "failed"
        exit_code = done.returncode
        reason = "" if done.returncode == 0 else f"exit {done.returncode}"
    except subprocess.TimeoutExpired:
        status, exit_code = "failed", -1
        reason = f"killed after {timeout_seconds}s"
    except OSError as exc:
        status, exit_code = "error", -1
        reason = f"launch failed: {exc}"
    return {
        "status": status,
        "exit_code": exit_code,
        "command": list(argv),
        "cwd": str(cwd),
        "started_at": started_at,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_seconds": round(time.monotonic() - started, 3),
        "log_path": str(log_path.resolve()),
        "reason": reason,
    }


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "TEST_PROFILES",
    "TestProfile",
    "freeze_test_profiles",
    "profile_cwd",
    "profile_for_repo",
    "resolve_test_profile",
    "run_test_command",
]
