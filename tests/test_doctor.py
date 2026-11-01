"""Doctor behavior against disposable fixture wiring (specrunway/v1 model-backed)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from tests.test_manifest import manifest as sample_manifest

from specrunway import doctor, launcher
from specrunway.cli import main as specrunway_main
from specrunway.doctor import run_doctor
from specrunway.models import load_local_config


def _severities(report):
    return {f["check"]: f["severity"] for f in report["data"]["findings"]}


def _set_agent(monkeypatch, argv):
    monkeypatch.setitem(
        launcher.PROFILES,
        "primary-coding-agent",
        launcher.AgentProfile(
            name="primary-coding-agent", argv=tuple(argv), timeout_seconds=30.0
        ),
    )


def _rewrite(control, updater):
    config = control / "local.yaml"
    parsed = yaml.safe_load(config.read_text())
    parsed = updater(parsed)
    config.write_text(yaml.safe_dump(parsed))


def test_doctor_ok_on_fixture(control_workspace):
    report = run_doctor(root_dir=str(control_workspace["control"]))
    sevs = _severities(report)
    assert report["ok"] is True
    assert sevs["local-yaml"] == "ok"
    assert sevs["store.id"] == "ok"
    assert sevs["repo:repo-a"] == "ok"
    assert sevs["repo:repo-b"] == "ok"
    assert report["data"]["store"]["id"] == "fixstore"


def test_doctor_agent_preflight_reports_resolved_binary(control_workspace):
    report = run_doctor(root_dir=str(control_workspace["control"]))
    agent = report["data"]["agent"]
    assert agent["ok"] is True
    assert agent["status"] == "completed"
    assert agent["binary"] == sys.executable
    assert _severities(report)["agent-preflight"] == "ok"
    assert "agent-preflight" not in report["errors"]


def test_doctor_agent_preflight_fails_on_nonzero_exit(control_workspace, monkeypatch):
    _set_agent(monkeypatch, (sys.executable, "-c", "raise SystemExit(3)"))
    report = run_doctor(root_dir=str(control_workspace["control"]))
    assert report["ok"] is False
    assert "agent-preflight" in report["errors"]
    finding = next(
        row for row in report["data"]["findings"] if row["check"] == "agent-preflight"
    )
    assert finding["severity"] == "error"
    assert "primary-coding-agent" in finding["message"]
    assert "exit 3" in finding["message"]
    assert report["data"]["agent"]["ok"] is False
    assert report["data"]["agent"]["exit_code"] == 3


def test_doctor_agent_preflight_reports_missing_binary(control_workspace, monkeypatch):
    _set_agent(monkeypatch, ("specrunway-no-such-agent-binary",))
    report = run_doctor(root_dir=str(control_workspace["control"]))
    assert report["ok"] is False
    assert "agent-preflight" in report["errors"]
    agent = report["data"]["agent"]
    assert agent["status"] == "missing-binary"
    assert agent["binary"] is None
    finding = next(
        row for row in report["data"]["findings"] if row["check"] == "agent-preflight"
    )
    assert "specrunway-no-such-agent-binary" in finding["message"]


def test_doctor_agent_preflight_is_bounded_and_outside_repositories(
    control_workspace, monkeypatch
):
    seen = {}
    real_run_agent = launcher.run_agent

    def capture(profile, cwd, prompt_file, log_dir, **kwargs):
        seen["cwd"] = Path(cwd)
        seen["prompt"] = Path(prompt_file)
        seen["prompt_exists"] = Path(prompt_file).is_file()
        seen["timeout"] = kwargs.get("timeout_seconds")
        return real_run_agent(profile, cwd, prompt_file, log_dir, **kwargs)

    monkeypatch.setattr(launcher, "run_agent", capture)
    run_doctor(root_dir=str(control_workspace["control"]))
    business_paths = {
        Path(control_workspace["control"]),
        Path(control_workspace["store"]),
        *[Path(repo) for repo in control_workspace["repos"]],
    }
    assert seen["cwd"] not in business_paths
    assert seen["prompt_exists"] is True
    assert seen["timeout"] == doctor.AGENT_PROBE_TIMEOUT_SECONDS


def test_doctor_no_agent_probe_skips_the_launch(control_workspace, monkeypatch, capsys):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("the agent preflight must not launch with --no-agent-probe")

    monkeypatch.setattr(launcher, "run_agent", forbidden)
    rc = specrunway_main(
        [
            "doctor",
            "--root",
            str(control_workspace["control"]),
            "--no-agent-probe",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["ok"] is True
    assert "agent" not in payload["data"]
    assert all(row["check"] != "agent-preflight" for row in payload["data"]["findings"])
    # Wiring findings are unchanged from a default run.
    assert _severities(payload)["repo:repo-a"] == "ok"


def test_doctor_default_cli_still_probes(control_workspace, capsys):
    rc = specrunway_main(
        ["doctor", "--root", str(control_workspace["control"]), "--json"]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["data"]["agent"]["ok"] is True
    assert _severities(payload)["agent-preflight"] == "ok"


def test_doctor_walks_up_from_control_child(control_workspace, monkeypatch):

    child = control_workspace["control"] / ".specrunway" / "runs"
    child.mkdir(parents=True)
    monkeypatch.chdir(child)
    report = run_doctor()
    assert report["data"]["control_root"].endswith(str(control_workspace["control"]))


def test_doctor_no_control_checkout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    report = run_doctor()  # none: walk upward from cwd
    assert report["ok"] is False
    assert report["errors"] == ["no-control-checkout"]


def test_doctor_explicit_root_without_config(tmp_path):
    report = run_doctor(root_dir=str(tmp_path))
    assert report["ok"] is False
    assert "local-yaml" in report["errors"]


def test_doctor_bad_yaml(control_workspace):
    (control_workspace["control"] / "local.yaml").write_text("store: [broken")
    report = run_doctor(root_dir=str(control_workspace["control"]))
    assert report["ok"] is False
    assert "local-yaml" in report["errors"]


def test_load_local_config_missing_file():
    import pathlib

    import pytest

    with pytest.raises(FileNotFoundError):
        load_local_config(pathlib.Path("/nonexistent/control"))


def test_model_load_configurability(control_workspace):
    config = load_local_config(control_workspace["control"])
    assert config["store"]["id"] == "fixstore"


def test_doctor_missing_store_path(control_workspace):
    _rewrite(
        control_workspace["control"],
        lambda p: {
            **p,
            "store": {**p["store"], "path": str(control_workspace["root"] / "absent-store")},
        },
    )
    report = run_doctor(root_dir=str(control_workspace["control"]))
    assert "store-missing" in report["errors"]


def test_doctor_store_without_openspec_dir(control_workspace):
    import shutil

    store = control_workspace["store"]
    shutil.rmtree(store / "openspec")
    report = run_doctor(root_dir=str(control_workspace["control"]))
    assert "store-uninitialized" in report["errors"]


def test_doctor_repo_not_git_shows_code(control_workspace):
    import shutil

    shutil.rmtree(control_workspace["root"] / "repo-a" / ".git")
    report = run_doctor(root_dir=str(control_workspace["control"]))
    assert "repo-not-git" in report["errors"]


def test_doctor_missing_repo_path_is_model_error(control_workspace):
    _rewrite(
        control_workspace["control"],
        lambda p: {**p, "repos": {**p["repos"], "ghost": {"path": "relative/path"}}},
    )
    report = run_doctor(root_dir=str(control_workspace["control"]))
    assert "local-yaml" in report["errors"]
    assert report["ok"] is False


def test_doctor_wrong_remote_identity(control_workspace):
    _rewrite(
        control_workspace["control"],
        lambda p: {
            **p,
            "repos": {
                **p["repos"],
                "repo-a": {
                    **p["repos"]["repo-a"],
                    "remote_identity": "github:example.org/other-repo",
                },
            },
        },
    )
    report = run_doctor(root_dir=str(control_workspace["control"]))
    assert "wrong-checkout" in report["errors"]


def test_doctor_max_workers_over_one_rejected(control_workspace):
    _rewrite(
        control_workspace["control"],
        lambda p: {**p, "max_workers": 2},
    )
    report = run_doctor(root_dir=str(control_workspace["control"]))
    assert report["errors"] == ["local-yaml"]
    joined = " ".join(f["message"] for f in report["data"]["findings"])
    assert "not-supported-in-v1" in joined


def test_doctor_agent_profile_missing_is_model_error(control_workspace):
    _rewrite(
        control_workspace["control"],
        lambda p: {k: v for k, v in p.items() if k != "agent_profile"},
    )
    report = run_doctor(root_dir=str(control_workspace["control"]))
    assert report["ok"] is False
    assert "local-yaml" in report["errors"]


def test_manifest_samples_valid_against_models():
    from specrunway.models import validate_manifest

    assert sample_manifest() == validate_manifest(sample_manifest())


def test_doctor_validation_error_shape_shows_code(control_workspace):
    _rewrite(control_workspace["control"], lambda p: {**p, "extra_key": 1})
    report = run_doctor(root_dir=str(control_workspace["control"]))
    joined = " ".join(f["message"] for f in report["data"]["findings"])
    assert "unknown-key" in joined
