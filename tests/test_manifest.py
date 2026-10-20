"""Manifest validator tests: IDs, routing, ordering, traversal, profiles, budget."""

from __future__ import annotations

import pytest

from specrunway.models import GroupedValidationError, validate_manifest

REPO_A = {
    "repo_id": "repo-a",
    "base_ref": "main",
    "task_ids": ["T001"],
    "depends_on": [],
    "allowed_paths": ["src/", "tests/"],
    "test_profile": "api-unit",
}
REPO_B = {
    "repo_id": "repo-b",
    "base_ref": "main",
    "task_ids": ["T002"],
    "depends_on": ["repo-a"],
    "allowed_paths": ["controllers/"],
    "test_profile": "operator-unit",
}
ACCEPTANCE = [
    {"id": "AC01", "requirement": "over quota rejected", "verifies": ["T001", "T002"]}
]


def manifest(**overrides) -> dict:
    base = {
        "api_version": "specrunway/v1",
        "store_uid": "67f80512-00d1-4b0f-b5cd-3a1aad009002",
        "change_id": "add-global-rate-limit",
        "change_uid": "b7c9aeb5-0cd5-4ea5-a66e-0f3414b9a244",
        "repo_order": ["repo-a", "repo-b"],
        "repos": [dict(REPO_A), dict(REPO_B)],
        "acceptance": ACCEPTANCE,
        "integration_profile": "quota-e2e",
        "completion_policy": "merged_commits",
        "budget": {"repo_max_attempts": 3, "integration_max_repairs": 2, "total_minutes": 120},
    }
    base.update(overrides)
    return base


def test_valid_manifest_roundtrip():
    validated = validate_manifest(manifest())
    assert validated["repo_order"] == ["repo-a", "repo-b"]


@pytest.mark.parametrize(
    "field,bad,code",
    [
        ("store_uid", "not-a-uuid", "store-uid"),
        ("change_id", "X!bad", "change-id"),
        ("change_uid", "67f80512", "change-uid"),
        ("api_version", "specrunway/v2", "manifest-api-version"),
        ("integration_profile", "", "integration-profile"),
        ("completion_policy", "auto_squash", "completion-policy"),
    ],
)
def test_malformed_ids_rejected(field, bad, code):
    with pytest.raises(GroupedValidationError) as excinfo:
        validate_manifest(manifest(**{field: bad}))
    assert excinfo.value.errors[0]["code"] == code
    assert any(e["code"] == code for e in excinfo.value.errors)


def test_unknown_key_rejected():
    with pytest.raises(GroupedValidationError) as excinfo:
        validate_manifest(manifest(repos=[dict(REPO_A, extra=1), REPO_B]))
    assert any(e["code"] == "unknown-key" for e in excinfo.value.errors)


@pytest.mark.parametrize(
    "task_ids,code",
    [
        (["t001"], "task-id-format"),
        (["T001", "T001"], "task-duplicate"),
        ([], "task-routing"),
        (["T001 "], "task-id-format"),
    ],
)
def test_task_routing_rules(task_ids, code):
    with pytest.raises(GroupedValidationError) as excinfo:
        validate_manifest(manifest(repos=[dict(REPO_A, task_ids=task_ids), REPO_B]))
    assert any(e["code"] == code for e in excinfo.value.errors)


def test_cross_repo_duplicate_task_rejected():
    with pytest.raises(GroupedValidationError) as excinfo:
        validate_manifest(manifest(repos=[REPO_A, dict(REPO_B, task_ids=["T001"])]))
    assert any(e["code"] == "task-duplicate" for e in excinfo.value.errors)


@pytest.mark.parametrize(
    "paths,code",
    [
        (["../escape/"], "path-traversal"),
        (["/abs/path"], "path-traversal"),
        (["a/../../b"], "path-traversal"),
        (["src\\win"], "path-traversal"),
        ([""], "path-traversal"),
    ],
)
def test_traversal_rejected(paths, code):
    with pytest.raises(GroupedValidationError) as excinfo:
        validate_manifest(manifest(repos=[dict(REPO_A, allowed_paths=paths), REPO_B]))
    assert any(e["code"] == code for e in excinfo.value.errors)


def test_unknown_profile_rejected_when_control_declares_profiles():
    with pytest.raises(GroupedValidationError) as excinfo:
        validate_manifest(manifest(), known_profiles={"api-unit"})
    assert any(e["code"] == "unknown-profile" for e in excinfo.value.errors)


def test_unknown_profile_accepted_without_control_registry():
    validate_manifest(manifest())


def test_forward_dependency_rejected():
    with pytest.raises(GroupedValidationError) as excinfo:
        validate_manifest(
            manifest(
                repo_order=["repo-b", "repo-a"],
                repos=[dict(REPO_B), REPO_A],
            )
        )
    assert any(e["code"] == "forward-dependency" for e in excinfo.value.errors)


def test_two_node_cycle_rejected():
    with pytest.raises(GroupedValidationError) as excinfo:
        validate_manifest(
            manifest(
                repo_order=["repo-a", "repo-b"],
                repos=[dict(REPO_A, depends_on=["repo-b"]), REPO_B],
            )
        )
    assert any(e["code"] == "forward-dependency" for e in excinfo.value.errors)


def test_repo_missing_from_repo_order():
    with pytest.raises(GroupedValidationError) as excinfo:
        validate_manifest(
            manifest(
                repo_order=["repo-a"],
                repos=[REPO_A, dict(REPO_B, depends_on=[])],
            )
        )
    assert any(e["code"] == "unknown-repo" for e in excinfo.value.errors)


def test_repo_order_entry_without_repos_row():
    with pytest.raises(GroupedValidationError) as excinfo:
        validate_manifest(manifest(repo_order=["repo-a", "repo-b", "repo-c"]))
    assert any(e["code"] == "repo-missing-entry" for e in excinfo.value.errors)


def test_incomplete_task_routing_rejected():
    with pytest.raises(GroupedValidationError) as excinfo:
        validate_manifest(
            manifest(acceptance=[{"id": "AC01", "requirement": "x", "verifies": ["T001"]}])
        )
    assert any(e["code"] == "acceptance-coverage" for e in excinfo.value.errors)


def test_unmapped_acceptance_task_rejected():
    with pytest.raises(GroupedValidationError) as excinfo:
        validate_manifest(
            manifest(
                acceptance=[{"id": "AC01", "requirement": "x", "verifies": ["T001", "T999"]}]
            )
        )
    assert any(e["code"] == "task-unmapped" for e in excinfo.value.errors)


@pytest.mark.parametrize(
    "budget,code",
    [(0, "budget-range"), (-1, "budget-range"), ("3", "budget-type"), (True, "budget-type")],
)
def test_budget_rules(budget, code):
    with pytest.raises(GroupedValidationError) as excinfo:
        validate_manifest(
            manifest(
                budget={
                    "repo_max_attempts": budget,
                    "integration_max_repairs": 2,
                    "total_minutes": 120,
                }
            )
        )
    assert any(e["code"] == code for e in excinfo.value.errors)


def test_missing_completion_policy_is_accepted_and_defaults_later():
    payload = manifest()
    payload.pop("completion_policy")
    validate_manifest(payload)  # accepted; execution layer defaults to merged_commits
