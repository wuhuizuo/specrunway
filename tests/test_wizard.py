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
    default_store_path,
    render_request,
    resolve_repository,
    run_wizard,
    validate_store_path,
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
    return Answers(store_id, "", str(repo_a), "", str(repo_b), "", "", "")


def _single_config_answers(repo: Path, store_id: str = "") -> Answers:
    return Answers(store_id, "", str(repo), "", "", "")


def _request_answers(
    *,
    description: str,
    tasks_by_repo: list,
    participating: str = "",
    order: str = "",
    dependencies: dict | None = None,
    integration: str = "n",
    integration_command: str = "",
    integration_repo: str = "",
) -> Answers:
    dependencies = dependencies or {}
    values = [description, "", "", "", "", participating, order]
    for index, (repo_id, tasks) in enumerate(tasks_by_repo):
        values.extend([tasks, "", "", ""])
        if index:
            values.append(dependencies.get(repo_id, ""))
    values.append(integration)
    if integration == "y":
        values.extend([integration_command, integration_repo])
    return Answers(*values)


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
    assert "test_profiles" not in config
    assert "integration_profiles" not in config
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
    request_answers = _request_answers(
        description="Add quota enforcement across both services",
        tasks_by_repo=[
            ("repo-a", "Add quota enforcement"),
            ("repo-b", "Expose quota metrics"),
        ],
        dependencies={"repo-b": "repo-a"},
    )
    answers = Answers(*_config_answers(repo_a, repo_b).values, *request_answers.values)
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
    assert manifest["repos"][0]["test_profile"].endswith("-repo-a")
    assert manifest["repos"][1]["test_profile"].endswith("-repo-b")
    assert "integration_profile" not in manifest
    local = yaml.safe_load((control / "local.yaml").read_text(encoding="utf-8"))
    assert set(local["test_profiles"]) == {
        f"{result['change_id']}-repo-a",
        f"{result['change_id']}-repo-b",
    }
    assert "integration_profiles" not in local
    assert result["integration_profile"] is None
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
    request_answers = _request_answers(
        description="Add a feature",
        tasks_by_repo=[("alpha", "Add a feature")],
    )
    answers = Answers(*request_answers.values, "n")
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
        repo_order=["alpha", "beta"],
        tasks_by_repo=tasks,
        base_refs={"alpha": "main", "beta": "main"},
        allowed_paths={"alpha": ["src"], "beta": ["lib"]},
        depends_on={"alpha": [], "beta": ["alpha"]},
        acceptance="done",
        test_profile_names={"alpha": "alpha-unit", "beta": "unit"},
        integration_profile="e2e",
    )
    assert manifest["repo_order"] == ["alpha", "beta"]
    assert [row["test_profile"] for row in manifest["repos"]] == ["alpha-unit", "unit"]
    assert manifest["acceptance"][0]["verifies"] == ["T001", "T002"]
    assert manifest["integration_profile"] == "e2e"


def test_build_manifest_allows_no_integration_profile(tmp_path):
    repo = _git_repo(tmp_path / "alpha", "https://example.org/acme/alpha.git")
    config = {
        "store": {"id": "s", "path": str(tmp_path / "store")},
        "repos": {"alpha": {"path": str(repo), "remote_identity": "https://x/alpha.git"}},
        "test_profiles": {},
    }
    manifest = build_manifest(
        config=config,
        change_id="demo",
        repo_order=["alpha"],
        tasks_by_repo={"alpha": [("T001", "first")]},
        base_refs={"alpha": "main"},
        allowed_paths={"alpha": ["src"]},
        depends_on={"alpha": []},
        acceptance="done",
        test_profile_names={"alpha": "unit"},
    )
    assert "integration_profile" not in manifest


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
    answers = _request_answers(
        description="Add a feature",
        tasks_by_repo=[("alpha", "Add a feature")],
    )
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
    request_answers = _request_answers(
        description="Add quota enforcement across both services",
        tasks_by_repo=[
            ("repo-a", "Add quota enforcement"),
            ("repo-b", "Expose quota metrics"),
        ],
    )
    answers = Answers(
        *_config_answers(repo_a, repo_b, store_id).values, *request_answers.values
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


def test_run_wizard_records_optional_integration_profile(tmp_path, monkeypatch):
    control = tmp_path / "control"
    control.mkdir()
    repo = _git_repo(tmp_path / "alpha", "https://example.org/acme/alpha.git")
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
    answers = Answers(
        *_single_config_answers(repo).values,
        *_request_answers(
            description="Add an integration check",
            tasks_by_repo=[("alpha", "Add integration check")],
            integration="y",
            integration_command="python -m pytest -q",
            integration_repo="alpha",
        ).values,
    )
    result = run_wizard(
        control,
        io=WizardIO(input_fn=answers, output=io.StringIO()),
        skip_init=True,
    )
    assert result["integration_profile"] == "add-an-integration-check-integration"
    manifest = yaml.safe_load(
        (
            control
            / ".specrunway"
            / "requests"
            / "add-an-integration-check.manifest.yaml"
        ).read_text(encoding="utf-8")
    )
    assert manifest["integration_profile"] == result["integration_profile"]
    local = yaml.safe_load((control / "local.yaml").read_text(encoding="utf-8"))
    assert local["integration_profiles"][result["integration_profile"]] == {
        "command": ["python", "-m", "pytest", "-q"],
        "repo": "alpha",
    }


def test_default_manifest_omits_integration_without_profiles(tmp_path):
    repo_a = tmp_path / "alpha"
    (repo_a / "src").mkdir(parents=True)
    config = {
        "repos": {"alpha": {"path": str(repo_a), "remote_identity": "https://x/a.git"}},
        "test_profiles": {},
    }

    class Adapter:
        store_path = tmp_path / "store"

    manifest = _default_manifest(
        Adapter(), "demo", ["T001"], config, {"T001": "first"}
    )
    assert "integration_profile" not in manifest


def test_collect_change_inputs_supports_selected_subset_and_monorepo_command(tmp_path):
    from specrunway.wizard import collect_change_inputs

    alpha = _git_repo(tmp_path / "alpha", "https://example.org/acme/alpha.git")
    beta = _git_repo(tmp_path / "beta", "https://example.org/acme/beta.git")
    config = {
        "repos": {
            "alpha": {"path": str(alpha), "remote_identity": "https://x/alpha.git"},
            "beta": {"path": str(beta), "remote_identity": "https://x/beta.git"},
        }
    }
    answers = Answers(
        "beta",
        "beta",
        "Change the beta module",
        "",
        "",
        "go test ./services/beta/...",
        "n",
    )
    inputs = collect_change_inputs(
        config, "Change the beta module", WizardIO(input_fn=answers, output=io.StringIO())
    )
    assert inputs.order == ["beta"]
    assert list(inputs.tasks_by_repo) == ["beta"]
    assert inputs.depends_on == {"beta": []}
    assert inputs.test_commands == {"beta": "go test ./services/beta/..."}
    assert inputs.integration is None


def test_default_store_path_avoids_control_git_checkout(tmp_path):
    control = _git_repo(tmp_path / "control", "https://example.org/acme/control.git")
    assert default_store_path(control) == tmp_path / "control-specrunway-store"
    plain = tmp_path / "plain"
    plain.mkdir()
    assert default_store_path(plain) == plain / "openspec-store"


def test_store_path_inside_control_git_checkout_is_rejected(tmp_path):
    control = _git_repo(tmp_path / "control", "https://example.org/acme/control.git")
    with pytest.raises(ValidationError) as exc_info:
        validate_store_path(control / "openspec-store", control)
    assert exc_info.value.code == "wizard-store-inside-git"
    assert "control-specrunway-store" in str(exc_info.value)


def test_collect_local_config_rejects_nested_store_path(tmp_path):
    control = _git_repo(tmp_path / "control", "https://example.org/acme/control.git")
    answers = Answers("", str(control / "openspec-store"))
    with pytest.raises(ValidationError) as exc_info:
        collect_local_config(
            control, WizardIO(input_fn=answers, output=io.StringIO())
        )
    assert exc_info.value.code == "wizard-store-inside-git"


def test_run_wizard_rejects_existing_nested_store_config(tmp_path):
    control = _git_repo(tmp_path / "control", "https://example.org/acme/control.git")
    repo = _git_repo(tmp_path / "alpha", "https://example.org/acme/alpha.git")
    _write_config(control / "local.yaml", repo, control / "openspec-store")
    with pytest.raises(ValidationError) as exc_info:
        run_wizard(
            control,
            io=WizardIO(input_fn=Answers(), output=io.StringIO()),
            skip_init=True,
        )
    assert exc_info.value.code == "wizard-store-inside-git"
    assert "--reconfigure" in str(exc_info.value)
