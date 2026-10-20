"""Independent result validation: identity, ancestry, paths, trusted evidence."""

from __future__ import annotations

from pathlib import Path

from hubcoord.models.common import (
    GroupedValidationError,
    ValidationError,
    is_safe_relpath,
    json_digest,
)
from hubcoord.models.records import validate_result
from hubcoord.runstore import _read_json_or_none
from hubcoord.worktrees import WorktreeError, is_ancestor


class ResultRejected(ValidationError):
    """A result that cannot be tied to the frozen execution."""


def compute_result_digest(record: dict) -> str:
    """Recovers hub-record digest binding: canonical json minus the digest field."""
    trimmed = {k: v for k, v in record.items() if k != "result_digest"}
    return json_digest(trimmed)


def _norm(path: str) -> str:
    parts = [p for p in path.replace("\\", "/").split("/") if p not in ("", ".")]
    return "/".join(parts)


def _within_allowed(changed: str, allowed: list) -> bool:
    normalized = _norm(changed)
    for pattern in allowed:
        prefix = _norm(pattern)
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return True
    return False


def trusted_receipt(run_dir: Path, repo_id: str, attempt: int) -> dict | None:
    candidate = Path(run_dir) / "tests_receipts" / repo_id / f"{attempt}.json"
    return _read_json_or_none(candidate)


def _head_exists(repo_checkout: Path, head: str) -> bool:
    from hubcoord.worktrees import _git

    done = _git(repo_checkout, "cat-file", "-e", f"{head}^{{commit}}")
    return done.returncode == 0


def accept_result(
    result_path: Path,
    execution_id: str,
    repo_id: str,
    manifest: dict,
    snapshot: dict,
    repo_checkout: Path,
    run_dir: Path,
) -> dict:
    """Validate and bind one agent result to the frozen execution.

    Raises ResultRejected (stable codes) when identity, ancestry, paths, or
    trusted test evidence do not check out.
    """
    result = _read_json_or_none(Path(result_path))
    if result is None:
        raise ResultRejected("result-missing", f"no parseable result.json at {result_path}")

    try:
        validate_result(result)
    except GroupedValidationError as exc:
        raise ResultRejected("result-invalid", f"result shape invalid: {exc}") from exc

    if result["execution_id"] != execution_id:
        raise ResultRejected(
            "execution-mismatch",
            f"result execution_id {result['execution_id']!r} != frozen {execution_id!r}",
        )
    if result["repo_id"] != repo_id:
        raise ResultRejected(
            "repo-mismatch", f"result repo_id {result['repo_id']!r} != expected {repo_id!r}"
        )

    repo_entry = next((r for r in manifest["repos"] if r["repo_id"] == repo_id), None)
    if repo_entry is None:
        raise ResultRejected("repo-not-in-manifest", f"repo_id {repo_id!r} not in manifest")

    declared = set(repo_entry["task_ids"])
    reported = {row["task_id"] for row in result["tasks"]}
    extra = reported - declared
    if extra:
        raise ResultRejected(
            "task-unmapped", f"result tasks not in {repo_id} routing: {sorted(extra)}"
        )

    base_entry = snapshot["repos"][repo_id]
    if result["base_commit"] != base_entry["base_oid"]:
        raise ResultRejected(
            "base-mismatch",
            f"result base_commit {result['base_commit'][:12]} != frozen "
            f"{base_entry['base_oid'][:12]} for {repo_id}",
        )

    if not _head_exists(Path(repo_checkout), result["head_commit"]):
        raise ResultRejected(
            "head-not-descendant",
            f"head_commit {result['head_commit'][:12]} does not exist in the repository",
        )
    try:
        descendant = is_ancestor(
            Path(repo_checkout), base_entry["base_oid"], result["head_commit"]
        )
    except WorktreeError as exc:
        raise ResultRejected("ancestry-check-failed", str(exc)) from exc
    if not descendant:
        raise ResultRejected(
            "head-not-descendant",
            f"head_commit {result['head_commit'][:12]} is not a descendant of the frozen base",
        )

    for changed in result["changed_paths"]:
        if not is_safe_relpath(changed):
            raise ResultRejected(
                "path-unsafe", f"changed path is not a safe relative path: {changed!r}"
            )
        if not _within_allowed(changed, repo_entry["allowed_paths"]):
            raise ResultRejected(
                "path-not-allowed",
                f"changed path outside allowed_paths for {repo_id}: {changed}",
            )

    claimed = result.get("tests_claimed") or {}
    receipt = trusted_receipt(run_dir, repo_id, result["attempt"])
    if receipt is None:
        raise ResultRejected(
            "receipt-missing",
            "no trusted test receipt for this repo/attempt; agent success claims are not evidence",
        )
    if claimed.get("status") != receipt["status"]:
        raise ResultRejected(
            "receipt-mismatch",
            f"agent claims tests {claimed.get('status')!r}; trusted receipt says {receipt['status']!r}",
        )
    if claimed.get("command") is not None and claimed["command"] != receipt["command"]:
        raise ResultRejected(
            "receipt-command-mismatch",
            "claimed test command differs from the trusted runner command",
        )

    if compute_result_digest(result) != result.get("result_digest"):
        raise ResultRejected(
            "digest-mismatch",
            "result_digest does not bind the embedded result payload",
        )
    return result


def persist_result(run_dir: Path, repo_id: str, result: dict) -> Path:
    """Keep the accepted copy under the run dir; returns the written path."""
    from hubcoord.runstore import atomic_write_json

    target = Path(run_dir) / "results" / repo_id / str(result["attempt"]) / "result.json"
    atomic_write_json(target, result)
    return target


__all__ = [
    "ResultRejected",
    "accept_result",
    "compute_result_digest",
    "persist_result",
    "trusted_receipt",
]
