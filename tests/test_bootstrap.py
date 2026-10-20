"""One-command bootstrap and bundled step package (L17)."""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

import pytest

import specrunway
from specrunway.cli import main as specrunway_main

REPO = Path(__file__).resolve().parents[1]
OPENSPEC = REPO / "tooling" / "openspec" / "node_modules" / ".bin" / "openspec"
SPECIFY = REPO / ".venv" / "bin" / "specify"

pytestmark = pytest.mark.skipif(
    not (OPENSPEC.is_file() and SPECIFY.is_file()),
    reason="pinned OpenSpec/Specify CLIs are not installed",
)


@pytest.fixture
def control(tmp_path):
    store_root = tmp_path / "store"
    store_id = f"boot-{uuid.uuid4().hex[:8]}"
    repo = tmp_path / "repo-a"
    repo.mkdir()
    subprocess.run(
        ["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", "https://example.org/repo-a.git"],
        check=True,
        capture_output=True,
    )
    control = tmp_path / "control"
    control.mkdir()
    (control / "local.yaml").write_text(
        json.dumps(
            {
                "store": {"id": store_id, "path": str(store_root)},
                "repos": {
                    "repo-a": {
                        "path": str(repo),
                        "remote_identity": "https://example.org/repo-a.git",
                    }
                },
                "agent_profile": "primary-coding-agent",
                "max_workers": 1,
            }
        ),
        encoding="utf-8",
    )
    yield {"control": control, "store_id": store_id}
    subprocess.run(
        [str(OPENSPEC), "store", "unregister", store_id, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )


def test_step_package_ships_with_the_distribution():
    step = Path(specrunway.__file__).parent / "step_package"
    assert (step / "step.yml").is_file()
    assert "type_key: specrunway" in (step / "step.yml").read_text(encoding="utf-8")
    assert (step / "__init__.py").is_file()


def test_init_prepares_control_and_is_idempotent(control, capsys):
    rc = specrunway_main(["init", "--root", str(control["control"]), "--json"])
    out = capsys.readouterr().out
    assert rc == 0, out
    first = json.loads(out)
    assert first["ok"] is True
    assert first["data"]["specify_initialized"] is True
    assert first["data"]["store_id"] == control["store_id"]
    assert (control["control"] / ".specify").is_dir()
    installed = (
        control["control"] / ".specify" / "workflows" / "steps" / "specrunway" / "step.yml"
    )
    assert installed.is_file()

    rc = specrunway_main(["init", "--root", str(control["control"]), "--json"])
    out = capsys.readouterr().out
    assert rc == 0, out
    second = json.loads(out)
    assert second["data"]["specify_initialized"] is False
    assert second["ok"] is True


def test_init_refuses_without_local_config(tmp_path, capsys):
    bare = tmp_path / "bare"
    bare.mkdir()
    rc = specrunway_main(["init", "--root", str(bare), "--json"])
    out = capsys.readouterr().out
    assert rc == 1
    assert json.loads(out)["error"]["code"] == "local-yaml-missing"
