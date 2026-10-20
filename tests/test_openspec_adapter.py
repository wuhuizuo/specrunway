"""Integration contract tests against the pinned OpenSpec CLI (L04 task 3.1)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

import specrunway.openspec_adapter as adapter_module
from specrunway.openspec_adapter import OpenSpecAdapter, OpenSpecProtocolError

REPO = Path(__file__).resolve().parents[1]
OPENSPEC_BIN = REPO / "tooling" / "openspec" / "node_modules" / ".bin" / "openspec"

pytestmark = pytest.mark.skipif(
    not OPENSPEC_BIN.is_file(),
    reason=f"pinned openspec CLI not found at {OPENSPEC_BIN}; run the dev toolchain install",
)

PROPOSAL = "# Proposal\nAdapter contract probe.\n"
DESIGN = "# Design\nAdapter probe design.\n"
TASKS = "# Tasks\n\n- [ ] 1.1 Probe unchecked task with a verify step\n"
SPEC = (
    "# probe-capability Specification\n\n## ADDED Requirements\n\n"
    "### Requirement: Probe SHALL work\n\nThe probe SHALL work.\n\n"
    "#### Scenario: Probe passes\n\n- **WHEN** probed\n- **THEN** passed\n"
)
SPEC_NO_RFC = (
    "# probe-capability Specification\n\n## ADDED Requirements\n\n"
    "### Requirement: wording without rfc2119\n\nJust some words.\n"
)


@pytest.fixture
def store(tmp_path):
    store_path = tmp_path / "planning"
    store_path.mkdir()
    store_id = f"ad-{uuid.uuid4().hex[:8]}"
    adapter = OpenSpecAdapter(
        store_path=store_path, store_id=store_id, openspec_bin=str(OPENSPEC_BIN)
    )
    adapter.store_setup()
    yield adapter

    def _unregister():
        import subprocess

        subprocess.run(
            [str(OPENSPEC_BIN), "store", "unregister", store_id, "--json"],
            capture_output=True,
            text=True,
            check=False,
        )

    _unregister()


def _scaffold(change_path: Path, spec=SPEC) -> None:
    (change_path / "specs" / "probe-capability").mkdir(parents=True, exist_ok=True)
    (change_path / "proposal.md").write_text(PROPOSAL)
    (change_path / "design.md").write_text(DESIGN)
    (change_path / "tasks.md").write_text(TASKS)
    (change_path / "specs" / "probe-capability" / "spec.md").write_text(spec)


def test_full_lifecycle(store):
    created = store.new_change("probe-change")
    assert created["change_id"] == "probe-change"
    assert created["schema"] == "spec-driven"
    change_path = Path(created["change_path"])
    assert change_path.is_dir()

    planning = store.status("probe-change")
    assert planning["planning_complete"] is False
    assert planning["root"]["store_id"] == store.store_id

    _scaffold(change_path)
    planning = store.status("probe-change")
    assert planning["planning_complete"] is True
    assert planning["artifacts"]["tasks"]

    # Planning-complete is NOT implementation-complete: tasks remain unchecked.
    steps = store.instructions_apply("probe-change")
    assert steps["progress"] == {"total": 1, "complete": 0, "remaining": 1}
    assert steps["tasks"][0]["done"] is False

    verdict = store.validate("probe-change")
    assert verdict["valid"] is True and verdict["issues"] == []

    (change_path / "tasks.md").write_text(TASKS.replace("- [ ] 1.1", "- [x] 1.1"))
    steps = store.instructions_apply("probe-change")
    assert steps["progress"] == {"total": 1, "complete": 1, "remaining": 0}

    archived = store.archive("probe-change")
    assert archived["specs_updated"] is True
    assert Path(str(archived["path"])).is_dir()
    assert not change_path.exists()


def test_strict_validation_rejects_rfc2119_violation(store):
    created = store.new_change("strict-probe")
    _scaffold(Path(created["change_path"]), spec=SPEC_NO_RFC)
    issues = store.validate("strict-probe", strict=True)
    assert issues["valid"] is False
    assert any(issue["level"] == "WARNING" for issue in issues["issues"])


def test_unknown_store_reported(store, tmp_path):
    stray = OpenSpecAdapter(
        store_path=tmp_path / "planning",
        store_id="ad-does-not-exist",
        openspec_bin=str(OPENSPEC_BIN),
    )
    with pytest.raises(Exception) as excinfo:
        stray.new_change("some-change")
    combined = str(excinfo.value)
    assert "unknown_store" in combined or "no_registered_stores" in combined


def test_change_exists_surfaces(store):
    created = store.new_change("dup-probe")
    assert created["change_id"] == "dup-probe"
    with pytest.raises(Exception) as excinfo:
        store.new_change("dup-probe")
    assert "exists" in str(excinfo.value)


def test_protocol_missing_keys_rejected(store, monkeypatch):
    monkeypatch.setattr(
        adapter_module.OpenSpecAdapter,
        "_run",
        lambda self, args, expect_json=True: {"api_version": "stub-only"},
    )
    with pytest.raises(OpenSpecProtocolError):
        store.store_setup()


def test_protocol_wrong_type_rejected(store, monkeypatch):
    monkeypatch.setattr(
        adapter_module.OpenSpecAdapter,
        "_run",
        lambda self, args, expect_json=True: [1, 2],
    )
    with pytest.raises(OpenSpecProtocolError):
        store.store_setup()


def test_root_resolution_guard(store, monkeypatch):
    """status refuses payloads whose root routing points at another store."""
    stubbed = {
        "changeName": "probe-change",
        "schemaName": "spec-driven",
        "artifactPaths": {},
        "root": {"path": "/elsewhere", "source": "store", "store_id": "other-store"},
        "isPlanningComplete": False,
        "isComplete": False,
    }
    monkeypatch.setattr(
        adapter_module.OpenSpecAdapter,
        "_run",
        lambda self, args, expect_json=True: stubbed,
    )
    with pytest.raises(OpenSpecProtocolError):
        store.status("probe-change")
