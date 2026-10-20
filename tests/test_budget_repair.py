"""Bounded repair budgets, no-progress stop, persistent counters (L12 task 7.1)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from hubcoord import launcher
from hubcoord.bridge.actions import (
    HubActionError,
    action_complete,
    action_repair_round,
    action_run_repo,
    action_verify_round,
)
from hubcoord.freezer import freeze_execution, new_execution_id
from hubcoord.runstore import FileRunStore, atomic_write_json

REPO = Path(__file__).resolve().parents[1]
FAKE_AGENT = Path(__file__).with_name("fake_agent_cli.py")
TOOLS = {"openspec": "1.14.3", "spec_kit": "1.2.1", "agent_profile": "fake-agent"}


def _manifest(budget: dict | None = None) -> dict:
    manifest = {
        "api_version": "hub/v1",
        "store_uid": "67f80512-00d1-4b0f-b5cd-3a1aad009072",
        "change_id": "budget-demo",
        "change_uid": "9c3e5e4e-2c2e-4b6e-8f9c-000000000072",
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
    if budget is not None:
        merged = {"repo_max_attempts": 3, "integration_max_repairs": 2, "total_minutes": 120}
        merged.update(budget)
        manifest["budget"] = merged
    return manifest


@pytest.fixture
def budgeted(tmp_path, monkeypatch):
    control = tmp_path / "control"
    (control / ".hub").mkdir(parents=True)
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
    repos_cfg = {"repo-a": {"path": str(repo), "remote_identity": "https://e/r.git"}}
    (control / "local.yaml").write_text(
        json.dumps(
            {
                "store": {"id": "budget-store", "path": str(tmp_path / "store")},
                "repos": repos_cfg,
                "agent_profile": "fake-agent",
                "max_workers": 1,
            }
        ),
        encoding="utf-8",
    )
    plans = tmp_path / "plans" / "budget-demo"
    (plans / "specs" / "repo-a-delivery").mkdir(parents=True)
    (plans / "proposal.md").write_text(
        "# p\n\n## Why\nw\n\n## What Changes\nx\n", encoding="utf-8"
    )
    (plans / "design.md").write_text("# d\n\n## Approach\na\n", encoding="utf-8")
    (plans / "tasks.md").write_text("# Tasks\n\n- [ ] 1.1 [T001] Work.\n", encoding="utf-8")
    (plans / "specs" / "repo-a-delivery" / "spec.md").write_text(
        "# repo-a-delivery Specification\n\n## ADDED Requirements\n\n"
        "### Requirement: Demo SHALL run\n\nIt SHALL run.\n\n"
        "#### Scenario: Go\n\n- **WHEN** ran\n- **THEN** true\n",
        encoding="utf-8",
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
    return {"control": control, "plans": plans, "repos": repos_cfg}


def _freeze(budgeted, budget: dict | None = None, execution_id: str | None = None):
    store = FileRunStore(budgeted["control"] / ".hub")
    execution_id = execution_id or new_execution_id()
    store.ensure_run(execution_id, "budget-demo")
    snapshot = freeze_execution(
        execution_id, budgeted["plans"], _manifest(budget), budgeted["repos"], TOOLS
    )
    atomic_write_json(store.run_dir(execution_id) / "snapshot.json", snapshot)
    return store, execution_id, snapshot


def _cfg(budgeted, store, execution_id, action: str, **extra) -> dict:
    config = {
        "action": action,
        "root": str(budgeted["control"]),
        "execution": execution_id,
    }
    config.update(extra)
    return config


def test_repair_round_repairs_and_feedback_reaches_agent(budgeted, monkeypatch):
    monkeypatch.setenv("HUB_FAKE_SCENARIO", "fail-until-pass")
    monkeypatch.setenv("HUB_FAKE_FAIL_BEFORE", "1")
    store, execution_id, _snapshot = _freeze(budgeted)
    first = action_run_repo(
        _cfg(budgeted, store, execution_id, "run-repo", repo="repo-a"), None
    )
    assert first["data"]["passed"] is False

    verify = action_verify_round(
        _cfg(budgeted, store, execution_id, "verify-round", round=1), None
    )
    assert verify["data"]["needs_repair"] is True
    assert store.read_state(execution_id)["verification"]["repo-a"]["status"] == "failed"

    repair = action_repair_round(_cfg(budgeted, store, execution_id, "repair-round"), None)
    assert repair["data"]["repaired"] is True
    assert repair["data"]["rounds_used"] == 1
    state = store.read_state(execution_id)
    assert state["verification"]["repo-a"]["status"] == "passed"
    assert state["budgets"]["repo-a"]["attempts_used"] == 2

    prompt = (store.run_dir(execution_id) / "prompts" / "repo-a-2.md").read_text(
        encoding="utf-8"
    )
    assert "## Prior verification feedback" in prompt
    assert "status: failed" in prompt


def test_budget_exhausted_stops_and_counters_survive_restart(budgeted, monkeypatch):
    monkeypatch.setenv("HUB_FAKE_SCENARIO", "fail")
    store, execution_id, _snapshot = _freeze(
        budgeted, budget={"repo_max_attempts": 2, "integration_max_repairs": 2}
    )
    action_run_repo(_cfg(budgeted, store, execution_id, "run-repo", repo="repo-a"), None)
    action_verify_round(_cfg(budgeted, store, execution_id, "verify-round", round=1), None)

    with pytest.raises(HubActionError) as exhausted:
        action_repair_round(_cfg(budgeted, store, execution_id, "repair-round"), None)
    assert exhausted.value.output["error"]["code"] == "budget-exhausted"
    state = store.read_state(execution_id)
    assert state["phase"] == "blocked"
    assert state["budgets"]["repo-a"]["attempts_used"] == 2

    # restart: a fresh store handle sees the same persistent counters and stops
    restarted = FileRunStore(budgeted["control"] / ".hub")
    assert restarted.read_state(execution_id)["budgets"]["repo-a"]["attempts_used"] == 2
    with pytest.raises(HubActionError) as stopped:
        action_run_repo(
            _cfg(budgeted, restarted, execution_id, "run-repo", repo="repo-a"), None
        )
    assert stopped.value.output["error"]["code"] == "budget-exhausted"
    assert restarted.read_state(execution_id)["budgets"]["repo-a"]["attempts_used"] == 2


def test_no_progress_stops_before_burning_budget(budgeted, monkeypatch):
    monkeypatch.setenv("HUB_FAKE_SCENARIO", "noop")
    store, execution_id, _snapshot = _freeze(budgeted, budget={"repo_max_attempts": 3})
    action_run_repo(_cfg(budgeted, store, execution_id, "run-repo", repo="repo-a"), None)
    action_verify_round(_cfg(budgeted, store, execution_id, "verify-round", round=1), None)

    with pytest.raises(HubActionError) as stopped:
        action_repair_round(_cfg(budgeted, store, execution_id, "repair-round"), None)
    assert stopped.value.output["error"]["code"] == "no-progress"
    state = store.read_state(execution_id)
    assert state["phase"] == "blocked"
    assert state["budgets"]["repo-a"]["attempts_used"] == 2


def test_failed_verification_cannot_become_ready(budgeted, monkeypatch):
    monkeypatch.setenv("HUB_FAKE_SCENARIO", "fail")
    store, execution_id, _snapshot = _freeze(budgeted)
    action_run_repo(_cfg(budgeted, store, execution_id, "run-repo", repo="repo-a"), None)
    action_verify_round(_cfg(budgeted, store, execution_id, "verify-round", round=1), None)

    with pytest.raises(HubActionError) as refused:
        action_complete(_cfg(budgeted, store, execution_id, "complete"), None)
    assert refused.value.output["error"]["code"] == "verification-failed"
    assert store.read_state(execution_id)["phase"] != "ready_for_review"


def test_total_minutes_budget_refuses_attempt(budgeted, monkeypatch):
    monkeypatch.setenv("HUB_FAKE_SCENARIO", "pass")
    store, execution_id, _snapshot = _freeze(budgeted, budget={"total_minutes": 1})
    from hubcoord.runstore import atomic_write_json as write_json

    state = store.read_state(execution_id)
    state["created_at"] = "2020-01-01T00:00:00Z"
    write_json(store.run_dir(execution_id) / "state.json", state)

    with pytest.raises(HubActionError) as stopped:
        action_run_repo(_cfg(budgeted, store, execution_id, "run-repo", repo="repo-a"), None)
    assert stopped.value.output["error"]["code"] == "budget-exhausted"
    assert "total budget" in stopped.value.output["error"]["message"]
