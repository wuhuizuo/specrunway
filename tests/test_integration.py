"""Combined-matrix integration verification and persistent budgets (L16)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from specrunway import launcher
from specrunway.bridge.actions import (
    SpecRunwayActionError,
    action_complete,
    action_integration_round,
    action_run_repo,
    action_verify_round,
)
from specrunway.freezer import freeze_execution, new_execution_id
from specrunway.integration import resolve_integration_profile
from specrunway.models import validate_local_config
from specrunway.models.common import ValidationError
from specrunway.runstore import FileRunStore, atomic_write_json

REPO = Path(__file__).resolve().parents[1]
FAKE_AGENT = Path(__file__).with_name("fake_agent_cli.py")
TOOLS = {"openspec": "1.14.3", "spec_kit": "1.2.1", "agent_profile": "fake-agent"}
PASS = [sys.executable, "-c", "print('combined ok')"]
FAIL = [sys.executable, "-c", "import sys; sys.exit(1)"]
MARKER = [
    sys.executable,
    "-c",
    "import pathlib,sys; sys.exit(0 if pathlib.Path('src/integration_ready.py').exists() else 1)",
]


def _manifest(budget: dict | None = None) -> dict:
    manifest = {
        "api_version": "specrunway/v1",
        "store_uid": "67f80512-00d1-4b0f-b5cd-3a1aad009095",
        "change_id": "integration-demo",
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
        "integration_profile": "e2e",
    }
    if budget is not None:
        merged = {
            "repo_max_attempts": 3,
            "integration_max_repairs": 2,
            "total_minutes": 120,
        }
        merged.update(budget)
        manifest["budget"] = merged
    return manifest


@pytest.fixture
def matrix(tmp_path, monkeypatch):
    control = tmp_path / "control"
    (control / ".specrunway").mkdir(parents=True)
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
    change = store_dir / "openspec" / "changes" / "integration-demo"
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
                "store": {"id": "matrix-store", "path": str(store_dir)},
                "repos": repos_cfg,
                "agent_profile": "fake-agent",
                "max_workers": 1,
                "integration_profiles": {"e2e": {"command": PASS, "repo": "repo-a"}},
            }
        ),
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
    monkeypatch.setenv("SPECRUNWAY_FAKE_SCENARIO", "pass")
    return {"control": control, "change": change, "repos": repos_cfg, "repo": repo}


def _freeze(matrix, command: list, budget: dict | None = None):
    store = FileRunStore(matrix["control"] / ".specrunway")
    execution_id = new_execution_id()
    store.ensure_run(execution_id, "integration-demo")
    integration = {
        "profile": "e2e",
        "command": list(command),
        "cwd_repo": "repo-a",
        "timeout_seconds": 120,
    }
    snapshot = freeze_execution(
        execution_id, matrix["change"], _manifest(budget), matrix["repos"], TOOLS, integration
    )
    atomic_write_json(store.run_dir(execution_id) / "snapshot.json", snapshot)
    return store, execution_id


def _cfg(matrix, store, execution_id, action: str, **extra) -> dict:
    config = {
        "action": action,
        "root": str(matrix["control"]),
        "execution": execution_id,
    }
    config.update(extra)
    return config


def _green_repo(matrix, store, execution_id):
    action_run_repo(_cfg(matrix, store, execution_id, "run-repo", repo="repo-a"), None)
    action_verify_round(_cfg(matrix, store, execution_id, "verify-round", round=1), None)


def test_resolution_requires_a_known_profile():
    config = validate_local_config(
        {
            "store": {"id": "s", "path": "/tmp/s"},
            "repos": {"repo-a": {"path": "/tmp/r", "remote_identity": "https://e/r.git"}},
            "agent_profile": "primary-coding-agent",
            "max_workers": 1,
        }
    )
    with pytest.raises(ValidationError) as missing:
        resolve_integration_profile(config, _manifest())
    assert missing.value.code == "integration-profile-missing"


def test_resolution_rejects_unknown_repo():
    config = validate_local_config(
        {
            "store": {"id": "s", "path": "/tmp/s"},
            "repos": {"repo-a": {"path": "/tmp/r", "remote_identity": "https://e/r.git"}},
            "agent_profile": "primary-coding-agent",
            "max_workers": 1,
            "integration_profiles": {"e2e": {"command": ["true"], "repo": "repo-z"}},
        }
    )
    with pytest.raises(ValidationError) as bad:
        resolve_integration_profile(config, _manifest())
    assert bad.value.code == "integration-repo"


def test_integration_failure_blocks_completion(matrix, monkeypatch):
    store, execution_id = _freeze(matrix, FAIL, budget={"integration_max_repairs": 0})
    _green_repo(matrix, store, execution_id)
    with pytest.raises(SpecRunwayActionError) as exhausted:
        action_integration_round(_cfg(matrix, store, execution_id, "integration-round"), None)
    assert exhausted.value.output["error"]["code"] == "integration-exhausted"
    state = store.read_state(execution_id)
    assert state["phase"] == "blocked"
    assert state["integration"]["status"] == "failed"
    assert state["integration_repairs"] == 0
    with pytest.raises(SpecRunwayActionError) as blocked:
        action_complete(_cfg(matrix, store, execution_id, "complete"), None)
    assert blocked.value.output["error"]["code"] == "integration-failed"
    assert store.read_state(execution_id)["phase"] != "ready_for_review"


def test_integration_repair_passes_and_counters_persist(matrix, monkeypatch):
    store, execution_id = _freeze(matrix, MARKER)
    _green_repo(matrix, store, execution_id)
    envelope = action_integration_round(
        _cfg(matrix, store, execution_id, "integration-round"), None
    )
    assert envelope["data"]["status"] == "passed"
    assert envelope["data"]["repairs_used"] == 1
    state = store.read_state(execution_id)
    assert state["integration_repairs"] == 1
    assert state["integration_rounds"] == 2
    prompt = (store.run_dir(execution_id) / "prompts" / "repo-a-2.md").read_text(
        encoding="utf-8"
    )
    assert "## Integration failure feedback" in prompt
    action_complete(_cfg(matrix, store, execution_id, "complete"), None)
    restarted = FileRunStore(matrix["control"] / ".specrunway")
    assert restarted.read_state(execution_id)["integration_repairs"] == 1


def test_integration_no_progress_stops(matrix, monkeypatch):
    monkeypatch.setenv("SPECRUNWAY_FAKE_SCENARIO", "no-commit")
    store, execution_id = _freeze(matrix, MARKER)
    _green_repo(matrix, store, execution_id)
    with pytest.raises(SpecRunwayActionError) as stopped:
        action_integration_round(_cfg(matrix, store, execution_id, "integration-round"), None)
    assert stopped.value.output["error"]["code"] == "no-progress"
    state = store.read_state(execution_id)
    assert state["phase"] == "blocked"
    assert state["integration_repairs"] == 1


def test_complete_refuses_missing_integration(matrix):
    store, execution_id = _freeze(matrix, PASS)
    snapshot_path = store.run_dir(execution_id) / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot.pop("integration")
    atomic_write_json(snapshot_path, snapshot)
    _green_repo(matrix, store, execution_id)
    with pytest.raises(SpecRunwayActionError) as refused:
        action_complete(_cfg(matrix, store, execution_id, "complete"), None)
    assert refused.value.output["error"]["code"] == "integration-required"


def test_complete_refuses_stale_matrix(matrix):
    store, execution_id = _freeze(matrix, PASS)
    _green_repo(matrix, store, execution_id)
    action_integration_round(_cfg(matrix, store, execution_id, "integration-round"), None)
    state = store.read_state(execution_id)

    def newer_head(next_state: dict) -> None:
        next_state["results"]["repo-a"]["head_commit"] = "f" * 40
        next_state["verification"]["repo-a"]["head_commit"] = "f" * 40

    store.update_state(execution_id, newer_head, state["revision"])
    with pytest.raises(SpecRunwayActionError) as stale:
        action_complete(_cfg(matrix, store, execution_id, "complete"), None)
    assert stale.value.output["error"]["code"] == "integration-stale"
