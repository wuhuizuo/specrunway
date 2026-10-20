"""Ordered two-repository execution through the installed step (L11 task 6.1)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from specrunway.checkboxes import accept_tasks
from specrunway.cli import main as specrunway_main
from specrunway.runstore import FileRunStore

REPO = Path(__file__).resolve().parents[1]
SPECIFY = REPO / ".venv" / "bin" / "specify"
FAKE_AGENT = Path(__file__).with_name("fake_agent_cli.py")
MANIFEST = {
    "api_version": "specrunway/v1",
    "store_uid": "67f80512-00d1-4b0f-b5cd-3a1aad009071",
    "change_id": "demo",
    "change_uid": "9c3e5e4e-2c2e-4b6e-8f9c-000000000071",
    "repo_order": ["repo-a", "repo-b"],
    "repos": [
        {
            "repo_id": "repo-a",
            "base_ref": "main",
            "task_ids": ["T001"],
            "depends_on": [],
            "allowed_paths": ["src/"],
            "test_profile": "unit",
        },
        {
            "repo_id": "repo-b",
            "base_ref": "main",
            "task_ids": ["T002"],
            "depends_on": ["repo-a"],
            "allowed_paths": ["src/"],
            "test_profile": "unit",
        },
    ],
    "acceptance": [
        {"id": "AC01", "requirement": "both repos work.", "verifies": ["T001", "T002"]}
    ],
    "integration_profile": "e2e",
}
TASKS_MD = (
    "# Tasks\n\n## Repo: repo-a\n- [ ] 1.1 [T001] First work item.\n\n"
    "## Repo: repo-b\n- [ ] 2.1 [T002] Second work item.\n"
)

pytestmark = pytest.mark.skipif(
    not (SPECIFY.is_file() and (REPO / "tooling" / "specrunwaystep" / "step.yml").is_file()),
    reason="pinned Specify CLI or specrunway step package is missing",
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def _make_repo(tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
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
    return repo


@pytest.fixture
def loop(tmp_path, monkeypatch):
    control = tmp_path / "control"
    (control / ".specrunway").mkdir(parents=True)
    repo_a = _make_repo(tmp_path, "repo-a")
    repo_b = _make_repo(tmp_path, "repo-b")

    store_dir = tmp_path / "store"
    change = store_dir / "openspec" / "changes" / "demo"
    (change / "specs" / "repo-a-delivery").mkdir(parents=True)
    (change / "specs" / "repo-b-delivery").mkdir(parents=True)
    (change / "proposal.md").write_text(
        "# p\n\n## Why\nw\n\n## What Changes\nx\n", encoding="utf-8"
    )
    (change / "design.md").write_text("# d\n\n## Approach\na\n", encoding="utf-8")
    (change / "tasks.md").write_text(TASKS_MD, encoding="utf-8")
    for repo_id in ("repo-a", "repo-b"):
        (change / "specs" / f"{repo_id}-delivery" / "spec.md").write_text(
            f"# {repo_id}-delivery Specification\n\n## ADDED Requirements\n\n"
            "### Requirement: Demo SHALL run\n\nIt SHALL run.\n\n"
            "#### Scenario: Go\n\n- **WHEN** ran\n- **THEN** true\n",
            encoding="utf-8",
        )

    (control / "local.yaml").write_text(
        json.dumps(
            {
                "store": {"id": "loop-store", "path": str(store_dir)},
                "repos": {
                    "repo-a": {
                        "path": str(repo_a),
                        "remote_identity": "https://example.org/repo-a.git",
                    },
                    "repo-b": {
                        "path": str(repo_b),
                        "remote_identity": "https://example.org/repo-b.git",
                    },
                },
                "agent_profile": "primary-coding-agent",
                "max_workers": 1,
            }
        ),
        encoding="utf-8",
    )
    plans = control / ".specrunway" / "plans" / "demo"
    plans.mkdir(parents=True)
    import yaml

    (plans / "manifest.yaml").write_text(yaml.safe_dump(MANIFEST), encoding="utf-8")

    # The real profile resolves `opencode` on PATH; shadow it with a
    # deterministic agent that honors the same argv shape.
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    wrapper = fake_bin / "opencode"
    wrapper.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "{FAKE_AGENT}" "$@"\n', encoding="utf-8"
    )
    wrapper.chmod(0o755)
    monkeypatch.setenv(
        "PATH", f"{fake_bin}:{Path('/usr/bin')}:{Path('/bin')}:{Path.home() / '.local' / 'bin'}"
    )

    init = subprocess.run(
        [
            str(SPECIFY),
            "init",
            "--here",
            "--force",
            "--non-interactive",
            "--ignore-agent-tools",
        ],
        cwd=str(control),
        capture_output=True,
        text=True,
        check=False,
    )
    assert init.returncode == 0, (init.stdout + init.stderr)[-3000:]
    step = subprocess.run(
        [
            str(SPECIFY),
            "workflow",
            "step",
            "add",
            "specrunway",
            "--dev",
            str(REPO / "tooling" / "specrunwaystep"),
        ],
        cwd=str(control),
        capture_output=True,
        text=True,
        check=False,
    )
    assert step.returncode == 0, (step.stdout + step.stderr)[-3000:]
    return {
        "control": control,
        "change": change,
        "repo_a": repo_a,
        "repo_b": repo_b,
    }


def test_accept_tasks_marks_only_listed_tasks():
    text = "- [ ] 1.1 [T001] one\n- [ ] 2.1 [T002] two\n"
    flipped_text, flipped = accept_tasks(text, ["T001"])
    assert flipped == ["T001"]
    assert "- [x] 1.1 [T001] one" in flipped_text
    assert "- [ ] 2.1 [T002] two" in flipped_text
    with pytest.raises(Exception) as refused:
        accept_tasks(text, ["T999"])
    assert getattr(refused.value, "code", "") == "task-unmapped"


def test_run_refuses_continue_without_approval(loop):
    # a fresh checkout has no native run and no receipts: refuse cleanly
    rc = specrunway_main(["run", "--execution", "does-not-exist", "--continue", "--json"])
    assert rc != 0


def test_two_repo_loop_reaches_ready_for_review(loop, capsys):
    control = loop["control"]
    rc = specrunway_main(
        ["run", "--change", "demo", "--root", str(control), "--json"],
    )
    out = capsys.readouterr().out
    assert rc == 0, out
    started = json.loads(out)
    execution_id = started["data"]["execution_id"]
    assert started["data"]["paused_step_id"] == "plan-gate"
    assert started["data"]["native_status"] == "paused"
    assert "- [ ]" in (loop["change"] / "tasks.md").read_text(encoding="utf-8")

    rc = specrunway_main(
        [
            "approve",
            "--execution",
            execution_id,
            "--kind",
            "plan",
            "--actor",
            "lead",
            "--root",
            str(control),
            "--json",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0, out

    rc = specrunway_main(["resume", "--execution", execution_id, "--root", str(control), "--json"])
    out = capsys.readouterr().out
    assert rc == 0, out
    implemented = json.loads(out)
    assert implemented["data"]["paused_step_id"] == "implementation-gate"

    store = FileRunStore(control / ".specrunway")
    state = store.read_state(execution_id)
    assert sorted(state["results"]) == ["repo-a", "repo-b"]
    assert state["phase"] == "awaiting_implementation_review"
    assert "- [x] 1.1 [T001]" in (loop["change"] / "tasks.md").read_text(encoding="utf-8")

    # Downstream context: repo-b saw repo-a's accepted commit.
    prompt_b = (store.run_dir(execution_id) / "prompts" / "repo-b-1.md").read_text(
        encoding="utf-8"
    )
    assert "- repo-a:" in prompt_b
    assert state["results"]["repo-a"]["head_commit"] in prompt_b

    rc = specrunway_main(
        [
            "approve",
            "--execution",
            execution_id,
            "--kind",
            "implementation",
            "--actor",
            "lead",
            "--root",
            str(control),
            "--json",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0, out

    rc = specrunway_main(
        ["run", "--execution", execution_id, "--continue", "--root", str(control), "--json"]
    )
    out = capsys.readouterr().out
    assert rc == 0, out
    finished = json.loads(out)
    assert finished["data"]["native_status"] == "completed"
    state = store.read_state(execution_id)
    assert state["phase"] == "ready_for_review"
    assert state["pending_gate"] is None
    tasks_text = (loop["change"] / "tasks.md").read_text(encoding="utf-8")
    assert "- [x] 1.1 [T001]" in tasks_text and "- [x] 2.1 [T002]" in tasks_text
    # Original checkouts never receive the implementation commits.
    assert "fake agent" not in _git(loop["repo_a"], "log", "--oneline")
    assert "fake agent" not in _git(loop["repo_b"], "log", "--oneline")
