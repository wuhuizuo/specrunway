"""Shared pytest fixtures: disposable control/Store/repo wiring."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml


def run_git(args: list, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def make_store(base: Path) -> Path:
    (base / "openspec").mkdir(parents=True)
    (base / "openspec" / "config.yaml").write_text("openspec:\n  version: 1\n")
    return base


def make_repo(base: Path, origin_url: str | None = None) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    run_git(["init", "-q"], base)
    run_git(["config", "user.email", "t@example.org"], base)
    run_git(["config", "user.name", "t"], base)
    if origin_url:
        run_git(["config", "remote.origin.url", origin_url], base)
    run_git(["commit", "-q", "--allow-empty", "-m", "init"], base)
    return base


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path / "ws"


@pytest.fixture
def control_workspace(workspace: Path) -> dict:
    """Store + two business checkouts + control checkout with valid local.yaml."""
    root = workspace
    store = make_store(root / "store")
    make_repo(root / "store")
    make_repo(root / "repo-a", "https://github.com/example.org/repo-a.git")
    make_repo(root / "repo-b", "git@github.com:example.org/repo-b.git")
    control = root / "control"
    control.mkdir()
    (control / "local.yaml").write_text(
        yaml.safe_dump(
            {
                "store": {"id": "fixstore", "path": str(store)},
                "repos": {
                    "repo-a": {
                        "path": str(root / "repo-a"),
                        "remote_identity": "github:example.org/repo-a",
                    },
                    "repo-b": {
                        "path": str(root / "repo-b"),
                        "remote_identity": "github:example.org/repo-b",
                    },
                },
                "agent_profile": "primary-coding-agent",
            }
        )
    )
    return {
        "root": root,
        "control": control,
        "store": store,
        "repos": [root / "repo-a", root / "repo-b"],
    }
