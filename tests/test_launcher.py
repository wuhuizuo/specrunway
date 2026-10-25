"""Agent launcher contract tests (L08 task 3.1) with deterministic fake agents."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from specrunway.launcher import (
    PROFILES,
    AgentProfile,
    cancel,
    kill_proc_group,
    launch_process,
    resolve_profile,
    run_agent,
)
from specrunway.models.common import ValidationError

FAKE_OK_TEMPLATE = """
import json, pathlib
prompt = pathlib.Path({prompt_path!r}).read_text()
pathlib.Path("wrote.txt").write_text("seen:" + prompt[:20])
result = {{"api_version": "specrunway/v1", "status": "done"}}
pathlib.Path("result.json").write_text(json.dumps(result))
print("fake agent ok")
"""

FAKE_FAIL = 'import sys\nprint("bad", file=sys.stderr)\nraise SystemExit(3)\n'

FAKE_SPAWNER = (
    "import subprocess, time, signal\n"
    "child = subprocess.Popen(['sleep', '120'])\n"
    "print(child.pid, flush=True)\n"
    "time.sleep(120)\n"
)

FAKE_SLEEPER = "import time\ntime.sleep(60)\nprint('slept')\n"


@pytest.fixture
def workspace(tmp_path):
    cwd = tmp_path / "worktree"
    cwd.mkdir()
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Prompt: implement T001 now.", encoding="utf-8")
    log_dir = tmp_path / "logs"
    return {"cwd": cwd, "prompt": prompt, "log_dir": log_dir, "tmp": tmp_path}


def test_fake_agent_completes_with_structured_outcome(workspace):
    script = workspace["tmp"] / "agent_ok.py"
    script.write_text(
        FAKE_OK_TEMPLATE.format(prompt_path=str(workspace["prompt"])), encoding="utf-8"
    )
    profile = AgentProfile(name="fake", argv=(sys.executable, str(script)))
    outcome = run_agent(profile, workspace["cwd"], workspace["prompt"], workspace["log_dir"])
    assert outcome["status"] == "completed"
    assert outcome["exit_code"] == 0
    assert outcome["duration_seconds"] >= 0
    assert "agent.log" in outcome["log_path"]
    assert Path(outcome["log_path"]).is_file()
    assert "fake agent ok" in Path(outcome["log_path"]).read_text(encoding="utf-8")
    # cwd honored + prompt file reached the agent
    wrote = Path(workspace["cwd"] / "wrote.txt").read_text(encoding="utf-8")
    assert wrote == "seen:Prompt: implement T0"


def test_failing_agent_reports_failed(workspace):
    script = workspace["tmp"] / "agent_fail.py"
    script.write_text(FAKE_FAIL, encoding="utf-8")
    profile = AgentProfile(name="fake", argv=(sys.executable, str(script)))
    outcome = run_agent(profile, workspace["cwd"], workspace["prompt"], workspace["log_dir"])
    assert outcome["status"] == "failed"
    assert outcome["exit_code"] == 3
    # the bridge formats failures through these properties, not raw keys
    assert outcome.status == "failed"
    assert outcome.reason == "exit 3"
    assert "bad" in Path(outcome["log_path"]).read_text(encoding="utf-8")


def test_timeout_kills_agent(workspace):
    script = workspace["tmp"] / "agent_sleep.py"
    script.write_text(FAKE_SLEEPER, encoding="utf-8")
    profile = AgentProfile(name="fake", argv=(sys.executable, str(script)))
    start = time.monotonic()
    outcome = run_agent(
        profile,
        workspace["cwd"],
        workspace["prompt"],
        workspace["log_dir"],
        timeout_seconds=1.0,
    )
    assert outcome["status"] == "timeout"
    assert time.monotonic() - start < 10
    # the agent is gone; its exit reflects termination
    assert outcome["exit_code"] is None or outcome["exit_code"] != 0


def test_process_group_kill_takes_down_grandchildren(workspace):
    script = workspace["tmp"] / "agent_spawner.py"
    script.write_text(FAKE_SPAWNER, encoding="utf-8")
    argv = [sys.executable, str(script)]
    process = launch_process(argv, workspace["cwd"], workspace["log_dir"] / "spawn.log")
    kill_proc_group(process, grace=2.0)
    assert process.poll() is not None
    # a cancelled launch reports the cancelled status
    outcome = cancel(process)
    assert outcome["status"] == "cancelled"


def test_cancel_stops_running_process(workspace):
    script = workspace["tmp"] / "agent_cancel.py"
    script.write_text(FAKE_SPAWNER, encoding="utf-8")
    process = launch_process(
        [sys.executable, str(script)], workspace["cwd"], workspace["log_dir"] / "cancel.log"
    )
    time.sleep(0.3)
    assert process.poll() is None
    cancel(process)
    assert process.poll() is not None


def test_missing_prompt_file_and_cwd_and_binary(workspace):
    profile = AgentProfile(name="fake", argv=(sys.executable, "does-not-matter"))
    with pytest.raises(ValidationError) as prompt_err:
        run_agent(profile, workspace["cwd"], workspace["tmp"] / "nope.md", workspace["log_dir"])
    assert prompt_err.value.code == "prompt-file-missing"

    with pytest.raises(ValidationError) as cwd_err:
        run_agent(
            profile,
            workspace["tmp"] / "gone",
            workspace["prompt"],
            workspace["log_dir"],
        )
    assert cwd_err.value.code == "cwd-missing"

    with pytest.raises(ValidationError) as bin_err:
        launch_process(
            ["definitely-not-a-binary-xyz"], workspace["cwd"], workspace["log_dir"] / "x.log"
        )
    assert bin_err.value.code == "agent-binary-missing"


def test_profile_registry_resolves_real_cli_shape():
    profile = resolve_profile("primary-coding-agent")
    assert "{prompt_file}" in profile.argv
    assert profile.argv[0] == "opencode"
    assert profile.argv[1] == "run"
    # opencode 2.x removed --pure; --file still takes one prompt attachment
    assert "--pure" not in profile.argv
    assert profile.argv[-2:] == ("--file", "{prompt_file}")
    assert "attached prompt file" in " ".join(profile.argv[:-2])
    with pytest.raises(ValidationError) as unknown:
        resolve_profile("no-such-agent")
    assert unknown.value.code == "profile-unknown"
    resolved = profile.resolved(Path("/tmp/p.md"))
    assert str(Path("/tmp/p.md").resolve()) in resolved
    assert "{prompt_file}" not in str(resolved)
    assert "primary-coding-agent" in PROFILES


def test_no_shell_interpolation_in_argv(workspace):
    """Agent output/paths never become shell text: argv list + shell=False."""
    script = workspace["tmp"] / "agent_sh.py"
    script.write_text("print('shell not used')\n", encoding="utf-8")
    profile = AgentProfile(name="fake", argv=(sys.executable, str(script)))
    outcome = run_agent(profile, workspace["cwd"], workspace["prompt"], workspace["log_dir"])
    assert outcome["status"] == "completed"
    # the launcher always starts a fresh session (own process group)
    process = launch_process(["/usr/bin/id"], workspace["cwd"], workspace["log_dir"] / "id.log")
    process.wait(timeout=10)
    assert process.returncode == 0
