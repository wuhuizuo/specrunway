"""Normal resume, receipt reuse, and orphan-running recovery (L13)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from hubcoord import launcher, recovery
from hubcoord.approvals import record_approval
from hubcoord.freezer import freeze_execution, new_execution_id
from hubcoord.models.common import json_digest
from hubcoord.runstore import FileRunStore, atomic_write_json
from hubcoord.worktrees import create_worktree, head_oid

REPO = Path(__file__).resolve().parents[1]
FAKE_AGENT = Path(__file__).with_name("fake_agent_cli.py")
TOOLS = {"openspec": "1.14.3", "spec_kit": "1.2.1", "agent_profile": "fake-agent"}


def _manifest() -> dict:
    return {
        "api_version": "hub/v1",
        "store_uid": "67f80512-00d1-4b0f-b5cd-3a1aad009094",
        "change_id": "resume-demo",
        "change_uid": "9c3e5e4e-2c2e-4b6e-8f9c-000000000094",
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
        "integration_profile": "e2e",
    }


@pytest.fixture
def paused(tmp_path, monkeypatch):
    control = tmp_path / "control"
    (control / ".hub").mkdir(parents=True)
    (control / ".specify").mkdir()
    repo = tmp_path / "repo-a"
    repo.mkdir()
    subprocess.run(
        ["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True, capture_output=True
    )
    (repo / "src").mkdir()
    (repo / "src" / "keep.py").write_text("KEEP = 1\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_base.py").write_text(
        "def test_base():\n    assert True\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=f",
            "-c",
            "user.email=f@example.org",
            "commit",
            "-q",
            "-m",
            "init",
        ],
        check=True,
        capture_output=True,
    )
    store_dir = tmp_path / "store"
    change = store_dir / "openspec" / "changes" / "resume-demo"
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
                "store": {"id": "resume-store", "path": str(store_dir)},
                "repos": repos_cfg,
                "agent_profile": "fake-agent",
                "max_workers": 1,
            }
        ),
        encoding="utf-8",
    )
    store = FileRunStore(control / ".hub")
    execution_id = new_execution_id()
    store.ensure_run(execution_id, "resume-demo")
    snapshot = freeze_execution(execution_id, change, _manifest(), repos_cfg, TOOLS)
    atomic_write_json(store.run_dir(execution_id) / "snapshot.json", snapshot)

    def seed(next_state: dict) -> None:
        next_state["phase"] = "awaiting_plan_review"
        next_state["pending_gate"] = "plan"
        next_state["native_run_id"] = "native-old"

    store.update_state(execution_id, seed, store.read_state(execution_id)["revision"])
    record_approval(
        store=store,
        execution_id=execution_id,
        kind="plan",
        snapshot=snapshot,
        actor="lead",
    )
    monkeypatch.setitem(
        launcher.PROFILES,
        "fake-agent",
        launcher.AgentProfile(
            name="fake-agent",
            argv=(sys.executable, str(FAKE_AGENT), "--file", "{prompt_file}", "fake"),
            timeout_seconds=120.0,
        ),
    )
    monkeypatch.setenv("HUB_FAKE_SCENARIO", "pass")
    return {
        "control": control,
        "store": store,
        "execution_id": execution_id,
        "snapshot": snapshot,
        "repos": repos_cfg,
        "change": change,
        "repo": repo,
    }


def test_resume_refuses_changed_plan(paused):
    (paused["change"] / "proposal.md").write_text(
        "# p\n\n## Why\nchanged after approval\n", encoding="utf-8"
    )
    with pytest.raises(recovery.RecoveryError) as stale:
        recovery.resume_execution(paused["control"], paused["execution_id"])
    assert stale.value.code == "approval-stale"


def test_resume_refuses_missing_pending_approval(paused):
    paused["store"].run_dir(paused["execution_id"]).joinpath("approvals", "plan.json").unlink()
    with pytest.raises(recovery.RecoveryError) as refused:
        recovery.resume_execution(paused["control"], paused["execution_id"])
    assert refused.value.code == "no-approval"


def test_reusable_result_returns_verified_evidence(paused):
    store = paused["store"]
    execution_id = paused["execution_id"]
    snapshot = paused["snapshot"]
    worktree = create_worktree(
        paused["repo"],
        snapshot["repos"]["repo-a"]["base_oid"],
        store.run_dir(execution_id),
        "repo-a",
    )
    (worktree / "src" / "done.py").write_text("DONE = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(worktree), "add", "src"], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(worktree),
            "-c",
            "user.name=f",
            "-c",
            "user.email=f@example.org",
            "commit",
            "-q",
            "-m",
            "done",
        ],
        check=True,
        capture_output=True,
    )
    head = head_oid(worktree)
    result = {
        "api_version": "hub/v1",
        "execution_id": execution_id,
        "repo_id": "repo-a",
        "attempt": 1,
        "agent": "fake",
        "head_commit": head,
        "base_commit": snapshot["repos"]["repo-a"]["base_oid"],
        "tasks": [{"task_id": "T001", "decision": "implemented", "notes": ""}],
        "changed_paths": ["src/done.py"],
        "tests_claimed": {"status": "passed"},
        "created_at": "2026-10-20T00:00:00Z",
    }
    result["result_digest"] = json_digest(result)
    path = store.run_dir(execution_id) / "results" / "repo-a" / "1" / "result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, result)
    receipts = store.run_dir(execution_id) / "tests_receipts" / "repo-a"
    receipts.mkdir(parents=True, exist_ok=True)
    atomic_write_json(receipts / "1.json", {"status": "passed", "exit_code": 0})

    def seed(next_state: dict) -> None:
        next_state["results"] = {
            "repo-a": {
                "attempt": 1,
                "head_commit": head,
                "result_ref": str(path),
                "passed": True,
                "result_digest": result["result_digest"],
            }
        }

    store.update_state(execution_id, seed, store.read_state(execution_id)["revision"])
    reused = recovery.reusable_result(store, snapshot, "repo-a", paused["repos"])
    assert reused is not None and reused["reused"] is True
    assert reused["head_commit"] == head

    record = json.loads(path.read_text(encoding="utf-8"))
    record["tasks"][0]["notes"] = "tampered"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(recovery.RecoveryError) as conflict:
        recovery.reusable_result(store, snapshot, "repo-a", paused["repos"])
    assert conflict.value.code == "evidence-conflict"


def test_orphan_running_recovery_preserves_old_run(paused, monkeypatch):
    monkeypatch.setattr(
        recovery,
        "native_status",
        lambda _root, _run: {
            "status": "running",
            "current_step_id": "implement:repo:0",
        },
    )
    monkeypatch.setattr(recovery, "_process_alive", lambda _pid: False)
    calls = []

    def fake_start(control_root, execution_id):
        calls.append(execution_id)
        return {"run_id": "native-new", "status": "paused", "current_step_id": "plan-gate"}

    monkeypatch.setattr("hubcoord.runner.start_execution", fake_start)
    outcome = recovery.recover_execution(paused["control"], paused["execution_id"])
    assert outcome["run_id"] == "native-new"
    assert calls == [paused["execution_id"]]
    state = paused["store"].read_state(paused["execution_id"])
    assert state["phase"] == "interrupted"
    assert state["native_runs"][0]["run_id"] == "native-old"
    assert state["native_runs"][0]["status"] == "abandoned-running"


def test_orphan_recovery_refuses_live_process(paused, monkeypatch):
    monkeypatch.setattr(
        recovery,
        "native_status",
        lambda _root, _run: {"status": "running", "current_step_id": "implement:repo:0"},
    )
    monkeypatch.setattr(recovery, "_process_alive", lambda _pid: True)
    with pytest.raises(recovery.RecoveryError) as alive:
        recovery.recover_execution(paused["control"], paused["execution_id"])
    assert alive.value.code == "orphan-alive"


def test_status_reports_phases_and_operations(paused):
    summary = recovery.execution_status(paused["control"], paused["execution_id"])
    assert summary["phase"] == "awaiting_plan_review"
    assert summary["pending_gate"] == "plan"
    assert summary["approvals"]["plan"]["decision"] == "approve"
    assert summary["repo_order"] == ["repo-a"]
