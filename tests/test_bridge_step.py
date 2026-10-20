"""Installed bridge verification against the pinned Specify CLI (L10 task 5.1)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from hubcoord.approvals import record_approval
from hubcoord.bridge.actions import (
    HubActionError,
    action_collect_summary,
    action_complete,
    action_gate_check,
    action_prepare,
)
from hubcoord.freezer import freeze_execution, new_execution_id
from hubcoord.runstore import FileRunStore, atomic_write_json

REPO = Path(__file__).resolve().parents[1]
SPECIFY = REPO / ".venv" / "bin" / "specify"
TOOLS = {"openspec": "1.14.3", "spec_kit": "1.2.1", "agent_profile": "primary-coding-agent"}
MANIFEST = {
    "api_version": "hub/v1",
    "store_uid": "67f80512-00d1-4b0f-b5cd-3a1aad009002",
    "change_id": "bridge-demo",
    "change_uid": "9c3e5e4e-2c2e-4b6e-8f9c-000000000001",
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
def executed(tmp_path):
    """Control checkout + a real git repo + a frozen execution in the run store."""
    control = tmp_path / "control"
    (control / ".hub").mkdir(parents=True)
    repo = tmp_path / "repo-a"
    repo.mkdir()
    subprocess.run(
        ["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True, capture_output=True
    )
    (repo / "src").mkdir()
    (repo / "src" / "keep.py").write_text("KEEP = 1\n", encoding="utf-8")
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
            "-m",
            "init",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True
    )

    repos_cfg = {
        "repo-a": {"path": str(repo), "remote_identity": "https://example.org/repo-a.git"}
    }
    (control / "local.yaml").write_text(
        json.dumps(
            {
                "store": {"id": "registry-less-probe", "path": str(tmp_path / "store")},
                "repos": repos_cfg,
                "agent_profile": "primary-coding-agent",
                "max_workers": 1,
            }
        ),
        encoding="utf-8",
    )

    plans = tmp_path / "plans" / "bridge-demo"
    (plans / "specs" / "repo-a-delivery").mkdir(parents=True)
    (plans / "proposal.md").write_text(
        "# p\n\n## Why\nw\n\n## What Changes\nx\n", encoding="utf-8"
    )
    (plans / "design.md").write_text("# d\n\n## Approach\na\n", encoding="utf-8")
    (plans / "tasks.md").write_text("# Tasks\n\n- [ ] 1.1 [T001] Work one.\n", encoding="utf-8")
    (plans / "specs" / "repo-a-delivery" / "spec.md").write_text(
        "# repo-a-delivery Specification\n\n## ADDED Requirements\n\n"
        "### Requirement: Demo SHALL run\n\nIt SHALL run.\n\n"
        "#### Scenario: Go\n\n- **WHEN** ran\n- **THEN** true\n",
        encoding="utf-8",
    )

    execution_id = new_execution_id()
    store = FileRunStore(control / ".hub")
    store.ensure_run(execution_id, "bridge-demo")
    snapshot = freeze_execution(execution_id, plans, MANIFEST, repos_cfg, TOOLS)
    atomic_write_json(store.run_dir(execution_id) / "snapshot.json", snapshot)
    return {
        "control": control,
        "execution_id": execution_id,
        "store": store,
        "snapshot": snapshot,
    }


def _cfg(executed, action, **extra) -> dict:
    config = {
        "action": action,
        "root": str(executed["control"]),
        "execution": executed["execution_id"],
    }
    config.update(extra)
    return config


def test_prepare_returns_ordered_repos_with_base_oid(executed):
    envelope = action_prepare(_cfg(executed, "prepare"), None)
    assert envelope["ok"] is True
    assert envelope["api_version"] == "hub/v1"
    assert envelope["data"]["repos"][0]["repo_id"] == "repo-a"
    assert len(envelope["data"]["repos"][0]["base_oid"]) == 40
    assert envelope["data"]["change_id"] == "bridge-demo"


def test_gate_check_refuses_then_accepts_receipt(executed):
    from hubcoord.approvals import record_approval

    config = _cfg(executed, "gate-check", kinds=["plan"])
    with pytest.raises(HubActionError) as refused:
        action_gate_check(config, None)
    assert refused.value.output["error"]["code"] == "no-approval"

    record_approval(
        store=executed["store"],
        execution_id=executed["execution_id"],
        kind="plan",
        snapshot=executed["snapshot"],
        actor="operator",
    )
    envelope = action_gate_check(config, None)
    assert envelope["ok"] is True
    assert envelope["data"]["confirmed"][0]["kind"] == "plan"


def test_collect_summary_aggregates_layers(executed):
    envelope = action_collect_summary(_cfg(executed, "collect-summary"), None)
    assert envelope["data"]["repos"][0]["passed"] is False
    assert envelope["data"]["implementation_approved"] is False
    state = executed["store"].read_state(executed["execution_id"])
    approved = dict(state)

    def mutate(next_state: dict) -> None:
        next_state["results"] = {
            "repo-a": {
                "attempt": 1,
                "head_commit": "a" * 40,
                "result_ref": "x",
                "passed": True,
                "result_digest": "b" * 64,
            }
        }

    executed["store"].update_state(executed["execution_id"], mutate, approved["revision"])
    result_record = {
        "api_version": "hub/v1",
        "execution_id": executed["execution_id"],
        "repo_id": "repo-a",
        "attempt": 1,
        "agent": "fake",
        "head_commit": "a" * 40,
        "base_commit": "c" * 40,
        "tasks": [{"task_id": "T001", "decision": "implemented", "notes": ""}],
        "changed_paths": ["src/keep.py"],
        "result_digest": "d" * 64,
        "tests_claimed": {"status": "passed", "command": ["python", "-m", "pytest", "-q"]},
        "created_at": "2026-10-20T00:00:00Z",
    }
    results_dir = (
        executed["store"].run_dir(executed["execution_id"]) / "results" / "repo-a" / "1"
    )
    results_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(results_dir / "result.json", result_record)
    record_approval(
        store=executed["store"],
        execution_id=executed["execution_id"],
        kind="implementation",
        snapshot=executed["snapshot"],
        actor="lead",
    )
    envelope = action_collect_summary(_cfg(executed, "collect-summary"), None)
    assert envelope["data"]["repos"][0]["passed"] is True
    assert envelope["data"]["implementation_approved"] is True


def test_complete_sets_ready_for_review(executed):
    envelope = action_complete(_cfg(executed, "complete"), None)
    assert envelope["ok"] is True
    assert envelope["data"]["phase"] == "ready_for_review"
    assert envelope["data"]["archived"] is False
    assert executed["store"].read_state(executed["execution_id"])["phase"] == "ready_for_review"


@pytest.fixture
def specify_control(tmp_path, executed):
    """Initialize Specify + install the hub step shim from tooling/hubstep."""
    init = subprocess.run(
        [
            str(SPECIFY),
            "init",
            "--here",
            "--force",
            "--non-interactive",
            "--ignore-agent-tools",
        ],
        cwd=str(executed["control"]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert init.returncode == 0, init.stderr[-1500:] + init.stdout[-1500:]
    add = subprocess.run(
        [
            str(SPECIFY),
            "workflow",
            "step",
            "add",
            "hub",
            "--dev",
            str(REPO / "tooling" / "hubstep"),
        ],
        cwd=str(executed["control"]),
        capture_output=True,
        text=True,
        check=False,
    )
    assert add.returncode == 0, add.stderr[-1500:] + add.stdout[-1500:]
    return executed


@pytest.mark.skipif(not SPECIFY.is_file(), reason="pinned specify CLI not installed in .venv")
def test_installed_bridge_runs_and_finishes_ready_for_review(specify_control):
    control = specify_control["control"]
    execution_id = specify_control["execution_id"]
    store = specify_control["store"]
    record_approval(
        store=store,
        execution_id=execution_id,
        kind="plan",
        snapshot=specify_control["snapshot"],
        actor="operator",
    )
    workflow = """schema_version: "1.0"
workflow:
  id: bridge-probe
  name: Hub bridge probe
  version: "1.0.0"
inputs:
  execution: {type: string, required: true}
  control_root: {type: string, required: true}
  plan_verdict: {type: string, default: ""}
steps:
  - id: prepare
    type: hub
    action: prepare
    root: "{{ inputs.control_root }}"
    execution: "{{ inputs.execution }}"
  - id: review-gate
    type: gate
    message: "Plan review"
    options: [approve, reject]
    on_reject: abort
    verdict_input: plan_verdict
  - id: complete
    type: hub
    action: complete
    root: "{{ inputs.control_root }}"
    execution: "{{ inputs.execution }}"
"""
    wf_file = control / ".specify" / "workflows" / "bridge-probe.yaml"
    wf_file.parent.mkdir(parents=True, exist_ok=True)
    wf_file.write_text(workflow, encoding="utf-8")

    run = subprocess.run(
        [
            str(SPECIFY),
            "workflow",
            "run",
            str(wf_file),
            "--input",
            f"execution={execution_id}",
            "--input",
            f"control_root={control}",
            "--input",
            "plan_verdict=approve",
            "--json",
        ],
        cwd=str(control),
        capture_output=True,
        text=True,
        check=False,
    )
    combined = run.stdout + run.stderr
    assert run.returncode == 0, combined[-3000:]
    # engine reports completed at the final hub step; the envelope data landed
    # in the coordinator run state (output.data -> FileRunStore, pinned CLI)
    assert '"status": "completed"' in run.stdout and combined
    state = store.read_state(execution_id)
    assert state["phase"] == "ready_for_review"
