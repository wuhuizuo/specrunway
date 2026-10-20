"""Integration contract tests for hub plan (L06 task 1.1)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import yaml

from hubcoord.cli import main as hub_main
from hubcoord.models.common import ValidationError
from hubcoord.planning import (
    crosscheck_task_routing,
    extract_task_ids,
    parse_task_texts,
)

REPO = Path(__file__).resolve().parents[1]
OPENSPEC_BIN = REPO / "tooling" / "openspec" / "node_modules" / ".bin" / "openspec"

pytestmark = pytest.mark.skipif(
    not OPENSPEC_BIN.is_file(),
    reason=f"pinned openspec CLI not found at {OPENSPEC_BIN}; run the dev toolchain install",
)

REQUEST = (
    "# why\nRate limiting spans two repos.\n\n"
    "# what\nAdd a shared quota service and operator metrics.\n\n"
    "# context\nFixture request.\n\n# goals\nSequential verified delivery.\n\n"
    "T001: Add quota enforcement.\nT002: Expose operator metrics.\n"
)


@pytest.fixture
def workspace(tmp_path):
    store_path = tmp_path / "store"
    store_path.mkdir()
    store_id = f"pl-{uuid.uuid4().hex[:8]}"
    import subprocess

    subprocess.run(
        [str(OPENSPEC_BIN), "store", "setup", store_id, "--path", str(store_path), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    control = tmp_path / "control"
    control.mkdir()
    (control / "local.yaml").write_text(
        yaml.safe_dump(
            {
                "store": {"id": store_id, "path": str(store_path)},
                "repos": {
                    "repo-a": {
                        "path": str(tmp_path / "repo-a"),
                        "remote_identity": "https://example.org/repo-a.git",
                    },
                    "repo-b": {
                        "path": str(tmp_path / "repo-b"),
                        "remote_identity": "https://example.org/repo-b.git",
                    },
                },
                "agent_profile": "primary-coding-agent",
            }
        ),
        encoding="utf-8",
    )
    request_file = tmp_path / "request.md"
    request_file.write_text(REQUEST, encoding="utf-8")
    yield control, request_file, store_id

    subprocess.run(
        [str(OPENSPEC_BIN), "store", "unregister", store_id, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )


def _manifest(tmp_path, change_id: str, store_uid: str) -> Path:
    manifest = {
        "api_version": "hub/v1",
        "store_uid": store_uid,
        "change_id": change_id,
        "change_uid": "9c3e5e4e-2c2e-4b6e-8f9c-000000000001",
        "repo_order": ["repo-a", "repo-b"],
        "repos": [
            {
                "repo_id": "repo-a",
                "base_ref": "main",
                "task_ids": ["T001"],
                "depends_on": [],
                "allowed_paths": ["src/"],
                "test_profile": "api-unit",
            },
            {
                "repo_id": "repo-b",
                "base_ref": "main",
                "task_ids": ["T002"],
                "depends_on": ["repo-a"],
                "allowed_paths": ["controllers/"],
                "test_profile": "operator-unit",
            },
        ],
        "acceptance": [
            {"id": "AC01", "requirement": "Rate limit enforced.", "verifies": ["T001", "T002"]}
        ],
        "integration_profile": "quota-e2e",
    }
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return path


def test_plan_generation_path(workspace, tmp_path):
    control, request_file, store_id = workspace
    manifest_file = _manifest(tmp_path, "gen-change", "67f80512-00d1-4b0f-b5cd-3a1aad009002")
    rc = hub_main(
        [
            "plan",
            "gen-change",
            "--store",
            store_id,
            "--root",
            str(control),
            "--request",
            str(request_file),
            "--manifest",
            str(manifest_file),
            "--json",
        ]
    )
    assert rc == 0

    change_path = control.parent / "store" / "openspec" / "changes" / "gen-change"
    tasks = (change_path / "tasks.md").read_text(encoding="utf-8")
    assert "[T001] Add quota enforcement." in tasks
    assert "[T002] Expose operator metrics." in tasks
    assert (change_path / "proposal.md").is_file()
    assert (change_path / "design.md").is_file()
    assert (change_path / "specs" / "repo-a-delivery" / "spec.md").is_file()

    plan_dir = control / ".hub" / "plans" / "gen-change"
    assert (plan_dir / "manifest.yaml").is_file()
    summary = (plan_dir / "plan-summary.json").read_text(encoding="utf-8")
    assert '"planning_complete": true' in summary


def test_plan_manual_acceptance_path(workspace):
    control, _request_file, store_id = workspace
    change_path = control.parent / "store" / "openspec" / "changes" / "manual-change"
    (change_path / "specs" / "demo-delivery").mkdir(parents=True)
    (change_path / "proposal.md").write_text(
        "# manual-change\n\n## Why\nDemo.\n\n## What Changes\nAdds a route.\n",
        encoding="utf-8",
    )
    (change_path / "design.md").write_text(
        "# Design\n\n## Approach\nManual artifacts.\n", encoding="utf-8"
    )
    (change_path / "tasks.md").write_text(
        "# Tasks\n\n## Repo: alpha\n- [ ] 1.1 [T101] Add route.\n\n"
        "## Repo: beta\n- [ ] 2.1 [T102] Export counts.\n",
        encoding="utf-8",
    )
    (change_path / "specs" / "demo-delivery" / "spec.md").write_text(
        "# demo-delivery Specification\n\n## ADDED Requirements\n\n"
        "### Requirement: Demo SHALL pass\n\nThe demo SHALL pass.\n\n"
        "#### Scenario: Demo runs\n\n- **WHEN** probed\n- **THEN** passed\n",
        encoding="utf-8",
    )

    rc = hub_main(
        ["plan", "manual-change", "--store", store_id, "--root", str(control), "--json"]
    )
    assert rc == 0

    plan_dir = control / ".hub" / "plans" / "manual-change"
    landing = yaml.safe_load((plan_dir / "manifest.yaml").read_text(encoding="utf-8"))
    found_ids = {task for repo in landing["repos"] for task in repo["task_ids"]}
    assert {"T101", "T102"} <= found_ids
    verified = {task for item in landing["acceptance"] for task in item["verifies"]}
    assert {"T101", "T102"} <= verified


def test_plan_rejects_routing_mismatch(workspace, tmp_path):
    control, request_file, store_id = workspace
    manifest_file = _manifest(
        tmp_path, "mismatch-change", "67f80512-00d1-4b0f-b5cd-3a1aad009002"
    )
    assert (
        hub_main(
            [
                "plan",
                "mismatch-change",
                "--store",
                store_id,
                "--root",
                str(control),
                "--request",
                str(request_file),
                "--manifest",
                str(manifest_file),
            ]
        )
        == 0
    )

    mismatched = tmp_path / "mismatched.yaml"
    mismatched.write_text(
        yaml.safe_dump(
            {
                "api_version": "hub/v1",
                "store_uid": "67f80512-00d1-4b0f-b5cd-3a1aad009002",
                "change_id": "mismatch-change",
                "change_uid": "9c3e5e4e-2c2e-4b6e-8f9c-000000000001",
                "repo_order": ["repo-a"],
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
                "acceptance": [{"id": "AC01", "requirement": "works.", "verifies": ["T001"]}],
                "integration_profile": "quota-e2e",
            }
        ),
        encoding="utf-8",
    )
    from hubcoord.planning import plan

    with pytest.raises(ValidationError) as exc_info:
        plan(
            control_root=control,
            store_id=store_id,
            change_id="mismatch-change",
            manifest_path=mismatched,
            openspec_bin=str(OPENSPEC_BIN),
        )
    assert exc_info.value.code == "task-routing"
    assert "T002" in str(exc_info.value)


def test_plan_requires_request_for_new_change(workspace):
    control, _request_file, store_id = workspace
    from hubcoord.planning import plan

    with pytest.raises(ValidationError) as exc_info:
        plan(
            control_root=control,
            store_id=store_id,
            change_id="blank-new",
            openspec_bin=str(OPENSPEC_BIN),
        )
    assert exc_info.value.code == "plan-request-required"


def test_plan_rejects_incomplete_existing_change_without_request(workspace):
    control, _request_file, store_id = workspace
    import subprocess

    subprocess.run(
        [str(OPENSPEC_BIN), "new", "change", "incomplete", "--store", store_id, "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    from hubcoord.planning import plan

    with pytest.raises(ValidationError) as exc_info:
        plan(
            control_root=control,
            store_id=store_id,
            change_id="incomplete",
            openspec_bin=str(OPENSPEC_BIN),
        )
    assert exc_info.value.code == "plan-incomplete"


def test_plan_rejects_unknown_store(workspace):
    control, _request_file, _store_id = workspace
    from hubcoord.planning import plan

    with pytest.raises(ValidationError) as exc_info:
        plan(
            control_root=control,
            store_id="wrong-store",
            change_id="any-change",
            openspec_bin=str(OPENSPEC_BIN),
        )
    assert exc_info.value.code == "store-unknown"


def test_crosscheck_task_routing_labeled_tasks(workspace):
    _control, _request_file, _store_id = workspace
    good = {
        "api_version": "hub/v1",
        "store_uid": "1b2e8a0e-95f7-4e9a-8a4e-7f20a34b5678",
        "change_id": "cc-good",
        "change_uid": "7d5e5e4e-2c2e-4b6e-8f9c-000000000010",
        "repo_order": ["repo-a"],
        "repos": [
            {
                "repo_id": "repo-a",
                "base_ref": "main",
                "task_ids": ["T001"],
                "depends_on": [],
                "allowed_paths": ["src/"],
                "test_profile": "a-unit",
            }
        ],
        "acceptance": [{"id": "AC01", "requirement": "x.", "verifies": ["T001"]}],
        "integration_profile": "e2e",
    }
    crosscheck_task_routing(good, ["T001"])
    bad = dict(good, repos=[dict(good["repos"][0])], acceptance=good["acceptance"])
    bad["repos"][0]["task_ids"] = ["T009"]
    with pytest.raises(ValidationError) as exc_info:
        crosscheck_task_routing(bad, ["T001"])
    assert exc_info.value.code == "task-routing"


def test_plan_routing_helpers():
    tasks_md = (
        "# Tasks\n\n## Repo: repo-a\n- [ ] 1.1 [T001] first text\n"
        "- [x] 1.2 [T002] second text\n- [ ] 2.2 no label here\n"
    )
    assert extract_task_ids(tasks_md) == ["T001", "T002"]
    request = "T077: check first\nT088 ; check second\nplain line\n"
    texts = parse_task_texts(request)
    assert texts["T077"] == "check first"
    assert texts["T088"] == "check second"
    manifest = {"repos": [{"repo_id": "repo-a", "task_ids": ["T001", "T002"]}]}
    crosscheck_task_routing(manifest, ["T001", "T002"])
    manifest = {"repos": [{"repo_id": "repo-a", "task_ids": ["T001", "T999"]}]}
    with pytest.raises(ValidationError) as exc_info:
        crosscheck_task_routing(manifest, ["T001", "T002"])
    assert exc_info.value.code == "task-routing"
