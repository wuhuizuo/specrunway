"""Operator visibility: status detail/follow, log discovery, executions, approval."""

from __future__ import annotations

import json
import os
import pty
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from specrunway import observability
from specrunway.cli import main as specrunway_main
from specrunway.freezer import freeze_execution, new_execution_id
from specrunway.runstore import FileRunStore, atomic_write_json

TOOLS = {"openspec": "1.15.0", "spec_kit": "1.2.1", "agent_profile": "fake-agent"}
START = "2026-11-08T02:00:00.000000+00:00"
FINISH = "2026-11-08T02:00:05.000000+00:00"
FAILED_AT = "2026-11-08T02:00:07.000000+00:00"


def _manifest(change_id: str = "observe-demo") -> dict:
    return {
        "api_version": "specrunway/v1",
        "store_uid": "67f80512-00d1-4b0f-b5cd-3a1aad009095",
        "change_id": change_id,
        "change_uid": "9c3e5e4e-2c2e-4b6e-8f9c-000000000095",
        "repo_order": ["repo-a"],
        "repos": [
            {
                "repo_id": "repo-a",
                "base_ref": "main",
                "task_ids": ["T001"],
                "depends_on": [],
                "allowed_paths": ["src/"],
                "test_profile": "unit",
            }
        ],
        "acceptance": [{"id": "AC01", "requirement": "works.", "verifies": ["T001"]}],
    }


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _control(tmp_path: Path, *, phase: str = "implementing", gate: str | None = None):
    control = tmp_path / "control"
    (control / ".specrunway").mkdir(parents=True)
    (control / ".specify").mkdir()
    repo = tmp_path / "repo-a"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "src").mkdir()
    (repo / "src" / "keep.py").write_text("KEEP = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(
        repo,
        "-c",
        "user.name=f",
        "-c",
        "user.email=f@example.org",
        "commit",
        "-q",
        "-m",
        "init",
    )
    store_dir = tmp_path / "store"
    change = store_dir / "openspec" / "changes" / "observe-demo"
    (change / "specs" / "repo-a-delivery").mkdir(parents=True)
    (change / "proposal.md").write_text(
        "# p\n\n## Why\nw\n\n## What Changes\nx\n", encoding="utf-8"
    )
    (change / "design.md").write_text("# d\n\n## Approach\na\n", encoding="utf-8")
    (change / "tasks.md").write_text("# Tasks\n\n- [ ] 1.1 [T001] Work.\n", encoding="utf-8")
    (change / "specs" / "repo-a-delivery" / "spec.md").write_text(
        "# repo-a-delivery Specification\n\n## ADDED Requirements\n\n"
        "### Requirement: Demo SHALL run\n\nIt SHALL run.\n\n"
        "#### Scenario: Go\n\n- **WHEN** ran\n- **THEN** true\n",
        encoding="utf-8",
    )
    repos_cfg = {"repo-a": {"path": str(repo), "remote_identity": "https://e/r.git"}}
    (control / "local.yaml").write_text(
        json.dumps(
            {
                "store": {"id": "observe-store", "path": str(store_dir)},
                "repos": repos_cfg,
                "agent_profile": "fake-agent",
                "max_workers": 1,
            }
        ),
        encoding="utf-8",
    )
    store = FileRunStore(control / ".specrunway")
    execution_id = new_execution_id()
    store.ensure_run(execution_id, "observe-demo")
    snapshot = freeze_execution(execution_id, change, _manifest(), repos_cfg, TOOLS)
    atomic_write_json(store.run_dir(execution_id) / "snapshot.json", snapshot)

    def seed(next_state: dict) -> None:
        next_state["phase"] = phase
        next_state["pending_gate"] = gate

    store.update_state(execution_id, seed, store.read_state(execution_id)["revision"])
    return {
        "control": control,
        "store": store,
        "execution_id": execution_id,
        "snapshot": snapshot,
        "change": change,
        "repos": repos_cfg,
    }


def _write_native_log(control: Path, run_id: str, events: list) -> Path:
    path = control / ".specify" / "workflows" / "runs" / run_id / "log.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )
    return path


def _seed_native(control: Path, store: FileRunStore, execution_id: str, run_id: str):
    def mutate(next_state: dict) -> None:
        next_state["native_run_id"] = run_id

    store.update_state(execution_id, mutate, store.read_state(execution_id)["revision"])


@pytest.mark.parametrize(
    "events,final_phase,expected_status",
    [
        (
            [
                {"event": "step_started", "step_id": "plan-gate", "type": "gate",
                 "timestamp": START},
                {"event": "step_completed", "step_id": "plan-gate", "status": "paused",
                 "timestamp": FINISH},
                {"event": "workflow_finished", "status": "paused", "timestamp": FINISH},
            ],
            "awaiting_plan_review",
            "paused",
        ),
        (
            [
                {"event": "step_started", "step_id": "implement:repo:0",
                 "type": "specrunway", "timestamp": START},
            ],
            "implementing",
            "failed",
        ),
        (
            [
                {"event": "step_started", "step_id": "complete", "type": "specrunway",
                 "timestamp": START},
                {"event": "step_completed", "step_id": "complete", "status": "completed",
                 "timestamp": FINISH},
                {"event": "workflow_finished", "status": "completed", "timestamp": FINISH},
            ],
            "ready_for_review",
            "completed",
        ),
    ],
)
def test_status_reports_step_start_elapsed_and_log(
    tmp_path, capsys, events, final_phase, expected_status
):
    fixture = _control(tmp_path, phase=final_phase)
    control = fixture["control"]
    store = fixture["store"]
    execution_id = fixture["execution_id"]
    _seed_native(control, store, execution_id, "native-1")
    log_path = _write_native_log(control, "native-1", events)
    if expected_status == "failed":

        def fail(next_state: dict) -> None:
            next_state["last_failure"] = {
                "step_id": "implement:repo:0",
                "code": "agent-failed",
                "message": "agent failed",
                "log_path": None,
                "recorded_at": FAILED_AT,
            }

        store.update_state(execution_id, fail, store.read_state(execution_id)["revision"])

    rc = specrunway_main(
        ["status", "--execution", execution_id, "--root", str(control), "--json"]
    )
    payload = json.loads(_captured(capsys))
    step = payload["data"]["current_step"]
    assert step["step_id"]
    assert step["status"] == expected_status
    assert step["started_at"] == START
    assert step["log_path"] == str(log_path)
    if expected_status != "failed":
        assert step["elapsed_seconds"] == pytest.approx(5.0, abs=0.001)
    assert rc == 0


def _captured(capsys) -> str:
    return capsys.readouterr().out


def test_status_follow_streams_step_transitions(tmp_path):
    fixture = _control(tmp_path, phase="implementing")
    control = fixture["control"]
    store = fixture["store"]
    execution_id = fixture["execution_id"]
    _seed_native(control, store, execution_id, "native-1")
    path = control / ".specify" / "workflows" / "runs" / "native-1" / "log.jsonl"
    path.parent.mkdir(parents=True)

    def append(events: list) -> None:
        with path.open("a", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event) + "\n")

    append([{"event": "step_started", "step_id": "prepare", "timestamp": START}])
    polls = {"count": 0}

    def fake_sleep(_seconds):
        polls["count"] += 1
        if polls["count"] == 1:
            append(
                [
                    {"event": "step_completed", "step_id": "prepare",
                     "status": "completed", "timestamp": FINISH},
                    {"event": "step_started", "step_id": "implement:repo:0",
                     "timestamp": FINISH},
                ]
            )
        elif polls["count"] == 2:
            append(
                [
                    {"event": "step_completed", "step_id": "implement:repo:0",
                     "status": "completed", "timestamp": FAILED_AT},
                    {"event": "workflow_finished", "status": "completed",
                     "timestamp": FAILED_AT},
                ]
            )

            def settle(next_state: dict) -> None:
                next_state["phase"] = "ready_for_review"

            store.update_state(
                execution_id, settle, store.read_state(execution_id)["revision"]
            )

    events = list(
        observability.iter_status_transitions(
            control, execution_id, poll_interval=0, sleep=fake_sleep
        )
    )
    assert [event["step"]["step_id"] for event in events] == [
        "prepare",
        "implement:repo:0",
        "implement:repo:0",
    ]
    assert events[0]["step"]["status"] == "running"
    assert events[-1]["step"]["status"] == "completed"
    assert events[-1]["step"]["elapsed_seconds"] == pytest.approx(2.0, abs=0.001)
    assert events[-1]["phase"] == "ready_for_review"


def test_run_forwards_native_progress_to_stderr_only(tmp_path, monkeypatch, capsys):
    from specrunway import runner

    control = tmp_path / "control"
    control.mkdir()

    def fake_prepare(_root, change):
        return {"execution_id": "exec-1"}

    def fake_start(_root, execution_id, progress_stream=None):
        progress_stream.write("[native] prepare started\n")
        return {
            "status": "paused",
            "run_id": "native-1",
            "current_step_id": "plan-gate",
        }

    monkeypatch.setattr(runner, "prepare_execution", fake_prepare)
    monkeypatch.setattr(runner, "start_execution", fake_start)
    rc = specrunway_main(
        ["run", "--change", "observe-demo", "--root", str(control), "--json"]
    )
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["api_version"] == "specrunway/v1"
    assert payload["data"]["execution_id"] == "exec-1"
    assert "[native]" not in captured.out
    assert "[native] prepare started" in captured.err


def test_specify_workflow_forwards_real_native_log_and_keeps_json(tmp_path, monkeypatch):
    from specrunway import runner

    control = tmp_path / "control"
    (control / ".specify" / "workflows" / "runs").mkdir(parents=True)
    script = tmp_path / "bin" / "specify"
    script.parent.mkdir()
    script.write_text(
        f"""#!{sys.executable}
import json
from pathlib import Path
runs = Path.cwd() / ".specify" / "workflows" / "runs" / "r2"
runs.mkdir(parents=True, exist_ok=True)
(runs / "log.jsonl").write_text(
    json.dumps({{"event": "step_started", "step_id": "prepare", "timestamp": "{START}"}}) + "\\n"
    + json.dumps({{"event": "step_completed", "step_id": "prepare", "status": "completed", "timestamp": "{FINISH}"}}) + "\\n"
)
print(json.dumps({{"status": "paused", "run_id": "r2", "current_step_id": "plan-gate"}}))
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setattr(runner, "resolve_tool_bin", lambda *a, **k: str(script))
    stream = __import__("io").StringIO()
    payload = runner._specify_workflow(
        ["workflow", "run", "wf"], control, progress_stream=stream
    )
    assert payload["status"] == "paused"
    assert "[native] prepare started" in stream.getvalue()
    assert "[native] prepare completed in 5.0s" in stream.getvalue()


def test_logs_lists_kinds_and_refuses_missing(tmp_path, capsys):
    fixture = _control(tmp_path, phase="ready_for_review")
    control = fixture["control"]
    store = fixture["store"]
    execution_id = fixture["execution_id"]
    run_dir = store.run_dir(execution_id)
    (run_dir / "logs" / "repo-a" / "1").mkdir(parents=True)
    (run_dir / "logs" / "repo-a" / "1" / "agent.log").write_text(
        "agent output\n", encoding="utf-8"
    )
    (run_dir / "logs" / "repo-a" / "1" / "tests.log").write_text(
        "1 passed\n", encoding="utf-8"
    )
    _seed_native(control, store, execution_id, "native-1")
    _write_native_log(
        control,
        "native-1",
        [{"event": "step_started", "step_id": "prepare", "timestamp": START}],
    )

    rc = specrunway_main(
        ["logs", "--execution", execution_id, "--root", str(control), "--json"]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert {row["kind"] for row in payload["data"]["logs"]} == {
        "agent",
        "test",
        "native",
    }

    rc = specrunway_main(
        [
            "logs",
            "--execution",
            execution_id,
            "--root",
            str(control),
            "--kind",
            "test",
            "--repo",
            "repo-a",
            "--attempt",
            "9",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["error"]["code"] == "log-missing"


def test_logs_follow_prints_existing_and_new_content(tmp_path, capsys):
    fixture = _control(tmp_path, phase="ready_for_review")
    control = fixture["control"]
    store = fixture["store"]
    execution_id = fixture["execution_id"]
    log = store.run_dir(execution_id) / "logs" / "repo-a" / "1" / "agent.log"
    log.parent.mkdir(parents=True)
    log.write_text("first line\n", encoding="utf-8")

    rc = specrunway_main(
        [
            "logs",
            "--execution",
            execution_id,
            "--root",
            str(control),
            "--kind",
            "agent",
            "--follow",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "first line" in out
    assert str(log) in out


def test_executions_lists_pending_gate(tmp_path, capsys):
    fixture = _control(tmp_path, phase="awaiting_plan_review", gate="plan")
    rc = specrunway_main(
        ["executions", "--root", str(fixture["control"]), "--json"]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["data"]["pending"] == [fixture["execution_id"]]
    assert payload["data"]["executions"][0]["pending_gate"] == "plan"


def test_approve_pending_resolves_single_and_records_receipt(tmp_path, capsys):
    fixture = _control(tmp_path, phase="awaiting_plan_review", gate="plan")
    rc = specrunway_main(
        [
            "approve",
            "--pending",
            "--actor",
            "operator",
            "--root",
            str(fixture["control"]),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0, payload
    assert payload["data"]["execution_id"] == fixture["execution_id"]
    assert payload["data"]["kind"] == "plan"
    receipt = (
        fixture["store"].run_dir(fixture["execution_id"]) / "approvals" / "plan.json"
    )
    assert receipt.is_file()
    assert json.loads(receipt.read_text(encoding="utf-8"))["auth_level"] == "self_asserted"


def test_approve_pending_zero_and_conflicting(tmp_path, capsys):
    fixture = _control(tmp_path, phase="implementing", gate=None)
    rc = specrunway_main(
        [
            "approve",
            "--pending",
            "--actor",
            "operator",
            "--root",
            str(fixture["control"]),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["error"]["code"] == "no-pending-execution"

    conflicted = _control(tmp_path / "conflict", phase="awaiting_plan_review", gate="plan")
    second_id = new_execution_id()
    conflicted["store"].ensure_run(second_id, "observe-demo")
    second_snapshot = freeze_execution(
        second_id,
        conflicted["change"],
        _manifest(),
        conflicted["repos"],
        TOOLS,
    )
    atomic_write_json(
        conflicted["store"].run_dir(second_id) / "snapshot.json", second_snapshot
    )

    def pending(next_state: dict) -> None:
        next_state["phase"] = "awaiting_plan_review"
        next_state["pending_gate"] = "plan"

    conflicted["store"].update_state(
        second_id, pending, conflicted["store"].read_state(second_id)["revision"]
    )
    rc = specrunway_main(
        [
            "approve",
            "--pending",
            "--actor",
            "operator",
            "--root",
            str(conflicted["control"]),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["error"]["code"] == "pending-execution-conflict"
    assert second_id in payload["error"]["message"]


def _approve_argv(fixture: dict) -> list:
    return [
        sys.executable,
        "-m",
        "specrunway.cli",
        "approve",
        "--execution",
        fixture["execution_id"],
        "--kind",
        "plan",
        "--actor",
        "operator",
        "--interactive",
        "--root",
        str(fixture["control"]),
        "--json",
    ]


def test_approve_interactive_records_on_pty(tmp_path):
    fixture = _control(tmp_path, phase="awaiting_plan_review", gate="plan")
    master, slave = pty.openpty()
    process = subprocess.Popen(
        _approve_argv(fixture),
        stdin=slave,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    os.close(slave)
    try:
        os.write(master, b"y\n")
        stdout, stderr = process.communicate(timeout=30)
    finally:
        os.close(master)
    assert process.returncode == 0, (stdout, stderr)
    payload = json.loads(stdout)
    assert payload["data"]["kind"] == "plan"
    receipt = (
        fixture["store"].run_dir(fixture["execution_id"]) / "approvals" / "plan.json"
    )
    assert receipt.is_file()


def test_approve_interactive_refuses_without_terminal(tmp_path):
    fixture = _control(tmp_path, phase="awaiting_plan_review", gate="plan")
    argv = _approve_argv(fixture)
    argv = [part for part in argv if part != "--json"]
    process = subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert process.returncode == 1
    assert "not-a-tty" in process.stderr
    receipt = (
        fixture["store"].run_dir(fixture["execution_id"]) / "approvals" / "plan.json"
    )
    assert not receipt.exists()


def test_current_step_uses_state_without_native_log(tmp_path):
    fixture = _control(tmp_path, phase="implementing")
    store = fixture["store"]

    def mutate(next_state: dict) -> None:
        next_state["current_step_id"] = "complete"

    store.update_state(
        fixture["execution_id"], mutate, store.read_state(fixture["execution_id"])["revision"]
    )
    step = observability.current_step(
        fixture["control"],
        fixture["execution_id"],
        store.read_state(fixture["execution_id"]),
        now=datetime(2026, 11, 8, 2, 0, 5, tzinfo=UTC),
    )
    assert step["step_id"] == "complete"
    assert step["elapsed_seconds"] is None
    assert step["log_path"] is None
