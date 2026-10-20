"""Configurable and frozen test profiles (L18)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from specrunway import launcher
from specrunway.bridge.actions import action_run_repo, action_verify_round
from specrunway.freezer import freeze_execution, new_execution_id
from specrunway.models import validate_local_config
from specrunway.models.common import GroupedValidationError, ValidationError
from specrunway.runstore import FileRunStore, atomic_write_json
from specrunway.testprofiles import (
    freeze_test_profiles,
    profile_for_repo,
    resolve_test_profile,
)

REPO = Path(__file__).resolve().parents[1]
FAKE_AGENT = Path(__file__).with_name("fake_agent_cli.py")
TOOLS = {"openspec": "1.14.3", "spec_kit": "1.2.1", "agent_profile": "fake-agent"}


def _manifest(profile: str = "sub-unit") -> dict:
    return {
        "api_version": "specrunway/v1",
        "store_uid": "67f80512-00d1-4b0f-b5cd-3a1aad009096",
        "change_id": "profiles-demo",
        "change_uid": "9c3e5e4e-2c2e-4b6e-8f9c-000000000096",
        "repo_order": ["repo-a"],
        "repos": [
            {
                "repo_id": "repo-a",
                "base_ref": "main",
                "task_ids": ["T001"],
                "depends_on": [],
                "allowed_paths": ["src/"],
                "test_profile": profile,
            }
        ],
        "acceptance": [{"id": "AC01", "requirement": "works.", "verifies": ["T001"]}],
        "integration_profile": "e2e",
    }


def _local(repo: Path) -> dict:
    return {
        "store": {"id": "profiles-store", "path": "/tmp/profiles-store"},
        "repos": {"repo-a": {"path": str(repo), "remote_identity": "https://e/r.git"}},
        "agent_profile": "fake-agent",
        "max_workers": 1,
        "test_profiles": {
            "sub-unit": {
                "command": ["python", "-m", "pytest", "-q"],
                "cwd": "sub",
            }
        },
    }


@pytest.fixture
def profiles(tmp_path, monkeypatch):
    control = tmp_path / "control"
    (control / ".specrunway").mkdir(parents=True)
    repo = tmp_path / "repo-a"
    repo.mkdir()
    subprocess.run(
        ["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True, capture_output=True
    )
    (repo / "src").mkdir()
    (repo / "src" / "keep.py").write_text("KEEP = 1\n", encoding="utf-8")
    (repo / "sub").mkdir()
    (repo / "sub" / "test_base.py").write_text(
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
    change = store_dir / "openspec" / "changes" / "profiles-demo"
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
    (control / "local.yaml").write_text(json.dumps(_local(repo)), encoding="utf-8")
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
    return {"control": control, "repo": repo, "change": change}


def _freeze(profiles, configured=None):
    store = FileRunStore(profiles["control"] / ".specrunway")
    execution_id = new_execution_id()
    store.ensure_run(execution_id, "profiles-demo")
    manifest = _manifest()
    frozen = freeze_test_profiles(
        manifest, configured or _local(profiles["repo"])["test_profiles"]
    )
    snapshot = freeze_execution(
        execution_id,
        profiles["change"],
        manifest,
        {"repo-a": {"path": str(profiles["repo"]), "remote_identity": "https://e/r.git"}},
        TOOLS,
        None,
        frozen,
    )
    atomic_write_json(store.run_dir(execution_id) / "snapshot.json", snapshot)
    return store, execution_id, snapshot


def _cfg(profiles, store, execution_id, action, **extra):
    config = {
        "action": action,
        "root": str(profiles["control"]),
        "execution": execution_id,
    }
    config.update(extra)
    return config


def test_config_rejects_unsafe_profiles():
    base = _local(Path("/tmp/repo-a"))
    for cwd in ("/abs", "../outside"):
        config = dict(base)
        config["test_profiles"] = {"sub-unit": {"command": ["true"], "cwd": cwd}}
        with pytest.raises(GroupedValidationError) as bad:
            validate_local_config(config)
        assert any(err["code"] == "test-cwd" for err in bad.value.errors)
    config = dict(base)
    config["test_profiles"] = {"sub-unit": {"command": []}}
    with pytest.raises(GroupedValidationError):
        validate_local_config(config)


def test_subdirectory_profile_runs_there(profiles):
    store, execution_id, snapshot = _freeze(profiles)
    action_run_repo(_cfg(profiles, store, execution_id, "run-repo", repo="repo-a"), None)
    envelope = action_verify_round(
        _cfg(profiles, store, execution_id, "verify-round", round=1), None
    )
    assert envelope["data"]["repos"][0]["status"] == "passed"
    receipt = json.loads(
        (store.run_dir(execution_id) / "tests_receipts" / "repo-a" / "1.json").read_text()
    )
    assert receipt["cwd"].endswith("/worktrees/repo-a/sub")
    assert snapshot["test_profiles"]["sub-unit"]["cwd"] == "sub"


def test_profile_is_frozen_after_config_change(profiles):
    store, execution_id, _snapshot = _freeze(profiles)
    local = profiles["control"] / "local.yaml"
    config = json.loads(local.read_text())
    config["test_profiles"]["sub-unit"]["command"] = [
        sys.executable,
        "-c",
        "raise SystemExit(1)",
    ]
    local.write_text(json.dumps(config), encoding="utf-8")

    action_run_repo(_cfg(profiles, store, execution_id, "run-repo", repo="repo-a"), None)
    envelope = action_verify_round(
        _cfg(profiles, store, execution_id, "verify-round", round=1), None
    )
    assert envelope["data"]["repos"][0]["status"] == "passed"


def test_unknown_profile_refuses_freeze(profiles):
    with pytest.raises(ValidationError) as unknown:
        freeze_test_profiles(_manifest("nope"), {})
    assert unknown.value.code == "unknown-profile"


def test_legacy_snapshot_falls_back_to_builtin():
    profile = profile_for_repo({}, {"repo_id": "repo-a", "task_ids": ["T001"]})
    assert profile.name == "unit"
    assert profile.command()[:2] == [sys.executable, "-m"]
    assert resolve_test_profile("unit").cwd == ""
