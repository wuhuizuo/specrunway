"""Guided onboarding wizard: configuration, request drafting, and CLI envelope."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from specrunway.cli import main as specrunway_main
from specrunway.models.common import ValidationError
from specrunway.planning import _default_manifest
from specrunway.wizard import (
    WizardIO,
    build_manifest,
    collect_local_config,
    render_request,
    resolve_repository,
    run_wizard,
)


def _git_repo(path: Path, origin: str) -> Path:
    path.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "wizard@example.org"], cwd=path, check=True
    )
    subprocess.run(["git", "config", "user.name", "wizard"], cwd=path, check=True)
    subprocess.run(["git", "remote", "add", "origin", origin], cwd=path, check=True)
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", "init"], cwd=path, check=True
    )
    return path


class Answers:
    def __init__(self, *values: str):
        self.values = list(values)
        self.asked: list = []

    def __call__(self) -> str:
        self.asked.append(True)
        if not self.values:
            raise AssertionError("the wizard asked for more answers than scripted")
        return self.values.pop(0)


def _config_answers(repo_a: Path, repo_b: Path, store_id: str = "") -> Answers:
    return Answers(
        store_id,
        "",
        str(repo_a),
        "",
        "",
        str(repo_b),
        "",
        "",
        "",
        "",
        "",
        "",
    )


def _write_config(path: Path, repo: Path, store: Path) -> dict:
    config = {
        "store": {"id": "wiz-store", "path": str(store)},
        "repos": {"alpha": {"path": str(repo), "remote_identity": "https://x/alpha.git"}},
        "agent_profile": "primary-coding-agent",
        "max_workers": 1,
        "test_profiles": {"alpha-unit": {"command": ["python", "-m", "pytest", "-q"]}},
        "integration_profiles": {
            "specrunway-integration": {
                "command": ["python", "-m", "pytest", "-q"],
                "repo": "alpha",
            }
        },
    }
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config


def test_collect_local_config_discovers_git_wiring(tmp_path):
    control = tmp_path / "control"
    control.mkdir()
    repo_a = _git_repo(tmp_path / "repo-a", "https://example.org/acme/repo-a.git")
    repo_b = _git_repo(tmp_path / "repo-b", "git@github.com:acme/repo-b.git")
    output = io.StringIO()
    answers = _config_answers(repo_a, repo_b)
    config = collect_local_config(
        control, WizardIO(input_fn=answers, output=output)
    )

    assert config["store"] == {
        "id": "specrunway-store",
        "path": str(control / "openspec-store"),
    }
    assert list(config["repos"]) == ["repo-a", "repo-b"]
    assert config["repos"]["repo-a"]["remote_identity"] == (
        "https://example.org/acme/repo-a.git"
    )
    assert config["repos"]["repo-b"]["remote_identity"] == (
        "git@github.com:acme/repo-b.git"
    )
    assert config["test_profiles"]["repo-a-unit"]["command"] == [
        "python",
        "-m",
        "pytest",
        "-q",
    ]
    assert config["integration_profiles"]["specrunway-integration"]["repo"] == "repo-a"
    assert "Detected sibling Git checkouts" in output.getvalue()
    assert not answers.values


def test_run_wizard_creates_config_request_and_manifest(tmp_path, monkeypatch):
    control = tmp_path / "control"
    control.mkdir()
    repo_a = _git_repo(tmp_path / "repo-a", "https://example.org/acme/repo-a.git")
    repo_b = _git_repo(tmp_path / "repo-b", "https://example.org/acme/repo-b.git")
    calls: list = []

    def fake_plan(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            change_id=kwargs["change_id"],
            change_path=str(tmp_path / "store" / "openspec" / "changes" / "quota"),
            planning_complete=True,
            task_ids=["T001", "T002"],
            generated=["proposal.md", "design.md", "tasks.md"],
        )

    monkeypatch.setattr("specrunway.wizard.plan", fake_plan)
    answers = Answers(
        *_config_answers(repo_a, repo_b).values,
        "Add quota enforcement across both services",
        "",
        "",
        "",
        "",
        "Add quota enforcement",
        "",
        "",
        "Expose quota metrics",
        "",
        "",
        "",
    )
    output = io.StringIO()
    result = run_wizard(
        control,
        io=WizardIO(input_fn=answers, output=output),
        skip_init=True,
    )

    assert result["config_created"] is True
    assert result["planned"] is True
    assert result["task_ids"] == ["T001", "T002"]
    request = (control / "requests" / "add-quota-enforcement-across-both-services.md")
    assert request.is_file()
    text = request.read_text(encoding="utf-8")
    assert "## Why" in text and "## Tasks" in text
    assert "T001: Add quota enforcement" in text
    manifest = yaml.safe_load(
        (
            control
            / ".specrunway"
            / "requests"
            / "add-quota-enforcement-across-both-services.manifest.yaml"
        ).read_text(encoding="utf-8")
    )
    assert manifest["repo_order"] == ["repo-a", "repo-b"]
    assert manifest["repos"][0]["task_ids"] == ["T001"]
    assert manifest["repos"][1]["task_ids"] == ["T002"]
    assert manifest["repos"][1]["depends_on"] == ["repo-a"]
    assert manifest["integration_profile"] == "specrunway-integration"
    assert calls and calls[0]["request_path"] == request
    assert calls[0]["manifest_path"].is_file()
    assert result["next"][0].startswith("specrunway run --change ")


def test_run_wizard_reuses_existing_config_and_refuses_overwrite(tmp_path, monkeypatch):
    control = tmp_path / "control"
    control.mkdir()
    repo = _git_repo(tmp_path / "alpha", "https://example.org/acme/alpha.git")
    store = tmp_path / "store"
    config = _write_config(control / "local.yaml", repo, store)
    before = (control / "local.yaml").read_bytes()
    request_path = control / "requests" / "add-a-feature.md"
    request_path.parent.mkdir(parents=True)
    request_path.write_text("keep me\n", encoding="utf-8")

    monkeypatch.setattr("specrunway.wizard.plan", lambda **kwargs: None)
    answers = Answers(
        "Add a feature",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "n",
    )
    with pytest.raises(ValidationError) as exc_info:
        run_wizard(
            control,
            io=WizardIO(input_fn=answers, output=io.StringIO()),
            skip_init=True,
        )
    assert exc_info.value.code == "wizard-overwrite-declined"
    assert (control / "local.yaml").read_bytes() == before
    assert request_path.read_text(encoding="utf-8") == "keep me\n"
    assert config["store"]["id"] == "wiz-store"


def test_render_request_and_build_manifest_use_declared_repos(tmp_path):
    repo = _git_repo(tmp_path / "alpha", "https://example.org/acme/alpha.git")
    other = _git_repo(tmp_path / "beta", "https://example.org/acme/beta.git")
    config = {
        "store": {"id": "s", "path": str(tmp_path / "store")},
        "repos": {
            "alpha": {"path": str(repo), "remote_identity": "https://x/alpha.git"},
            "beta": {"path": str(other), "remote_identity": "https://x/beta.git"},
        },
        "test_profiles": {"alpha-unit": {"command": ["python", "-m", "pytest", "-q"]}},
        "integration_profiles": {
            "e2e": {"command": ["true"], "repo": "alpha"},
        },
    }
    tasks = {"alpha": [("T001", "first")], "beta": [("T002", "second")]}
    text = render_request(
        change_id="demo",
        why="why",
        what="what",
        context="",
        acceptance="done",
        tasks_by_repo=tasks,
    )
    assert "T001: first" in text and "T002: second" in text
    manifest = build_manifest(
        config=config,
        change_id="demo",
        tasks_by_repo=tasks,
        base_refs={"alpha": "main", "beta": "main"},
        allowed_paths={"alpha": ["src"], "beta": ["lib"]},
        depends_on={"alpha": [], "beta": ["alpha"]},
        acceptance="done",
    )
    assert manifest["repo_order"] == ["alpha", "beta"]
    assert [row["test_profile"] for row in manifest["repos"]] == ["alpha-unit", "unit"]
    assert manifest["acceptance"][0]["verifies"] == ["T001", "T002"]
    assert manifest["integration_profile"] == "e2e"


def test_build_manifest_requires_integration_profile(tmp_path):
    repo = _git_repo(tmp_path / "alpha", "https://example.org/acme/alpha.git")
    config = {
        "store": {"id": "s", "path": str(tmp_path / "store")},
        "repos": {"alpha": {"path": str(repo), "remote_identity": "https://x/alpha.git"}},
        "test_profiles": {},
        "integration_profiles": {},
    }
    with pytest.raises(ValidationError) as exc_info:
        build_manifest(
            config=config,
            change_id="demo",
            tasks_by_repo={"alpha": [("T001", "first")]},
            base_refs={"alpha": "main"},
            allowed_paths={"alpha": ["src"]},
            depends_on={"alpha": []},
            acceptance="done",
        )
    assert exc_info.value.code == "integration-profile-missing"


def test_default_manifest_uses_configured_repositories(tmp_path):
    repo_a = tmp_path / "alpha"
    repo_b = tmp_path / "beta"
    (repo_a / "src").mkdir(parents=True)
    (repo_b / "controllers").mkdir(parents=True)
    config = {
        "repos": {
            "alpha": {"path": str(repo_a), "remote_identity": "https://x/alpha.git"},
            "beta": {"path": str(repo_b), "remote_identity": "https://x/beta.git"},
        },
        "test_profiles": {"beta-unit": {"command": ["go", "test", "./..."]}},
        "integration_profiles": {"e2e": {"command": ["true"], "repo": "alpha"}},
    }

    class Adapter:
        store_path = tmp_path / "store"

    manifest = _default_manifest(
        Adapter(),
        "demo",
        ["T001", "T002"],
        config,
        {"T001": "first", "T002": "second"},
    )
    assert manifest["repo_order"] == ["alpha", "beta"]
    assert manifest["repos"][0]["repo_id"] == "alpha"
    assert manifest["repos"][0]["allowed_paths"] == ["src"]
    assert manifest["repos"][1]["test_profile"] == "beta-unit"
    assert manifest["repos"][1]["depends_on"] == ["alpha"]
    assert manifest["integration_profile"] == "e2e"


def test_resolve_repository_rejects_non_git(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(ValidationError) as exc_info:
        resolve_repository(str(plain), tmp_path)
    assert exc_info.value.code == "wizard-repo-not-git"


def test_wizard_json_uses_stderr_for_prompts(tmp_path, monkeypatch, capsys):
    control = tmp_path / "control"
    control.mkdir()
    repo = _git_repo(tmp_path / "alpha", "https://example.org/acme/alpha.git")
    _write_config(control / "local.yaml", repo, tmp_path / "store")
    monkeypatch.setattr(
        "specrunway.wizard.plan",
        lambda **kwargs: SimpleNamespace(
            change_id=kwargs["change_id"],
            change_path=str(tmp_path / "change"),
            planning_complete=True,
            task_ids=["T001"],
            generated=["proposal.md"],
        ),
    )
    answers = Answers("Add a feature", "", "", "", "", "", "", "")
    monkeypatch.setattr("builtins.input", answers)

    rc = specrunway_main(
        ["wizard", "--root", str(control), "--skip-init", "--json"]
    )
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert payload["api_version"] == "specrunway/v1"
    assert payload["action"] == "wizard"
    assert payload["data"]["planned"] is True
    assert "Change summary" in captured.err
    assert "Change summary" not in captured.out


OPENSPEC_BIN = (
    Path(__file__).resolve().parents[1]
    / "tooling"
    / "openspec"
    / "node_modules"
    / ".bin"
    / "openspec"
)
SPECIFY_BIN = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "specify"


@pytest.mark.skipif(
    not (OPENSPEC_BIN.is_file() and SPECIFY_BIN.is_file()),
    reason="pinned OpenSpec/Specify CLIs are not installed",
)
def test_wizard_real_plan_generation(tmp_path):
    import uuid

    control = tmp_path / "control"
    control.mkdir()
    repo_a = _git_repo(tmp_path / "repo-a", "https://example.org/acme/repo-a.git")
    repo_b = _git_repo(tmp_path / "repo-b", "https://example.org/acme/repo-b.git")
    store_id = f"wiz-{uuid.uuid4().hex[:8]}"
    answers = Answers(
        *_config_answers(repo_a, repo_b, store_id).values,
        "Add quota enforcement across both services",
        "",
        "",
        "",
        "",
        "Add quota enforcement",
        "",
        "",
        "Expose quota metrics",
        "",
        "",
        "",
    )
    try:
        result = run_wizard(
            control,
            io=WizardIO(input_fn=answers, output=io.StringIO()),
        )
        assert result["planned"] is True
        assert result["planning_complete"] is True
        change_path = Path(result["change_path"])
        tasks = (change_path / "tasks.md").read_text(encoding="utf-8")
        assert "[T001] Add quota enforcement" in tasks
        assert "[T002] Expose quota metrics" in tasks
        assert (change_path / "proposal.md").is_file()
        assert (change_path / "specs" / "repo-a-delivery" / "spec.md").is_file()
    finally:
        subprocess.run(
            [str(OPENSPEC_BIN), "store", "unregister", store_id, "--json"],
            capture_output=True,
            text=True,
            check=False,
        )


def test_wizard_uses_current_directory_as_new_control_root(
    tmp_path, monkeypatch, capsys
):
    control = tmp_path / "control"
    control.mkdir()
    repo_a = _git_repo(tmp_path / "repo-a", "https://example.org/acme/repo-a.git")
    repo_b = _git_repo(tmp_path / "repo-b", "https://example.org/acme/repo-b.git")
    monkeypatch.chdir(control)
    monkeypatch.setattr("builtins.input", _config_answers(repo_a, repo_b))
    rc = specrunway_main(["wizard", "--skip-init", "--skip-plan"])
    assert rc == 0
    assert (control / "local.yaml").is_file()
    assert "No local.yaml found" in capsys.readouterr().out
