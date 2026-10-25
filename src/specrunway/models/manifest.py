"""Manifest machine validation (docs/DESIGN.md §2.3, specrunway/v1 routing owner)."""

from __future__ import annotations

from specrunway.models.common import (
    ErrorCollector,
    GroupedValidationError,
    ValidationError,
    is_safe_relpath,
    is_slug,
    is_task_id,
    is_uuid,
)

SPECRUNWAY_API_VERSION = "specrunway/v1"
MANIFEST_KEYS = {
    "api_version",
    "store_uid",
    "change_id",
    "change_uid",
    "repo_order",
    "repos",
    "acceptance",
    "integration_profile",
    "completion_policy",
    "budget",
}
REPO_KEYS = {"repo_id", "base_ref", "task_ids", "depends_on", "allowed_paths", "test_profile"}
BUDGET_KEYS = {"repo_max_attempts", "integration_max_repairs", "total_minutes"}
COMPLETION_POLICIES = {"merged_commits", "validated_commits"}


def validate_manifest(manifest: dict, known_profiles: set | None = None) -> dict:
    """Validate a manifest and return it; raise on the first malformed input.

    Pass *known_profiles* (profiles declared by the control checkout) to
    reject undeclared profile names as unknown-profile.
    """
    err = ErrorCollector()
    if not isinstance(manifest, dict):
        err.fail("manifest-type", "manifest must be a mapping")
        raise GroupedValidationError(err.errors)

    err.require(
        manifest.get("api_version") == SPECRUNWAY_API_VERSION,
        "manifest-api-version",
        f"api_version must be {SPECRUNWAY_API_VERSION!r}",
    )
    unknown = set(manifest) - MANIFEST_KEYS
    err.require(not unknown, "unknown-key", f"unknown manifest keys: {sorted(unknown)}")

    err.require(
        is_uuid(manifest.get("store_uid")), "store-uid", "store_uid must be a UUID string"
    )
    err.require(
        is_slug(manifest.get("change_id")), "change-id", "change_id must be a slug string"
    )
    err.require(
        is_uuid(manifest.get("change_uid")), "change-uid", "change_uid must be a UUID string"
    )

    repo_order = manifest.get("repo_order")
    repos = manifest.get("repos")
    err.require(
        isinstance(repo_order, list) and repo_order,
        "repo-order",
        "repo_order must be a non-empty list of repository ids",
    )
    err.require(isinstance(repos, list) and repos, "repos", "repos must be a non-empty list")
    if not err.ok:
        raise GroupedValidationError(err.errors)

    order_positions: dict = {}
    for index, repo_id in enumerate(repo_order):
        err.require(
            isinstance(repo_id, str) and is_slug(repo_id),
            "repo-id-format",
            f"repo_order[{index}] must be a slug string",
        )
        if isinstance(repo_id, str) and repo_id not in order_positions:
            order_positions[repo_id] = index
    err.require(
        len(order_positions) == len(repo_order),
        "repo-order-duplicate",
        "repo_order entries must be unique",
    )

    seen_task_ids: dict = {}
    repo_ids_seen: set = set()
    for index, entry in enumerate(repos):
        err.push_base(f"repos[{index}]")
        _validate_repo_entry(entry, err, order_positions, seen_task_ids, known_profiles)
        err.pop_base()
        if isinstance(entry, dict) and isinstance(entry.get("repo_id"), str):
            repo_ids_seen.add(entry["repo_id"])

    for repo_id, position in order_positions.items():
        err.require(
            repo_id in repo_ids_seen,
            "repo-missing-entry",
            f"repo_order entry {repo_id!r} (position {position}) has no repos entry",
        )
    for index, entry in enumerate(repos):
        if not isinstance(entry, dict):
            continue
        repo_id = entry.get("repo_id")
        if isinstance(repo_id, str) and repo_id not in order_positions:
            err.push_base(f"repos[{index}]")
            err.fail("unknown-repo", f"{repo_id!r} is not declared in repo_order", stop=False)
            err.pop_base()

    if not err.ok:
        raise GroupedValidationError(err.errors)

    _validate_acceptance(manifest.get("acceptance"), seen_task_ids, err)
    integration = manifest.get("integration_profile")
    if integration is not None:
        err.require(
            isinstance(integration, str) and bool(integration.strip()),
            "integration-profile",
            "integration_profile must be a non-empty string when present",
        )
    policy = manifest.get("completion_policy", "merged_commits")
    err.require(
        isinstance(policy, str) and policy in COMPLETION_POLICIES,
        "completion-policy",
        f"completion_policy must be one of {sorted(COMPLETION_POLICIES)}",
    )
    _validate_budget(manifest.get("budget"), err)

    if not err.ok:
        raise GroupedValidationError(err.errors)
    return manifest


def _validate_repo_entry(entry, err, order_positions, seen_task_ids, known_profiles):
    base = err.base or "repos"
    if not isinstance(entry, dict):
        err.fail("repo-type", f"{base} must be a mapping")
        return
    unknown = set(entry) - REPO_KEYS
    err.require(not unknown, "unknown-key", f"{base} has unknown keys: {sorted(unknown)}")
    repo_id = entry.get("repo_id")
    err.require(
        isinstance(repo_id, str) and is_slug(repo_id),
        "repo-id-format",
        f"{base}.repo_id must be a slug string",
    )
    base_ref = entry.get("base_ref")
    err.require(
        isinstance(base_ref, str) and bool(base_ref.strip()),
        "base-ref",
        f"{base}.base_ref must be a non-empty Git ref name",
    )

    deps = entry.get("depends_on", [])
    err.require(isinstance(deps, list), "depends-on-type", f"{base}.depends_on must be a list")
    if isinstance(deps, list) and isinstance(repo_id, str) and repo_id in order_positions:
        position = order_positions[repo_id]  # type: ignore[typeddict-item]
        for dep in sorted({d for d in deps if isinstance(d, str)}):
            err.require(
                dep in order_positions,
                "unknown-dep",
                f"{base}.depends_on names undeclared repository {dep!r}",
            )
            dep_position = order_positions.get(dep)
            if dep_position is None:
                continue
            err.require(
                dep_position < position,
                "forward-dependency",
                f"{repo_id!r} depends on {dep!r} which is later in repo_order "
                "(v1 permits one-way cross-repository dependencies only)",
            )

    task_ids = entry.get("task_ids")
    err.require(
        isinstance(task_ids, list) and task_ids,
        "task-routing",
        f"{base}.task_ids must be a non-empty list",
    )
    if isinstance(task_ids, list):
        if len(task_ids) != len(set(task_ids)):
            err.require(
                False, "task-duplicate", f"{base} repeats a task id within one repository"
            )
        for task_index, task_id in enumerate(task_ids):
            field = f"{base}.task_ids[{task_index}]"
            err.require(is_task_id(task_id), "task-id-format", f"{field} must match [A-Z0-9-]+")
            if is_task_id(task_id):
                prior = seen_task_ids.get(task_id)
                err.require(
                    prior is None,
                    "task-duplicate",
                    f"{field} duplicates task {task_id!r} from {prior}",
                )
                seen_task_ids.setdefault(task_id, field)
    allowed_paths = entry.get("allowed_paths")
    err.require(
        isinstance(allowed_paths, list),
        "allowed-paths-type",
        f"{base}.allowed_paths must be a list",
    )
    if isinstance(allowed_paths, list):
        for path_index, allowed in enumerate(allowed_paths):
            err.require(
                is_safe_relpath(allowed),
                "path-traversal",
                f"{base}.allowed_paths[{path_index}] must be a relative normed path",
            )
    profile = entry.get("test_profile")
    err.require(
        isinstance(profile, str) and bool(profile.strip()),
        "test-profile",
        f"{base}.test_profile must be a non-empty string",
    )
    if known_profiles is not None:
        err.require(
            isinstance(profile, str) and profile in known_profiles,
            "unknown-profile",
            f"{base}.test_profile {profile!r} is not declared in the control checkout",
        )


def _validate_acceptance(acceptance, seen_task_ids, err):
    err.require(
        isinstance(acceptance, list) and acceptance,
        "acceptance",
        "acceptance must be a non-empty list",
    )
    if not isinstance(acceptance, list):
        return
    seen_acceptance_ids: set = set()
    verified_task_ids: set = set()
    for index, row in enumerate(acceptance):
        err.push_base(f"acceptance[{index}]")
        if not isinstance(row, dict):
            err.fail("acceptance-type", "acceptance row must be a mapping")
            err.pop_base()
            continue
        ac_id = row.get("id")
        err.require(
            isinstance(ac_id, str) and is_task_id(ac_id),
            "acceptance-id-format",
            "acceptance id must match [A-Z0-9-]+",
        )
        if isinstance(ac_id, str):
            err.require(
                ac_id not in seen_acceptance_ids,
                "acceptance-duplicate",
                f"acceptance id {ac_id!r} repeated",
            )
            seen_acceptance_ids.add(ac_id)
        requirement = row.get("requirement")
        err.require(
            isinstance(requirement, str) and bool(requirement.strip()),
            "requirement",
            "acceptance requirement must be non-empty text",
        )
        verifies = row.get("verifies")
        if not isinstance(verifies, list) or not verifies:
            err.fail("verifies", "acceptance verifies must be a non-empty list", stop=False)
        else:
            for verify_index, task_id in enumerate(verifies):
                err.require(
                    is_task_id(task_id),
                    "task-id-format",
                    f"verifies[{verify_index}] must match [A-Z0-9-]+",
                )
                if is_task_id(task_id):
                    err.require(
                        task_id in seen_task_ids,
                        "task-unmapped",
                        f"verifies[{verify_index}] references untracked task {task_id!r}",
                    )
                    verified_task_ids.add(task_id)
        err.pop_base()
    for task_id, field in sorted(seen_task_ids.items()):
        err.require(
            task_id in verified_task_ids,
            "acceptance-coverage",
            f"task {task_id!r} ({field}) is not covered by any acceptance row",
        )


def _validate_budget(budget, err):
    if budget is None:
        return
    err.require(isinstance(budget, dict), "budget-type", "budget must be a mapping")
    if not isinstance(budget, dict):
        return
    unknown = set(budget) - BUDGET_KEYS
    err.require(not unknown, "unknown-key", f"unknown budget keys: {sorted(unknown)}")
    for key in ("repo_max_attempts", "integration_max_repairs", "total_minutes"):
        value = budget.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            err.require(False, "budget-type", f"budget.{key} must be an integer")
        else:
            err.require(
                value >= (1 if key == "repo_max_attempts" else 0),
                "budget-range",
                f"budget.{key}={value} is out of range",
            )


__all__ = ["COMPLETION_POLICIES", "ValidationError", "validate_manifest"]
