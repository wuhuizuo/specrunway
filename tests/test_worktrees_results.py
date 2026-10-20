"""Worktree + trusted tests + result validation contract tests (L09 task 4.1)."""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import pytest

from specrunway.freezer import freeze_execution, new_execution_id
from specrunway.results import (
    ResultRejected,
    accept_result,
    compute_result_digest,
    persist_result,
)
from specrunway.runstore import FileRunStore, atomic_write_json
from specrunway.testprofiles import resolve_test_profile, run_test_command
from specrunway.worktrees import (
    WorktreeError,
    assert_original_preserved,
    commit_all,
    create_worktree,
    head_oid,
    original_status,
)

TOOLS = {"openspec": "1.14.3", "spec_kit": "1.2.1", "agent_profile": "primary-coding-agent"}
MANIFEST = {
    "api_version": "specrunway/v1",
    "store_uid": "67f80512-00d1-4b0f-b5cd-3a1aad009002",
    "change_id": "loop-demo",
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


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )


def _commit_all(repo: Path, message: str) -> str:
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
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture
def loop(tmp_path):
    """One git repo, a run root, and a frozen snapshot for that repo."""
    repo = tmp_path / "repo-a"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "src").mkdir()
    (repo / "src" / "mod.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (repo / "README.md").write_text("# repo\n", encoding="utf-8")
    base_oid = _commit_all(repo, "init")

    change_dir = tmp_path / "change"
    (change_dir / "specs" / "cap").mkdir(parents=True)
    (change_dir / "proposal.md").write_text(
        "# p\n\n## Why\nw\n\n## What Changes\nx\n", encoding="utf-8"
    )
    (change_dir / "design.md").write_text("# d\n\n## Approach\na\n", encoding="utf-8")
    (change_dir / "tasks.md").write_text(
        "# Tasks\n\n- [ ] 1.1 [T001] Task one.\n", encoding="utf-8"
    )
    (change_dir / "specs" / "cap" / "spec.md").write_text(
        "# cap Specification\n\n## ADDED Requirements\n\n### Requirement: R SHALL work\n\nR SHALL work.\n\n"
        "#### Scenario: S\n\n- **WHEN** s\n- **THEN** done\n",
        encoding="utf-8",
    )

    store = FileRunStore(tmp_path / "control" / ".specrunway")
    execution_id = new_execution_id()
    store.ensure_run(execution_id, "loop-demo")
    snapshot = freeze_execution(
        execution_id,
        change_dir,
        MANIFEST,
        {"repo-a": {"path": str(repo), "remote_identity": "https://example.org/repo-a.git"}},
        TOOLS,
    )
    atomic_write_json(store.run_dir(execution_id) / "snapshot.json", snapshot)
    worktree = create_worktree(repo, base_oid, store.run_dir(execution_id), "repo-a")
    return {
        "store": store,
        "execution_id": execution_id,
        "snapshot": snapshot,
        "worktree": worktree,
        "repo": repo,
        "base_oid": base_oid,
        "tmp": tmp_path,
    }


def _write_result(
    worktree: Path, execution_id: str, base_oid: str, head: str, **overrides
) -> Path:
    result = {
        "api_version": "specrunway/v1",
        "execution_id": execution_id,
        "repo_id": "repo-a",
        "attempt": 1,
        "agent": "fake-agent",
        "head_commit": head,
        "base_commit": base_oid,
        "tasks": [{"task_id": "T001", "decision": "implemented", "notes": ""}],
        "changed_paths": ["src/mod.py"],
        "result_digest": "",
        "tests_claimed": {"status": "passed", "command": ["python", "-m", "pytest", "-q"]},
        "created_at": "2026-10-20T00:00:00Z",
    }
    result.update(overrides)
    result["result_digest"] = compute_result_digest(result)
    target = worktree / "result.json"
    atomic_write_json(target, result)
    return target


def _receipt(store: FileRunStore, execution_id: str, status: str = "passed") -> dict:
    receipt = {
        "status": status,
        "exit_code": 0 if status == "passed" else 1,
        "command": ["python", "-m", "pytest", "-q"],
        "cwd": "/worktree",
        "started_at": "2026-10-20T00:00:00Z",
        "finished_at": "2026-10-20T00:00:01Z",
        "duration_seconds": 1.0,
        "log_path": f"/worktree/log-{uuid.uuid4().hex[:6]}.log",
        "reason": "",
    }
    run_dir = store.run_dir(execution_id)
    (run_dir / "tests_receipts" / "repo-a").mkdir(parents=True, exist_ok=True)
    atomic_write_json(run_dir / "tests_receipts" / "repo-a" / "1.json", receipt)
    return receipt


def test_worktree_starts_from_frozen_base_and_preserves_original(loop):
    worktree = loop["worktree"]
    # detached exactly at the frozen base commit
    assert head_oid(worktree) == loop["base_oid"]
    assert (worktree / "src" / "mod.py").is_file()
    # original checkout preserved: snapshot before + after identical, incl. untracked
    original = loop["repo"]
    (original / "untracked-note.txt").write_text("operator work in progress", encoding="utf-8")
    before = original_status(original)
    assert_original_preserved(original, before)
    assert "untracked-note.txt" in before


def test_worktree_conflict_refuses(loop):
    store = loop["store"]
    execution_id = loop["execution_id"]
    with pytest.raises(WorktreeError) as again:
        create_worktree(loop["repo"], loop["base_oid"], store.run_dir(execution_id), "repo-a")
    assert again.value.code == "worktree-exists"


def test_accepted_result_binds_commit_and_tasks(loop):
    store = loop["store"]
    execution_id = loop["execution_id"]
    worktree = loop["worktree"]
    _receipt(store, execution_id, status="passed")

    (worktree / "src" / "feat.py").write_text("def feat():\n    return 1\n", encoding="utf-8")
    head = commit_all(worktree, "feat: add feat")
    result_path = _write_result(worktree, execution_id, loop["base_oid"], head)
    accepted = accept_result(
        result_path=result_path,
        execution_id=execution_id,
        repo_id="repo-a",
        manifest=MANIFEST,
        snapshot=loop["snapshot"],
        repo_checkout=loop["repo"],
        run_dir=store.run_dir(execution_id),
    )
    target = persist_result(store.run_dir(execution_id), "repo-a", accepted)
    assert target.is_file()
    stored = (
        store.run_dir(execution_id) / "results" / "repo-a" / "1" / "result.json"
    ).read_text(encoding="utf-8")
    assert head in stored


def test_foreign_result_head_rejected(loop):
    store = loop["store"]
    execution_id = loop["execution_id"]
    _receipt(store, execution_id, status="passed")
    impossible_head = "f" * 40
    result_path = _write_result(
        loop["worktree"], execution_id, loop["base_oid"], impossible_head
    )
    with pytest.raises(ResultRejected) as exc:
        accept_result(
            result_path=result_path,
            execution_id=execution_id,
            repo_id="repo-a",
            manifest=MANIFEST,
            snapshot=loop["snapshot"],
            repo_checkout=loop["repo"],
            run_dir=store.run_dir(execution_id),
        )
    assert exc.value.code == "head-not-descendant"


def test_wrong_execution_and_untasked_result_rejected(loop):
    store = loop["store"]
    execution_id = loop["execution_id"]
    _receipt(store, execution_id, status="passed")
    head = head_oid(loop["worktree"])

    wrong_exec = _write_result(
        loop["worktree"], "00000000-0000-0000-0000-000000000009", loop["base_oid"], head
    )
    with pytest.raises(ResultRejected) as exc:
        accept_result(
            result_path=wrong_exec,
            execution_id=execution_id,
            repo_id="repo-a",
            manifest=MANIFEST,
            snapshot=loop["snapshot"],
            repo_checkout=loop["repo"],
            run_dir=store.run_dir(execution_id),
        )
    assert exc.value.code == "execution-mismatch"

    stray = _write_result(loop["worktree"], execution_id, loop["base_oid"], head)
    # overwrite with an extra task id the manifest never declared
    stray_record = {
        "api_version": "specrunway/v1",
        "execution_id": execution_id,
        "repo_id": "repo-a",
        "attempt": 1,
        "agent": "fake",
        "head_commit": head,
        "base_commit": loop["base_oid"],
        "tasks": [{"task_id": "T999", "decision": "implemented", "notes": ""}],
        "changed_paths": ["src/mod.py"],
        "tests_claimed": {"status": "passed"},
        "created_at": "2026-10-20T00:00:00Z",
    }
    stray_record["result_digest"] = compute_result_digest(stray_record)
    atomic_write_json(stray, stray_record)
    with pytest.raises(ResultRejected) as exc:
        accept_result(
            result_path=stray,
            execution_id=execution_id,
            repo_id="repo-a",
            manifest=MANIFEST,
            snapshot=loop["snapshot"],
            repo_checkout=loop["repo"],
            run_dir=store.run_dir(execution_id),
        )
    assert exc.value.code in ("task-unmapped", "base-mismatch")
    assert wrong_exec.is_file()


def test_unexpected_changed_path_rejected(loop):
    store = loop["store"]
    execution_id = loop["execution_id"]
    _receipt(store, execution_id, status="passed")
    head = head_oid(loop["worktree"])
    stranger = _write_result(
        loop["worktree"], execution_id, loop["base_oid"], head, changed_paths=["../secret"]
    )
    with pytest.raises(ResultRejected) as exc:
        accept_result(
            result_path=stranger,
            execution_id=execution_id,
            repo_id="repo-a",
            manifest=MANIFEST,
            snapshot=loop["snapshot"],
            repo_checkout=loop["repo"],
            run_dir=store.run_dir(execution_id),
        )
    # the shape validator catches the traversal before path-allowance applies
    assert "changed_paths[0] must be a relative normed path" in str(exc.value)

    outside = _write_result(
        loop["worktree"],
        execution_id,
        loop["base_oid"],
        head,
        changed_paths=["controllers/other.py"],
    )
    with pytest.raises(ResultRejected) as exc:
        accept_result(
            result_path=outside,
            execution_id=execution_id,
            repo_id="repo-a",
            manifest=MANIFEST,
            snapshot=loop["snapshot"],
            repo_checkout=loop["repo"],
            run_dir=store.run_dir(execution_id),
        )
    assert exc.value.code == "path-not-allowed"


def test_unverified_success_claim_rejected(loop):
    store = loop["store"]
    execution_id = loop["execution_id"]
    head = head_oid(loop["worktree"])
    # agent claims green tests; no trusted receipt exists at all
    scandal = _write_result(loop["worktree"], execution_id, loop["base_oid"], head)
    with pytest.raises(ResultRejected) as missing:
        accept_result(
            result_path=scandal,
            execution_id=execution_id,
            repo_id="repo-a",
            manifest=MANIFEST,
            snapshot=loop["snapshot"],
            repo_checkout=loop["repo"],
            run_dir=store.run_dir(execution_id),
        )
    assert missing.value.code == "receipt-missing"

    # the runner recorded a failure while the agent claims passed
    _receipt(store, execution_id, status="failed")
    with pytest.raises(ResultRejected) as mismatch:
        accept_result(
            result_path=scandal,
            execution_id=execution_id,
            repo_id="repo-a",
            manifest=MANIFEST,
            snapshot=loop["snapshot"],
            repo_checkout=loop["repo"],
            run_dir=store.run_dir(execution_id),
        )
    assert mismatch.value.code == "receipt-mismatch"


def test_digest_tampering_rejected(loop):
    store = loop["store"]
    execution_id = loop["execution_id"]
    _receipt(store, execution_id, status="passed")
    head = head_oid(loop["worktree"])
    result_path = _write_result(loop["worktree"], execution_id, loop["base_oid"], head)
    import json as _json

    payload = _json.loads(Path(result_path).read_text(encoding="utf-8"))
    payload["tasks"][0]["notes"] = "tampered"
    Path(result_path).write_text(_json.dumps(payload, indent=2), encoding="utf-8")
    with pytest.raises(ResultRejected) as exc:
        accept_result(
            result_path=result_path,
            execution_id=execution_id,
            repo_id="repo-a",
            manifest=MANIFEST,
            snapshot=loop["snapshot"],
            repo_checkout=loop["repo"],
            run_dir=store.run_dir(execution_id),
        )
    assert exc.value.code == "digest-mismatch"


def test_trusted_runner_runs_real_tests_and_receipt(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    profile = resolve_test_profile("unit")
    receipt = run_test_command(profile.command(), project, tmp_path / "logs" / "unit.log")
    assert receipt["status"] == "passed"
    assert receipt["exit_code"] == 0
    assert "no tests ran" not in Path(receipt["log_path"]).read_text(encoding="utf-8").lower()

    (project / "test_bad.py").write_text(
        "def test_bad():\n    assert False\n", encoding="utf-8"
    )
    failed = run_test_command(profile.command(), project, tmp_path / "logs" / "unit2.log")
    assert failed["status"] == "failed"
    assert failed["exit_code"] != 0
    with pytest.raises(Exception) as unknown:
        resolve_test_profile("nope")
    assert "unknown test profile" in str(unknown.value)
