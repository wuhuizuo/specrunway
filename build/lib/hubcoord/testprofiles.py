"""Trusted test runner: configured argv against the recorded commit, not agent claims."""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from hubcoord.models.common import ValidationError

DEFAULT_TIMEOUT_SECONDS = 900.0


@dataclass(frozen=True)
class TestProfile:
    name: str
    argv: tuple

    def command(self) -> list:
        argv: list = []
        for part in self.argv:
            if part == "python":
                argv.append(sys.executable)
            else:
                argv.append(part)
        return argv


#: Trusted profile registry (explicit argv per profile name; commands come from
#: the trusted hub package, never from agent output).
TEST_PROFILES: dict = {
    "unit": TestProfile(name="unit", argv=("python", "-m", "pytest", "-q")),
}


def resolve_test_profile(name: str) -> TestProfile:
    profile = TEST_PROFILES.get(name)
    if profile is None:
        raise ValidationError(
            "unknown-profile",
            f"unknown test profile {name!r}; known: {sorted(TEST_PROFILES)}",
        )
    return profile


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
        log_handle = log_path.open("wb")
    except OSError as exc:
        raise ValidationError(
            "log-open-failed", f"cannot open test log {log_path}: {exc}"
        ) from exc
    try:
        try:
            done = subprocess.run(
                argv,
                cwd=str(cwd),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                shell=False,
                timeout=timeout_seconds,
                env=env,
                check=False,
            )
            exit_code = done.returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            exit_code = None
            timed_out = True
    finally:
        log_handle.close()
    finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if timed_out:
        status = "error"
        reason = f"test run exceeded {timeout_seconds}s"
    elif exit_code == 0:
        status = "passed"
        reason = ""
    else:
        status = "failed"
        reason = f"exit {exit_code}"
    return {
        "status": status,
        "exit_code": exit_code,
        "command": argv,
        "cwd": str(cwd),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": round(time.monotonic() - started, 3),
        "log_path": str(log_path.resolve()),
        "reason": reason,
    }


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "TEST_PROFILES",
    "TestProfile",
    "resolve_test_profile",
    "run_test_command",
]
