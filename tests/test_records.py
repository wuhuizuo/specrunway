"""snapshot/result/approval/operation record validators."""

from __future__ import annotations

import pytest

from hubcoord.models import (
    GroupedValidationError,
    json_digest,
    validate_approval,
    validate_operation,
    validate_result,
    validate_snapshot,
)
from hubcoord.models.common import sha256_bytes, strip_checkbox_markers

MANIFEST = {
    "api_version": "hub/v1",
    "store_uid": "67f80512-00d1-4b0f-b5cd-3a1aad009002",
    "change_id": "add-global-rate-limit",
    "change_uid": "b7c9aeb5-0cd5-4ea5-a66e-0f3414b9a244",
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
    "acceptance": [{"id": "AC01", "requirement": "x", "verifies": ["T001"]}],
    "integration_profile": "e2e",
}


def snapshot(**overrides) -> dict:
    base = {
        "api_version": "hub/v1",
        "execution_id": "0d1f8d02-01d4-4d5d-8df5-ecda48c01001",
        "store_uid": MANIFEST["store_uid"],
        "change_id": MANIFEST["change_id"],
        "change_uid": MANIFEST["change_uid"],
        "manifest": MANIFEST,
        "manifest_digest": json_digest(MANIFEST),
        "planning_digest": sha256_bytes(b"plan-bytes"),
        "context_digest": sha256_bytes(b"context-bytes"),
        "repos": {
            "repo-a": {
                "base_ref": "main",
                "base_oid": "0123456789012345678901234567890123456789",
                "remote_identity": "github:example.org/repo-a",
            }
        },
        "tools": {
            "openspec": "1.14.3",
            "spec_kit": "1.2.1",
            "agent_profile": "primary-coding-agent",
        },
        "created_at": "2026-10-20T00:00:00Z",
    }
    base.update(overrides)
    return base


def result(**overrides) -> dict:
    base = {
        "api_version": "hub/v1",
        "execution_id": "0d1f8d02-01d4-4d5d-8df5-ecda48c01001",
        "repo_id": "repo-a",
        "attempt": 1,
        "agent": "primary-coding-agent",
        "head_commit": "0123456789012345678901234567890123456789",
        "base_commit": "f0e1d2c3b4a59687786950413230f1e2d3c4b5a6",
        "tasks": [{"task_id": "T001", "decision": "implemented", "notes": "done"}],
        "changed_paths": ["src/ratelimit/limiter.py"],
        "result_digest": sha256_bytes(b"payload"),
        "tests_claimed": {"status": "not-run", "command": None},
        "created_at": "2026-10-20T00:00:00Z",
    }
    base["tests_claimed"] = {"status": "passed", "command": ["go", "test", "./..."]}
    base.update(overrides)
    return base


def test_snapshot_valid_and_manifest_digest_bound():
    validated = validate_snapshot(snapshot())
    assert validated["manifest_digest"] == json_digest(MANIFEST)


def test_snapshot_manifest_mutation_breaks_digest():
    mutant = {**MANIFEST, "repos": [{**MANIFEST["repos"][0], "allowed_paths": ["src/oxide/"]}]}
    tampered = snapshot(manifest=mutant)
    with pytest.raises(GroupedValidationError) as excinfo:
        validate_snapshot(tampered)
    codes = {e["code"] for e in excinfo.value.errors}
    assert "digest-mismatch" in codes


def test_snapshot_base_oid_validation():
    with pytest.raises(GroupedValidationError) as excinfo:
        validate_snapshot(
            snapshot(
                repos={
                    "repo-a": {
                        "base_ref": "main",
                        "base_oid": "xyz",
                        "remote_identity": "github:a/b",
                    }
                }
            )
        )
    assert any(e["code"] == "base-oid" for e in excinfo.value.errors)


def test_snapshot_unknown_tool_key():
    with pytest.raises(GroupedValidationError) as excinfo:
        validate_snapshot(
            snapshot(
                tools={"openspec": "1", "spec_kit": "1", "agent_profile": "x", "harness": "y"}
            )
        )
    assert any(e["code"] == "unknown-key" for e in excinfo.value.errors)


def test_result_valid():
    validate_result(result())


@pytest.mark.parametrize(
    "patch,code",
    [
        ({"repo_id": "BAD"}, "repo-id"),
        ({"attempt": 0}, "attempt"),
        ({"head_commit": "short"}, "commit-oid"),
        ({"tasks": [{"task_id": "T001", "decision": "maybe"}]}, "decision"),
        ({"tasks": [{"task_id": "t1", "decision": "implemented"}]}, "task-id-format"),
        (
            {
                "tasks": [
                    {"task_id": "T001", "decision": "implemented"},
                    {"task_id": "T001", "decision": "implemented"},
                ]
            },
            "task-duplicate",
        ),
        ({"changed_paths": ["../escape"]}, "path-traversal"),
        ({"result_digest": "SHA256-tamper"}, "digest-format"),
        ({"tests_claimed": {"status": "scores-high", "command": ["x"]}}, "test-status"),
    ],
)
def test_result_rejections(patch, code):
    with pytest.raises(GroupedValidationError) as excinfo:
        validate_result(result(**patch))
    assert any(e["code"] == code for e in excinfo.value.errors)


def test_decision_authorized_skipped_and_blocked():
    validate_result(
        result(tasks=[{"task_id": "T001", "decision": "blocked", "notes": "pending"}])
    )


def test_approval():
    validation_ok = validate_approval(
        {
            "api_version": "hub/v1",
            "kind": "plan",
            "execution_id": "0d1f8d02-01d4-4d5d-8df5-ecda48c01001",
            "decision": "approve",
            "subject_digest": sha256_bytes(b"snapshot"),
            "subject_kind": "planning_snapshot",
            "approver": "operator@example.org",
            "auth_level": "self_asserted",
            "created_at": "2026-10-20T00:00:00Z",
            "note": "",
        }
    )
    assert validation_ok["auth_level"] == "self_asserted"


def test_approval_rejects_team_auth():
    with pytest.raises(GroupedValidationError) as excinfo:
        validate_approval(
            {
                "api_version": "hub/v1",
                "kind": "plan",
                "execution_id": "0d1f8d02-01d4-4d5d-8df5-ecda48c01001",
                "decision": "approve",
                "subject_digest": sha256_bytes(b"snapshot"),
                "subject_kind": "planning_snapshot",
                "approver": "bot",
                "auth_level": "authenticated",
                "created_at": "2026-10-20T00:00:00Z",
            }
        )
    assert any(e["code"] == "auth-level" for e in excinfo.value.errors)


def test_operation_key_and_status():
    validated = validate_operation(
        {
            "api_version": "hub/v1",
            "operation_key": "0d1f8d02-01d4-4d5d-8df5-ecda48c01001:checkbox:repo-a/T001:1:deadbeef",
            "execution_id": "0d1f8d02-01d4-4d5d-8df5-ecda48c01001",
            "action": "checkbox-update",
            "scope": {"repo_id": "repo-a", "task_id": "T001", "attempt": 1},
            "intent": {"input_digest": sha256_bytes(b"tasks-md-bytes")},
            "before": {"path": "x", "digest": "…" * 0 + sha256_bytes(b"old")},
            "after": None,
            "status": "pending",
            "started_at": "2026-10-20T00:00:00Z",
        }
    )
    assert validated["status"] == "pending"


def test_operation_unknown_status():
    with pytest.raises(GroupedValidationError) as excinfo:
        validate_operation(
            {
                "api_version": "hub/v1",
                "operation_key": "k1:x",
                "execution_id": "0d1f8d02-01d4-4d5d-8df5-ecda48c01001",
                "action": "x",
                "scope": {},
                "intent": {"input_digest": sha256_bytes(b"z")},
                "status": " vielleicht",
                "started_at": "2026-10-20T00:00:00Z",
            }
        )
    assert any(e["code"] == "status" for e in excinfo.value.errors)


def test_strip_checkbox_markers():
    text = "# Tasks\n- [ ] 1.1 [T001] do it\n- [x] 1.2 [T002] done\n"
    assert "- 1.1 [T001] do it" in strip_checkbox_markers(text)
    assert "- 1.2 [T002] done" in strip_checkbox_markers(text)
    assert "[ ]" not in strip_checkbox_markers(text)
    assert "[x]" not in strip_checkbox_markers(text)
