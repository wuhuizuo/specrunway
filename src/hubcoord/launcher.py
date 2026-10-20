"""Agent launcher: argv/cwd/prompt-file invocation with process-group control."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from hubcoord.models.common import ValidationError

#: Seconds between SIGTERM and SIGKILL when terminating agent process groups.
KILL_GRACE_SECONDS = 5.0

OUTCOME_STATUSES = {"completed", "failed", "timeout", "cancelled"}


@dataclass(frozen=True)
class AgentProfile:
    """One real CLI: a fixed argv template with a {prompt_file} placeholder."""

    name: str
    argv: tuple
    timeout_seconds: float = 1800.0

    def resolved(self, prompt_file: Path) -> list:
        parts: list = []
        for part in self.argv:
            text = part.replace("{prompt_file}", str(Path(prompt_file).resolve()))
            parts.append(text)
        return parts


#: The real coding agent CLI actually used (verified argv surface: ``opencode
#: run``); release acceptance exercises this profile live at the pinned version.
PROFILES: dict = {
    "primary-coding-agent": AgentProfile(
        name="primary-coding-agent",
        argv=(
            "opencode",
            "run",
            "--auto",
            "--pure",
            # 1.18.33 parses --file as an array: the message must precede it,
            # otherwise the fixed text is swallowed as a second attachment.
            "Execute the attached prompt file exactly; do not ask interactive questions.",
            "--file",
            "{prompt_file}",
        ),
    ),
}


class AgentOutcome(dict):
    """Structured launch result: status/exit/duration/log paths only."""

    @property
    def status(self) -> str:
        return self["status"]

    @property
    def reason(self) -> str:
        return str(self.get("reason") or "")


def resolve_profile(name: str) -> AgentProfile:
    profile = PROFILES.get(name)
    if profile is None:
        raise ValidationError(
            "profile-unknown",
            f"unknown agent profile {name!r}; known: {sorted(PROFILES)}",
        )
    return profile


def launch_process(
    argv: list,
    cwd: Path,
    log_path: Path,
    env: dict | None = None,
) -> subprocess.Popen:
    """Start the agent in its own process group; never through a shell."""
    if not shutil.which(argv[0]) and not Path(argv[0]).is_absolute():
        raise ValidationError(
            "agent-binary-missing", f"agent executable not found: {argv[0]!r}"
        )
    if not cwd.is_dir():
        raise ValidationError("cwd-missing", f"agent cwd does not exist: {cwd}")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("wb")
    try:
        return subprocess.Popen(
            argv,
            cwd=str(cwd),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            shell=False,
            start_new_session=True,
            env=env,
        )
    finally:
        log_handle.close()


def kill_proc_group(process: subprocess.Popen, grace: float = KILL_GRACE_SECONDS) -> None:
    """Terminate the whole agent process group (SIGTERM, then SIGKILL)."""
    try:
        pgid = os.getpgid(process.pid)
    except ProcessLookupError:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if process.poll() is not None:
            return
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + grace if sig == signal.SIGTERM else time.monotonic()
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return
            time.sleep(0.05)
        if sig == signal.SIGTERM:
            time.sleep(0.05)


def run_agent(
    profile: AgentProfile,
    cwd: Path,
    prompt_file: Path,
    log_dir: Path,
    timeout_seconds: float | None = None,
    env: dict | None = None,
) -> AgentOutcome:
    """Run the agent synchronously and return a structured outcome."""
    if not Path(prompt_file).is_file():
        raise ValidationError(
            "prompt-file-missing", f"prompt file does not exist: {prompt_file}"
        )
    argv = profile.resolved(prompt_file)
    started = time.monotonic()
    process = launch_process(argv, cwd, Path(log_dir) / "agent.log", env=env)
    timeout = profile.timeout_seconds if timeout_seconds is None else float(timeout_seconds)
    status = "completed"
    reason = ""
    try:
        return_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_proc_group(process)
        return_code = process.poll()
        status, reason = "timeout", f"killed after {timeout}s"
    if process.returncode is not None and process.returncode != 0 and status == "completed":
        status = "failed"
        reason = f"exit {process.returncode}"
    return AgentOutcome(
        status=status,
        exit_code=process.returncode if process.returncode is not None else return_code,
        duration_seconds=round(time.monotonic() - started, 3),
        log_path=str((Path(log_dir) / "agent.log").resolve()),
        reason=reason,
    )


def cancel(process: subprocess.Popen) -> AgentOutcome:
    """Operator-initiated cancellation of a running launch."""
    kill_proc_group(process)
    return AgentOutcome(
        status="cancelled",
        exit_code=process.poll(),
        duration_seconds=0.0,
        log_path="",
        reason="cancelled via process-group kill",
    )


__all__ = [
    "OUTCOME_STATUSES",
    "PROFILES",
    "AgentOutcome",
    "AgentProfile",
    "cancel",
    "kill_proc_group",
    "launch_process",
    "resolve_profile",
    "run_agent",
]
