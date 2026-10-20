"""Typed validators for snapshot/result/approval/receipt records (hub/v1)."""

from __future__ import annotations

from hubcoord.models.common import (
    ErrorCollector,
    GroupedValidationError,
    is_git_hex,
    is_safe_relpath,
    is_sha256_hex,
    is_slug,
    is_task_id,
    is_uuid,
    json_digest,
)
from hubcoord.models.manifest import validate_manifest

RECORD_API_VERSION = "hub/v1"

APPROVAL_KINDS = {"plan", "implementation"}
DECISIONS = {"approve", "reject"}
RESULT_DECISIONS = {"implemented", "skipped", "blocked"}
TEST_STATUSES = {"not-run", "passed", "failed", "error"}
OPERATION_STATUSES = {"pending", "recorded", "uncertain", "reconciled"}


def _base_check(payload: dict, err: ErrorCollector, keys: set, what: str) -> bool:
    if not isinstance(payload, dict):
        err.fail(f"{what}-type", f"{what} record must be a mapping")
        return False
    unknown = set(payload) - keys
    err.require(not unknown, "unknown-key", f"unknown {what} keys: {sorted(unknown)}")
    err.require(
        payload.get("api_version") == RECORD_API_VERSION,
        "api-version",
        f"api_version must be {RECORD_API_VERSION!r}",
    )
    err.require(
        is_uuid(payload.get("execution_id")), "execution-id", "execution_id must be a UUID"
    )
    return err.ok or True


def validate_snapshot(snapshot: dict) -> dict:
    """snapshot.json freezes planning bytes, base OIDs, and tool digests."""
    keys = {
        "api_version",
        "execution_id",
        "store_uid",
        "change_id",
        "change_uid",
        "manifest",
        "manifest_digest",
        "planning_digest",
        "context_digest",
        "repos",
        "tools",
        "created_at",
    }
    err = ErrorCollector()
    if not _base_check(snapshot, err, keys, "snapshot"):
        raise GroupedValidationError(err.errors)
    err.require(is_uuid(snapshot.get("store_uid")), "store-uid", "store_uid must be a UUID")
    err.require(is_slug(snapshot.get("change_id")), "change-id", "change_id must be a slug")
    err.require(is_uuid(snapshot.get("change_uid")), "change-uid", "change_uid must be a UUID")
    for digest_key in ("manifest_digest", "planning_digest", "context_digest"):
        err.require(
            is_sha256_hex(snapshot.get(digest_key)),
            "digest-format",
            f"{digest_key} must be lowercase sha256 hex",
        )
    manifest = snapshot.get("manifest")
    err.require(
        isinstance(manifest, dict), "manifest-type", "manifest must embed the frozen routing"
    )
    if isinstance(manifest, dict):
        manifest_ok = True
        try:
            validate_manifest(manifest)
        except GroupedValidationError as exc:
            err.errors.append(
                {"code": "manifest-invalid", "message": str(exc), "path": "manifest"}
            )
            manifest_ok = False
        if manifest_ok:
            err.require(
                json_digest(manifest) == snapshot.get("manifest_digest"),
                "digest-mismatch",
                "manifest_digest does not match the embedded manifest",
            )
    repos = snapshot.get("repos")
    err.require(
        isinstance(repos, dict) and repos, "snapshot-repos", "repos must be a non-empty mapping"
    )
    if isinstance(repos, dict):
        for repo_id, entry in repos.items():
            err.push_base(f"repos/{repo_id}")
            err.require(is_slug(str(repo_id)), "repo-id-format", "repository id must be a slug")
            if isinstance(entry, dict):
                err.require(
                    is_git_hex(entry.get("base_oid")),
                    "base-oid",
                    "base_oid must be a 40-hex commit id",
                )
                err.require(
                    isinstance(entry.get("base_ref"), str) and bool(entry.get("base_ref")),
                    "base-ref",
                    "base_ref must be a non-empty ref name",
                )
                remote = entry.get("remote_identity")
                err.require(
                    isinstance(remote, str) and bool(remote.strip()),
                    "remote-identity",
                    "remote_identity must be a non-empty string",
                )
                bugs = {
                    k for k in entry if k not in {"base_ref", "base_oid", "remote_identity"}
                }
                err.require(not bugs, "unknown-key", f"unknown repository keys: {sorted(bugs)}")
            else:
                err.fail("repo-entry-type", "repository entry must be a mapping")
            err.pop_base()
    tools = snapshot.get("tools")
    err.require(isinstance(tools, dict), "tools-type", "tools must be a mapping")
    if isinstance(tools, dict):
        tool_unknown = set(tools) - {"openspec", "spec_kit", "agent_profile"}
        err.require(
            not tool_unknown, "unknown-key", f"unknown tools keys: {sorted(tool_unknown)}"
        )
        for tool_key in ("openspec", "spec_kit", "agent_profile"):
            err.require(
                isinstance(tools.get(tool_key), str) and bool(tools.get(tool_key).strip()),
                "tool-version",
                f"tools.{tool_key} must be a non-empty version string",
            )
    err.require(
        isinstance(snapshot.get("created_at"), str)
        and bool(snapshot.get("created_at").strip()),
        "timestamp",
        "created_at must be an RFC 3339 timestamp string",
    )
    if err.errors:
        raise GroupedValidationError(err.errors)
    return snapshot


def validate_result(result: dict) -> dict:
    """result.json is untrusted agent output; only shape/identity are checked."""
    keys = {
        "api_version",
        "execution_id",
        "repo_id",
        "attempt",
        "agent",
        "head_commit",
        "base_commit",
        "tasks",
        "changed_paths",
        "result_digest",
        "tests_claimed",
        "created_at",
    }
    err = ErrorCollector()
    if not _base_check(result, err, keys, "result"):
        raise GroupedValidationError(err.errors)
    err.require(is_slug(result.get("repo_id")), "repo-id", "repo_id must be a slug")
    attempt = result.get("attempt")
    err.require(
        isinstance(attempt, int) and not isinstance(attempt, bool) and attempt >= 1,
        "attempt",
        "attempt must be a positive integer",
    )
    err.require(
        isinstance(result.get("agent"), str) and bool(result["agent"].strip()),
        "agent",
        "agent must be a non-empty name",
    )
    for commit_key in ("head_commit", "base_commit"):
        err.require(
            is_git_hex(result.get(commit_key)),
            "commit-oid",
            f"{commit_key} must be a 40-hex commit id",
        )
    tasks = result.get("tasks")
    err.require(isinstance(tasks, list) and tasks, "tasks", "tasks must be a non-empty list")
    if isinstance(tasks, list):
        err.push_base("tasks")
        seen: set = set()
        for index, row in enumerate(tasks):
            err.push_base(str(index))
            err.require(isinstance(row, dict), "task-type", "task row must be a mapping")
            if isinstance(row, dict):
                err.require(
                    is_task_id(row.get("task_id")),
                    "task-id-format",
                    "task_id must match [A-Z0-9-]+",
                )
                if is_task_id(row["task_id"]):
                    err.require(
                        row["task_id"] not in seen,
                        "task-duplicate",
                        f"task {row['task_id']!r} repeated",
                    )
                    seen.add(row["task_id"])
                err.require(
                    row.get("decision") in RESULT_DECISIONS,
                    "decision",
                    f"decision must be one of {sorted(RESULT_DECISIONS)}",
                )
                notes = row.get("notes", "")
                err.require(isinstance(notes, str), "notes", "notes must be a string")
                unknown = set(row) - {"task_id", "decision", "notes"}
                err.require(not unknown, "unknown-key", f"unknown task keys: {sorted(unknown)}")
            err.pop_base()
        err.pop_base()
    changed_paths = result.get("changed_paths")
    err.require(
        isinstance(changed_paths, list), "changed-paths-type", "changed_paths must be a list"
    )
    if isinstance(changed_paths, list):
        for path_index, changed in enumerate(changed_paths):
            err.require(
                is_safe_relpath(changed),
                "path-traversal",
                f"changed_paths[{path_index}] must be a relative normed path",
            )
    err.require(
        is_sha256_hex(result.get("result_digest")),
        "digest-format",
        "result_digest must be lowercase sha256 hex of the result payload",
    )
    tests_claimed = result.get("tests_claimed")
    if isinstance(tests_claimed, dict):
        err.require(
            tests_claimed.get("status") in TEST_STATUSES,
            "test-status",
            f"tests_claimed.status must be one of {sorted(TEST_STATUSES)}",
        )
        argv = tests_claimed.get("command")
        if argv is not None:
            err.require(
                isinstance(argv, list) and all(isinstance(a, str) for a in argv),
                "test-argv",
                "tests_claimed.command must be an argv list of strings",
            )
    created_at = result.get("created_at")
    err.require(
        isinstance(created_at, str) and bool(created_at.strip()),
        "timestamp",
        "created_at must be an RFC 3339 timestamp string",
    )
    if err.errors:
        raise GroupedValidationError(err.errors)
    return result


def validate_approval(approval: dict) -> dict:
    """Local approval records always carry auth_level self_asserted."""
    keys = {
        "api_version",
        "kind",
        "execution_id",
        "decision",
        "subject_digest",
        "subject_kind",
        "approver",
        "auth_level",
        "created_at",
        "note",
    }
    err = ErrorCollector()
    if not _base_check(approval, err, keys, "approval"):
        raise GroupedValidationError(err.errors)
    err.require(
        approval.get("kind") in APPROVAL_KINDS,
        "kind",
        f"kind must be one of {sorted(APPROVAL_KINDS)}",
    )
    err.require(
        approval.get("decision") in DECISIONS,
        "decision",
        f"decision must be one of {sorted(DECISIONS)}",
    )
    err.require(
        is_sha256_hex(approval.get("subject_digest")),
        "digest-format",
        "subject_digest must be lowercase sha256 hex of the approved subject",
    )
    subject_kind = approval.get("subject_kind")
    err.require(
        isinstance(subject_kind, str) and bool(subject_kind.strip()),
        "subject-kind",
        "subject_kind must be a short name (e.g. planning_snapshot)",
    )
    err.require(
        isinstance(approval.get("approver"), str) and bool(approval["approver"].strip()),
        "approver",
        "approver must be a non-empty operator name",
    )
    err.require(
        approval.get("auth_level") == "self_asserted",
        "auth-level",
        'local approvals must carry auth_level="self_asserted"',
    )
    created_at = approval.get("created_at")
    err.require(
        isinstance(created_at, str) and bool(created_at.strip()),
        "timestamp",
        "created_at must be an RFC 3339 timestamp string",
    )
    note = approval.get("note", "")
    err.require(isinstance(note, str), "note", "note must be a string")
    if err.errors:
        raise GroupedValidationError(err.errors)
    return approval


def validate_operation(receipt: dict) -> dict:
    """Operation records carry stable keys, intents, evidence, and status."""
    keys = {
        "api_version",
        "operation_key",
        "execution_id",
        "action",
        "scope",
        "intent",
        "before",
        "after",
        "status",
        "started_at",
        "finished_at",
    }
    err = ErrorCollector()
    if not _base_check(receipt, err, keys, "operation"):
        raise GroupedValidationError(err.errors)
    operation_key = receipt.get("operation_key")
    err.require(
        isinstance(operation_key, str)
        and bool(operation_key.strip())
        and all(part.strip() for part in operation_key.split(":")),
        "operation-key",
        "operation_key must be a colon-separated non-empty key "
        "(execution:action:scope:attempt:input_digest)",
    )
    action = receipt.get("action")
    err.require(
        isinstance(action, str) and bool(action.strip()),
        "action",
        "action must be a short name",
    )
    scope = receipt.get("scope")
    err.require(isinstance(scope, dict), "scope-type", "scope must be a mapping")
    if isinstance(scope, dict):
        unknown = set(scope) - {"repo_id", "task_id", "attempt", "store_uid", "change_id"}
        err.require(not unknown, "unknown-key", f"unknown scope keys: {sorted(unknown)}")
    intent = receipt.get("intent")
    err.require(isinstance(intent, dict), "intent-type", "intent must be a mapping")
    if isinstance(intent, dict):
        input_digest = intent.get("input_digest")
        err.require(
            is_sha256_hex(input_digest),
            "digest-format",
            "intent.input_digest must be lowercase sha256 hex",
        )
    status = receipt.get("status")
    err.require(
        status in OPERATION_STATUSES,
        "status",
        f"status must be one of {sorted(OPERATION_STATUSES)}",
    )
    for stamp in ("started_at", "finished_at"):
        if receipt.get(stamp) is not None:
            err.require(
                isinstance(receipt.get(stamp), str) and bool(receipt.get(stamp).strip()),
                "timestamp",
                f"{stamp} must be an RFC 3339 timestamp string",
            )
    for evidence_key in ("before", "after"):
        evidence = receipt.get(evidence_key)
        if evidence is not None:
            err.require(
                isinstance(evidence, dict),
                f"{evidence_key}-type",
                f"{evidence_key} must be a mapping",
            )
    if err.errors:
        raise GroupedValidationError(err.errors)
    return receipt


def validate_record(kind: str, payload: dict) -> dict:  # type: ignore[no-untyped-def]
    validators = {
        "snapshot": validate_snapshot,
        "result": validate_result,
        "approval": validate_approval,
        "operation": validate_operation,
    }
    if kind not in validators:
        raise ValueError(f"unknown record kind: {kind!r}")
    return validators[kind](payload)


__all__ = [
    "APPROVAL_KINDS",
    "OPERATION_STATUSES",
    "RESULT_DECISIONS",
    "TEST_STATUSES",
    "validate_approval",
    "validate_operation",
    "validate_record",
    "validate_result",
    "validate_snapshot",
]
