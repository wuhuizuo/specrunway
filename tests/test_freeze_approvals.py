"""Freeze + approval contract tests (L07 task 2.1)."""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import pytest
import yaml

from hubcoord.approvals import (
    GateError,
    approval_path,
    record_approval,
    require_gate,
    verify_frozen_approval,
)
from hubcoord.cli import main as hub_main
from hubcoord.freezer import (
    compute_context_digest,
    compute_planning_digest,
    freeze_execution,
    is_snapshot_immutable,
    new_execution_id,
)
from hubcoord.models.common import json_digest, strip_checkbox_markers
from hubcoord.models.records import validate_result
from hubcoord.runstore import FileRunStore, atomic_write_json

REPO = Path(__file__).resolve().parents[1]
OPENSPEC_BIN = REPO / "tooling" / "openspec" / "node_modules" / ".bin" / "openspec"

pytestmark = pytest.mark.skipif(
    not OPENSPEC_BIN.is_file(),
    reason=f"pinned openspec CLI not found at {OPENSPEC_BIN}; run the dev toolchain install",
)

TOOLS = {"openspec": "1.14.3", "spec_kit": "1.2.1", "agent_profile": "primary-coding-agent"}
TASKS_MD = (
    "# Tasks\n\n## Repo: repo-a\n- [ ] 1.1 [T001] First work item.\n\n"
    "## Repo: repo-b\n- [ ] 2.1 [T002] Second work item.\n"
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def _commit_all(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(
        repo,
        "-c",
        "user.name=fixture",
        "-c",
        "user.email=fixture@example.org",
        "commit",
        "-m",
        message,
    )


@pytest.fixture
def frozen(tmp_path):
    """Real git repos + a real store change + machine-validated manifest."""
    registry_id = f"fz-{uuid.uuid4().hex[:8]}"
    store_path = tmp_path / "store"
    store_path.mkdir()
    subprocess.run(
        [str(OPENSPEC_BIN), "store", "setup", registry_id, "--path", str(store_path), "--json"],
        capture_output=True,
        text=True,
        check=True,
    )

    control = tmp_path / "control"
    (control / ".hub").mkdir(parents=True)
    repos = {}
    for repo_id in ("repo-a", "repo-b"):
        path = tmp_path / repo_id
        path.mkdir()
        _git(path, "init", "-q")
        (path / "README.md").write_text("# fixture repo\n", encoding="utf-8")
        _commit_all(path, "init")
        (path / ".git").exists()
        repos[repo_id] = {
            "path": str(path),
            "remote_identity": f"https://example.org/{repo_id}.git",
        }
    (tmp_path / "repo-a" / "AGENTS.md").write_text(
        "# Repo rules\nKeep changes small.\n", encoding="utf-8"
    )
    (control / "local.yaml").write_text(
        yaml.safe_dump(
            {
                "store": {"id": registry_id, "path": str(store_path)},
                "repos": repos,
                "agent_profile": "primary-coding-agent",
                "max_workers": 1,
            }
        ),
        encoding="utf-8",
    )

    change_path = store_path / "openspec" / "changes" / "freeze-demo"
    (change_path / "specs" / "demo-delivery").mkdir(parents=True)
    (change_path / "proposal.md").write_text(
        "# freeze-demo\n\n## Why\nNeeded.\n\n## What Changes\nTwo tasks.\n",
        encoding="utf-8",
    )
    (change_path / "design.md").write_text(
        "# Design\n\n## Approach\nSequential.\n", encoding="utf-8"
    )
    (change_path / "tasks.md").write_text(TASKS_MD, encoding="utf-8")
    (change_path / "specs" / "demo-delivery" / "spec.md").write_text(
        "# demo-delivery Specification\n\n## ADDED Requirements\n\n"
        "### Requirement: Demo SHALL verify\n\nThe demo SHALL verify.\n\n"
        "#### Scenario: Verify runs\n\n- **WHEN** verified\n- **THEN** passes\n",
        encoding="utf-8",
    )
    manifest = {
        "api_version": "hub/v1",
        "store_uid": "67f80512-00d1-4b0f-b5cd-3a1aad009002",
        "change_id": "freeze-demo",
        "change_uid": "9c3e5e4e-2c2e-4b6e-8f9c-000000000001",
        "repo_order": ["repo-a", "repo-b"],
        "repos": [
            {
                "repo_id": "repo-a",
                "base_ref": "main",
                "task_ids": ["T001"],
                "depends_on": [],
                "allowed_paths": ["src/"],
                "test_profile": "a-unit",
            },
            {
                "repo_id": "repo-b",
                "base_ref": "main",
                "task_ids": ["T002"],
                "depends_on": ["repo-a"],
                "allowed_paths": ["controllers/"],
                "test_profile": "b-unit",
            },
        ],
        "acceptance": [{"id": "AC01", "requirement": "works.", "verifies": ["T001", "T002"]}],
        "integration_profile": "e2e",
    }

    store = FileRunStore(control / ".hub")
    execution_id = new_execution_id()
    state_dir = store.ensure_run(execution_id, "freeze-demo")
    snapshot = freeze_execution(execution_id, change_path, manifest, repos, TOOLS)
    atomic_write_json(store.run_dir(execution_id) / "snapshot.json", snapshot)
    yield {
        "store": store,
        "execution_id": execution_id,
        "snapshot": snapshot,
        "change_path": change_path,
        "repos": repos,
        "manifest": manifest,
        "control": control,
        "state_dir": state_dir,
    }

    subprocess.run(
        [str(OPENSPEC_BIN), "store", "unregister", registry_id, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )


def test_freeze_binds_digests_base_oids_and_tools(frozen):
    snapshot = frozen["snapshot"]
    assert snapshot["manifest_digest"] == json_digest(snapshot["manifest"])
    assert snapshot["planning_digest"] == compute_planning_digest(
        frozen["change_path"], frozen["manifest"]
    )
    assert snapshot["context_digest"] == compute_context_digest(
        frozen["change_path"], frozen["manifest"], frozen["repos"]
    )
    for entry in snapshot["repos"].values():
        assert len(entry["base_oid"]) == 40
        assert entry["remote_identity"].startswith("https://")
    assert snapshot["tools"] == TOOLS


def test_snapshot_immutability_ignores_created_at(frozen):
    snapshot = frozen["snapshot"]
    shifted = dict(snapshot, created_at="1999-01-01T00:00:00Z")
    assert is_snapshot_immutable(snapshot, shifted)
    drifted = dict(snapshot)
    drifted["planning_digest"] = "0" * 64
    assert not is_snapshot_immutable(snapshot, drifted)


def test_planning_digest_ignores_checkbox_markers_only(frozen):
    change_path = frozen["change_path"]
    manifest = frozen["manifest"]
    before = compute_planning_digest(change_path, manifest)

    tasks_file = change_path / "tasks.md"
    text = tasks_file.read_text(encoding="utf-8")
    tasks_file.write_text(text.replace("- [ ] 1.1", "- [x] 1.1"), encoding="utf-8")
    assert compute_planning_digest(change_path, manifest) == before
    assert "First work item." in strip_checkbox_markers(text)

    tasks_file.write_text(
        text.replace("First work item.", "First work item CHANGED."), encoding="utf-8"
    )
    after_text = tasks_file.read_text(encoding="utf-8")
    assert after_text != text
    assert compute_planning_digest(change_path, manifest) != before


def test_context_digest_changes_with_rule_drift(frozen):
    change_path = frozen["change_path"]
    manifest = frozen["manifest"]
    before = compute_context_digest(change_path, manifest, frozen["repos"])

    rules = Path(frozen["repos"]["repo-b"]["path"]) / "AGENTS.md"
    rules.write_text("# Rules\nRequire runtwice checks.\n", encoding="utf-8")
    assert compute_context_digest(change_path, manifest, frozen["repos"]) != before


def test_approve_records_self_asserted_receipt(frozen):
    store = frozen["store"]
    execution_id = frozen["execution_id"]
    record = record_approval(
        store=store,
        execution_id=execution_id,
        kind="plan",
        snapshot=frozen["snapshot"],
        actor="operator",
    )
    assert record["auth_level"] == "self_asserted"
    assert record["subject_digest"] == frozen["snapshot"]["planning_digest"]
    expected = approval_path(store.hub_root, execution_id, "plan")
    assert expected.is_file()
    state = store.read_state(execution_id)
    assert state["approvals"]["plan"]["subject_digest"] == frozen["snapshot"]["planning_digest"]

    approval = require_gate(store, execution_id, "plan")
    assert approval["kind"] == "plan"


def test_gate_refuses_injected_verdict_without_receipt(frozen):
    store = frozen["store"]
    execution_id = frozen["execution_id"]
    with pytest.raises(GateError) as missing:
        require_gate(store, execution_id, "plan")
    assert missing.value.code == "no-approval"

    record_approval(
        store=store,
        execution_id=execution_id,
        kind="plan",
        snapshot=frozen["snapshot"],
        actor="operator",
        decision="reject",
    )
    with pytest.raises(GateError) as rejected:
        require_gate(store, execution_id, "plan")
    assert rejected.value.code == "approval-rejected"

    (_file := store.run_dir(execution_id) / "approvals" / "plan.json").unlink()
    record_approval(
        store=store,
        execution_id=execution_id,
        kind="plan",
        snapshot=frozen["snapshot"],
        actor="operator",
    )
    # caller claims a different subject: the recorded receipt wins, refusal stands
    with pytest.raises(GateError) as mismatch:
        require_gate(store, execution_id, "plan", expected_subject_digest="f" * 64)
    assert mismatch.value.code == "approval-mismatch"


def test_changed_approved_input_invalidates_approval(frozen):
    store = frozen["store"]
    execution_id = frozen["execution_id"]
    record_approval(
        store=store,
        execution_id=execution_id,
        kind="plan",
        snapshot=frozen["snapshot"],
        actor="operator",
    )
    # a rule change only alters the context digest; the plan approval still binds
    verify_frozen_approval(store, execution_id, "plan", frozen["snapshot"]["planning_digest"])
    tasks_file = frozen["change_path"] / "tasks.md"
    tasks_file.write_text(
        tasks_file.read_text(encoding="utf-8").replace("First work item.", "Dangerous edit"),
        encoding="utf-8",
    )
    from hubcoord.freezer import compute_planning_digest

    recomputed = compute_planning_digest(frozen["change_path"], frozen["manifest"])
    assert recomputed != frozen["snapshot"]["planning_digest"]
    with pytest.raises(GateError) as stale:
        verify_frozen_approval(store, execution_id, "plan", recomputed)
    assert stale.value.code == "approval-stale"


def test_implementation_approval_binds_result_digest(frozen):
    from hubcoord.approvals import subject_digest_for_results

    store = frozen["store"]
    execution_id = frozen["execution_id"]
    result = validate_result(
        {
            "api_version": "hub/v1",
            "execution_id": execution_id,
            "repo_id": "repo-a",
            "attempt": 1,
            "agent": "codex",
            "head_commit": frozen["snapshot"]["repos"]["repo-a"]["base_oid"],
            "base_commit": frozen["snapshot"]["repos"]["repo-a"]["base_oid"],
            "tasks": [{"task_id": "T001", "decision": "implemented", "notes": "done"}],
            "changed_paths": ["src/mod.py"],
            "result_digest": "a" * 64,
            "tests_claimed": {"status": "passed", "command": ["pytest", "-q"]},
            "created_at": "2026-10-20T00:00:00Z",
        }
    )
    results_dir = store.run_dir(execution_id) / "results" / "repo-a" / "1"
    results_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(results_dir / "result.json", result)
    expected_subject = subject_digest_for_results(store.run_dir(execution_id))
    record = record_approval(
        store=store,
        execution_id=execution_id,
        kind="implementation",
        snapshot=frozen["snapshot"],
        actor="reviewer",
    )
    assert record["subject_digest"] == expected_subject
    assert (
        require_gate(store, execution_id, "implementation")["subject_digest"]
        == expected_subject
    )


def test_hub_approve_cli_records_and_refuses(frozen, capsys):
    control = frozen["control"]
    execution_id = frozen["execution_id"]
    rc = hub_main(
        [
            "approve",
            "--execution",
            execution_id,
            "--kind",
            "plan",
            "--actor",
            "operator",
            "--root",
            str(control),
            "--json",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert frozen["snapshot"]["planning_digest"] in out
    assert '"auth_level": "self_asserted"' in out

    # implementation kind without accepted results must refuse; JSON to stdout
    assert (
        hub_main(
            [
                "approve",
                "--execution",
                execution_id,
                "--kind",
                "implementation",
                "--actor",
                "operator",
                "--root",
                str(control),
                "--json",
            ]
        )
        == 1
    )
    out_again = capsys.readouterr().out
    assert "result-required" in out_again
