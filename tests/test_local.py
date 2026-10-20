"""local.yaml validation and wiring cross-check tests (L03 task 2.2)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from specrunway.models import (
    GroupedValidationError,
    load_local_config,
    validate_checkout_wiring,
    validate_local_config,
)


def local_payload(tmp_path: Path) -> dict:
    return {
        "store": {"id": "fixstore", "path": str(tmp_path / "store")},
        "repos": {
            "repo-a": {
                "path": str(tmp_path / "repo-a"),
                "remote_identity": "github:example.org/repo-a",
            }
        },
        "agent_profile": "primary-coding-agent",
        "max_workers": 1,
    }


def test_validate_local_config_ok(tmp_path):
    validated = validate_local_config(local_payload(tmp_path))
    assert validated["agent_profile"] == "primary-coding-agent"


@pytest.mark.parametrize(
    "patch,code",
    [
        ({"store": {}}, "store-id"),
        ({"store": {"id": "x", "path": "relative/path"}}, "store-path"),
        (
            {"repos": {"BAD-ID!": {"path": "/tmp/x", "remote_identity": "github:a/b"}}},
            "repo-id-format",
        ),
        (
            {"repos": {"re": {"path": "relative/path", "remote_identity": "github:a/b"}}},
            "repo-path",
        ),
        ({"repos": {"re": {"path": "/tmp/x"}}}, "remote-identity"),
        (
            {"repos": {"re": {"path": "/tmp/x", "remote_identity": "nota Forma"}}},
            "remote-identity",
        ),
        ({"agent_profile": ""}, "agent-profile"),
        ({"max_workers": 4}, "not-supported-in-v1"),
        ({"extra_key": True}, "unknown-key"),
    ],
)
def test_local_shapes_rejected(patch, code):
    with pytest.raises(GroupedValidationError) as excinfo:
        probe = local_payload(Path("."))  # absolute paths not needed under checks
        probe.update(patch)
        validate_local_config(probe)
    assert any(e["code"] == code for e in excinfo.value.errors)


def test_load_local_config_resolves_relative_paths(tmp_path):
    control = tmp_path / "control"
    control.mkdir()
    (control / "local.yaml").write_text(
        yaml.safe_dump(
            {
                "store": {"id": "fixstore", "path": "store"},
                "repos": {"repo-a": {"path": "./repo-a", "remote_identity": "github:a/b"}},
                "agent_profile": "primary-coding-agent",
            }
        )
    )
    (control / "store").mkdir()
    (control / "repo-a").mkdir()
    config = load_local_config(control)
    assert config["store"]["path"] == str(control / "store")
    assert config["repos"]["repo-a"]["path"] == str(control / "repo-a")


def test_wiring_happy(control_workspace):
    config = {
        "store": {"id": "fixstore", "path": str(control_workspace["store"])},
        "repos": {
            "repo-a": {
                "path": str(control_workspace["repos"][0]),
                "remote_identity": "github:example.org/repo-a",
            },
            "repo-b": {
                "path": str(control_workspace["repos"][1]),
                "remote_identity": "github:example.org/repo-b",
            },
        },
    }
    assert validate_checkout_wiring(config) == []


def test_wiring_wrong_checkout_detected(control_workspace):
    import shutil

    swap = control_workspace["root"] / "other"
    swap.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=swap, check=True)
    subprocess.run(
        ["git", "config", "remote.origin.url", "https://github.com/example.org/other.git"],
        cwd=swap,
        check=True,
    )
    config = {
        "store": {"id": "fixstore", "path": str(control_workspace["store"])},
        "repos": {
            "repo-a": {"path": str(swap), "remote_identity": "github:example.org/repo-a"}
        },
    }
    errors = validate_checkout_wiring(config)
    assert [e["code"] for e in errors] == ["wrong-checkout"]
    shutil.rmtree(swap)


def test_wiring_cross_manifest(control_workspace):
    manifest = {
        "api_version": "specrunway/v1",
        "store_uid": "67f80512-00d1-4b0f-b5cd-3a1aad009002",
        "change_id": "add-global-rate-limit",
        "change_uid": "b7c9aeb5-0cd5-4ea5-a66e-0f3414b9a244",
        "repo_order": ["repo-a", "ghost"],
        "repos": [
            {
                "repo_id": "repo-a",
                "base_ref": "main",
                "task_ids": ["T001"],
                "depends_on": [],
                "allowed_paths": ["src/"],
                "test_profile": "api-unit",
            }
        ],
        "acceptance": [{"id": "AC01", "requirement": "x", "verifies": ["T001"]}],
        "integration_profile": "e2e",
    }
    config = {
        "store": {"id": "fixstore", "path": str(control_workspace["store"])},
        "repos": {
            "repo-a": {
                "path": str(control_workspace["repos"][0]),
                "remote_identity": "github:example.org/repo-a",
            }
        },
        "_manifest": manifest,
    }
    errors = validate_checkout_wiring(config)
    codes = {e["code"] for e in errors}
    assert "manifest-invalid" in codes  # ghost lacks repos entry


def test_wiring_manifest_repo_missing_local(control_workspace):

    manifest = {
        "api_version": "specrunway/v1",
        "store_uid": "67f80512-00d1-4b0f-b5cd-3a1aad009002",
        "change_id": "add-global-rate-limit",
        "change_uid": "b7c9aeb5-0cd5-4ea5-a66e-0f3414b9a244",
        "repo_order": ["repo-a", "repo-b"],
        "repos": [
            {
                "repo_id": "repo-a",
                "base_ref": "main",
                "task_ids": ["T001"],
                "depends_on": [],
                "allowed_paths": ["src/"],
                "test_profile": "p",
            },
            {
                "repo_id": "repo-b",
                "base_ref": "main",
                "task_ids": ["T002"],
                "depends_on": ["repo-a"],
                "allowed_paths": ["b/"],
                "test_profile": "p",
            },
        ],
        "acceptance": [{"id": "AC01", "requirement": "x", "verifies": ["T001", "T002"]}],
        "integration_profile": "e2e",
    }
    config = {
        "store": {"id": "fixstore", "path": str(control_workspace["store"])},
        "repos": {
            "repo-a": {
                "path": str(control_workspace["repos"][0]),
                "remote_identity": "github:example.org/repo-a",
            }
        },
        "_manifest": manifest,
    }
    errors = validate_checkout_wiring(config)
    codes = [e["code"] for e in errors]
    assert "unknown-repo" in codes  # repo-b missing from local.yaml repos
