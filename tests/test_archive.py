"""Explicit archive, completion policy, and archive reconciliation (L14)."""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from hubcoord.approvals import record_approval
from hubcoord.archive import ArchiveError, archive_execution, reconcile_pending_archive
from hubcoord.freezer import freeze_execution, new_execution_id
from hubcoord.models.common import json_digest
from hubcoord.runstore import FileRunStore, atomic_write_json
from hubcoord.worktrees import create_worktree, head_oid

REPO = Path(__file__).resolve().parents[1]
OPENSPEC = REPO / "tooling" / "openspec" / "node_modules" / ".bin" / "openspec"
TOOLS = {"openspec": "1.14.3", "spec_kit": "1.2.1", "agent_profile": "primary-coding-agent"}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def _manifest(store_uid: str, policy: str | None = None) -> dict:
    manifest = {
        "api_version": "hub/v1",
        "store_uid": store_uid,
        "change_id": "ship-demo",
        "change_uid": "9c3e5e4e-2c2e-4b6e-8f9c-000000000093",
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
    if policy:
        manifest["completion_policy"] = policy
    return manifest


@pytest.fixture
def completion(tmp_path):
    store_path = tmp_path / "store"
    store_path.mkdir()
    store_id = f"ar-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        [str(OPENSPEC), "store", "setup", store_id, "--path", str(store_path), "--json"],
        check=True,
        capture_output=True,
    )
    change = store_path / "openspec" / "changes" / "ship-demo"
    (change / "specs" / "repo-a-delivery").mkdir(parents=True)
    (change / "proposal.md").write_text(
        "# p\n\n## Why\nw\n\n## What Changes\nx\n", encoding="utf-8"
    )
    (change / "design.md").write_text("# d\n\n## Approach\na\n", encoding="utf-8")
    (change / "tasks.md").write_text("# Tasks\n\n- [x] 1.1 [T001] Ship it.\n", encoding="utf-8")
    (change / "specs" / "repo-a-delivery" / "spec.md").write_text(
        "# repo-a-delivery Specification\n\n## ADDED Requirements\n\n"
        "### Requirement: Ship SHALL run\n\nIt SHALL run.\n\n"
        "#### Scenario: Go\n\n- **WHEN** ran\n- **THEN** true\n",
        encoding="utf-8",
    )
    repo = tmp_path / "repo-a"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "src").mkdir()
    (repo / "src" / "keep.py").write_text("KEEP = 1\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_base.py").write_text(
        "def test_base():\n    assert True\n", encoding="utf-8"
    )
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
    control = tmp_path / "control"
    (control / ".hub").mkdir(parents=True)
    repos_cfg = {"repo-a": {"path": str(repo), "remote_identity": "https://e/r.git"}}
    (control / "local.yaml").write_text(
        json.dumps(
            {
                "store": {"id": store_id, "path": str(store_path)},
                "repos": repos_cfg,
                "agent_profile": "primary-coding-agent",
                "max_workers": 1,
            }
        ),
        encoding="utf-8",
    )
    execution_id = new_execution_id()
    store = FileRunStore(control / ".hub")
    store.ensure_run(execution_id, "ship-demo")
    snapshot = freeze_execution(
        execution_id,
        change,
        _manifest("67f80512-00d1-4b0f-b5cd-3a1aad009093"),
        repos_cfg,
        TOOLS,
    )
    atomic_write_json(store.run_dir(execution_id) / "snapshot.json", snapshot)

    worktree = create_worktree(
        repo, snapshot["repos"]["repo-a"]["base_oid"], store.run_dir(execution_id), "repo-a"
    )
    (worktree / "src" / "ship.py").write_text("SHIP = True\n", encoding="utf-8")
    _git(worktree, "add", "--", "src")
    _git(
        worktree,
        "-c",
        "user.name=f",
        "-c",
        "user.email=f@example.org",
        "commit",
        "-q",
        "-m",
        "ship T001",
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
        "changed_paths": ["src/ship.py"],
        "tests_claimed": {"status": "passed"},
        "created_at": "2026-10-20T00:00:00Z",
    }
    result["result_digest"] = json_digest(result)
    results_dir = store.run_dir(execution_id) / "results" / "repo-a" / "1"
    results_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(results_dir / "result.json", result)
    receipts = store.run_dir(execution_id) / "tests_receipts" / "repo-a"
    receipts.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        receipts / "1.json",
        {"status": "passed", "command": ["python", "-m", "pytest", "-q"], "exit_code": 0},
    )

    def seed(next_state: dict) -> None:
        next_state["phase"] = "ready_for_review"
        next_state["results"] = {
            "repo-a": {
                "attempt": 1,
                "head_commit": head,
                "result_ref": str(results_dir / "result.json"),
                "passed": True,
                "result_digest": result["result_digest"],
            }
        }
        next_state["verification"] = {
            "repo-a": {"repo_id": "repo-a", "status": "passed", "head_commit": head}
        }

    store.update_state(execution_id, seed, store.read_state(execution_id)["revision"])
    record_approval(
        store=store,
        execution_id=execution_id,
        kind="implementation",
        snapshot=snapshot,
        actor="lead",
    )
    yield {
        "control": control,
        "store": store,
        "store_path": store_path,
        "store_id": store_id,
        "execution_id": execution_id,
        "change": change,
        "repo": repo,
        "head": head,
        "snapshot": snapshot,
    }
    subprocess.run(
        [str(OPENSPEC), "store", "unregister", store_id, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(not OPENSPEC.is_file(), reason="pinned openspec CLI missing")
def test_archive_requires_merged_commits(completion):
    pre = {
        name: (completion["change"] / name).read_bytes()
        for name in ("proposal.md", "design.md", "tasks.md")
    }
    pre_spec = (completion["change"] / "specs" / "repo-a-delivery" / "spec.md").read_bytes()
    with pytest.raises(ArchiveError) as blocked:
        archive_execution(completion["control"], completion["execution_id"])
    assert blocked.value.code == "partial-merge"
    assert completion["change"].is_dir()

    _git(completion["repo"], "merge", "--ff-only", completion["head"])
    outcome = archive_execution(completion["control"], completion["execution_id"])
    assert outcome["archived"] is True
    assert outcome["policy"] == "merged_commits"
    assert not completion["change"].exists()
    archived = list((completion["change"].parent / "archive").glob("*-ship-demo"))
    assert archived and Path(outcome["path"]) == archived[0]
    state = completion["store"].read_state(completion["execution_id"])
    assert state["phase"] == "archived"
    backup = Path(outcome["backup_dir"], "change")
    for name, payload in pre.items():
        assert (backup / name).read_bytes() == payload
    assert (backup / "specs" / "repo-a-delivery" / "spec.md").read_bytes() == pre_spec
    assert (Path(outcome["backup_dir"]) / "before.json").is_file()
    assert (Path(outcome["backup_dir"]) / "after.json").is_file()
    # replay is refused, not re-applied
    again = archive_execution(completion["control"], completion["execution_id"])
    assert again["already_archived"] is True


@pytest.mark.skipif(not OPENSPEC.is_file(), reason="pinned openspec CLI missing")
def test_archive_blocks_stale_approval(completion):
    result_file = (
        completion["store"].run_dir(completion["execution_id"])
        / "results"
        / "repo-a"
        / "1"
        / "result.json"
    )
    record = json.loads(result_file.read_text(encoding="utf-8"))
    record["tasks"][0]["notes"] = "tampered after review"
    record["result_digest"] = json_digest(record)
    result_file.write_text(json.dumps(record), encoding="utf-8")

    def reseed(next_state: dict) -> None:
        next_state["results"]["repo-a"]["result_digest"] = record["result_digest"]

    store = completion["store"]
    execution_id = completion["execution_id"]
    store.update_state(execution_id, reseed, store.read_state(execution_id)["revision"])
    with pytest.raises(ArchiveError) as stale:
        archive_execution(completion["control"], execution_id)
    assert stale.value.code == "approval-stale"


@pytest.mark.skipif(not OPENSPEC.is_file(), reason="pinned openspec CLI missing")
def test_archive_blocks_unchecked_tasks(completion):
    tasks = completion["change"] / "tasks.md"
    tasks.write_text("# Tasks\n\n- [ ] 1.1 [T001] Ship it.\n", encoding="utf-8")
    with pytest.raises(ArchiveError) as blocked:
        archive_execution(completion["control"], completion["execution_id"])
    assert blocked.value.code == "unaccepted-code"


def test_archive_requires_not_ready_phase(completion):
    store = completion["store"]
    execution_id = completion["execution_id"]

    def reset(next_state: dict) -> None:
        next_state["phase"] = "implementing"

    store.update_state(execution_id, reset, store.read_state(execution_id)["revision"])
    with pytest.raises(ArchiveError) as blocked:
        archive_execution(completion["control"], execution_id)
    assert blocked.value.code == "not-ready"


@pytest.mark.skipif(not OPENSPEC.is_file(), reason="pinned openspec CLI missing")
def test_validated_commits_needs_explicit_confirmation(completion):
    with pytest.raises(ArchiveError) as blocked:
        archive_execution(
            completion["control"], completion["execution_id"], policy="validated_commits"
        )
    assert blocked.value.code == "confirmation-required"
    outcome = archive_execution(
        completion["control"],
        completion["execution_id"],
        policy="validated_commits",
        confirm_validated=True,
    )
    assert outcome["policy"] == "validated_commits"
    assert "merged" not in json.dumps(outcome).lower()


def test_reconcile_completed_archive_without_replay(completion):
    store = completion["store"]
    execution_id = completion["execution_id"]
    change = completion["change"]
    archived = change.parent / "archive" / "2026-10-20-ship-demo"
    change.rename(archived)
    store.write_intent(
        execution_id,
        {
            "operation_key": f"{execution_id}:archive:deadbeef",
            "kind": "archive",
            "execution_id": execution_id,
            "before": {"change_path": str(change)},
        },
    )
    outcome = reconcile_pending_archive(store, execution_id, completion["snapshot"])
    assert outcome["outcome"] == "archived"
    assert store.read_state(execution_id)["phase"] == "archived"
    ops = store.operations(execution_id)
    assert [op["status"] for op in ops if op.get("kind") == "archive"] == ["recorded"]


def test_reconcile_mixed_state_blocks(completion):
    store = completion["store"]
    execution_id = completion["execution_id"]
    change = completion["change"]
    archived = change.parent / "archive" / "2026-10-20-ship-demo"
    shutil.copytree(change, archived)
    store.write_intent(
        execution_id,
        {
            "operation_key": f"{execution_id}:archive:cafebabe",
            "kind": "archive",
            "execution_id": execution_id,
            "before": {"change_path": str(change)},
        },
    )
    with pytest.raises(ArchiveError) as blocked:
        reconcile_pending_archive(store, execution_id, completion["snapshot"])
    assert blocked.value.code == "archive-mixed"


def test_reconcile_not_applied_allows_new_attempt(completion):
    store = completion["store"]
    execution_id = completion["execution_id"]
    change = completion["change"]
    store.write_intent(
        execution_id,
        {
            "operation_key": f"{execution_id}:archive:feedface",
            "kind": "archive",
            "execution_id": execution_id,
            "before": {"change_path": str(change)},
        },
    )
    outcome = reconcile_pending_archive(store, execution_id, completion["snapshot"])
    assert outcome["outcome"] == "not-applied"
    statuses = {
        op["status"] for op in store.operations(execution_id) if op.get("kind") == "archive"
    }
    assert statuses == {"reconciled"}


def test_portable_business_payloads(completion):
    execution_id = completion["execution_id"]
    run_dir = completion["store"].run_dir(execution_id)
    approval = json.loads((run_dir / "approvals" / "implementation.json").read_text())
    for field in ("execution_id", "kind", "decision", "subject_digest", "scope", "actor"):
        assert field in approval
    blob = json.dumps(approval)
    assert "/private/" not in blob and "/var/" not in blob
    result = json.loads((run_dir / "results" / "repo-a" / "1" / "result.json").read_text())
    result_blob = json.dumps(result)
    assert "/private/" not in result_blob and "/var/" not in result_blob
    assert result["changed_paths"] == ["src/ship.py"]
    manifest = completion["snapshot"]["manifest"]
    assert all(not path.startswith("/") for path in manifest["repos"][0]["allowed_paths"])
    assert "path" not in manifest["repos"][0]
    assert str(completion["repo"]) not in json.dumps(manifest)
    assert not any(
        key in result_blob.lower() for key in ("secret", "password", "api_key", "token")
    )
