"""Explicit archive preflight, completion policies, backup, reconciliation (L14)."""

from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path

from specrunway.approvals import GateError, subject_digest_for_results, verify_frozen_approval
from specrunway.checkboxes import TASK_LINE_RE
from specrunway.models import load_local_config
from specrunway.models.common import ValidationError
from specrunway.runstore import FileRunStore, _read_json_or_none, atomic_write_json
from specrunway.testprofiles import profile_cwd, profile_for_repo, run_test_command
from specrunway.toolresolvers import resolve_tool_bin
from specrunway.worktrees import is_ancestor


class ArchiveError(ValidationError):
    """Archive refusal with a stable error code."""


POLICIES = {"merged_commits", "validated_commits"}


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _digest_tree(root: Path) -> str:
    rows = []
    if Path(root).is_dir():
        for path in sorted(Path(root).rglob("*")):
            if path.is_file():
                rows.append(
                    [
                        str(path.relative_to(root)),
                        hashlib.sha256(path.read_bytes()).hexdigest(),
                    ]
                )
    return hashlib.sha256(repr(rows).encode("utf-8")).hexdigest()


def _unchecked_tasks(tasks_md: str) -> list:
    return [
        match.group("label")
        for match in TASK_LINE_RE.finditer(tasks_md)
        if match.group("mark").lower() != "x"
    ]


def _preflight(control_root: Path, store: FileRunStore, execution_id: str) -> dict:
    config = load_local_config(Path(control_root))
    snapshot = _read_json_or_none(store.run_dir(execution_id) / "snapshot.json")
    if snapshot is None:
        raise ArchiveError("snapshot-missing", "no frozen snapshot for this execution")
    state = store.read_state(execution_id)
    if state.get("phase") != "ready_for_review":
        raise ArchiveError(
            "not-ready",
            f"execution phase is {state.get('phase')!r}, not ready_for_review",
        )
    manifest = snapshot["manifest"]
    results = state.get("results") or {}
    verification = state.get("verification") or {}
    unproven = [
        repo_id
        for repo_id in manifest["repo_order"]
        if not (results.get(repo_id) or {}).get("passed")
        or (verification.get(repo_id) or {}).get("status") != "passed"
    ]
    if unproven:
        raise ArchiveError(
            "unaccepted-code",
            f"required repository results are not accepted: {', '.join(unproven)}",
        )
    change_path = Path(config["store"]["path"]) / "openspec" / "changes" / snapshot["change_id"]
    tasks_file = change_path / "tasks.md"
    if not tasks_file.is_file():
        raise ArchiveError("tasks-missing", f"no tasks.md at {tasks_file}")
    unchecked = _unchecked_tasks(tasks_file.read_text(encoding="utf-8"))
    if unchecked:
        raise ArchiveError(
            "unaccepted-code",
            f"mapped tasks remain unchecked: {', '.join(unchecked)}",
        )
    subject = subject_digest_for_results(store.run_dir(execution_id))
    try:
        verify_frozen_approval(store, execution_id, "implementation", subject)
    except GateError as exc:
        raise ArchiveError(exc.code, exc.message) from exc

    final_rows = []
    for repo_id in manifest["repo_order"]:
        entry = _repo_entry(manifest, repo_id)
        worktree = store.run_dir(execution_id) / "worktrees" / repo_id
        if not worktree.is_dir():
            raise ArchiveError("verification-stale", f"worktree for {repo_id} is gone")
        profile = profile_for_repo(snapshot, entry)
        receipt = run_test_command(
            profile.command(),
            profile_cwd(worktree, profile),
            store.run_dir(execution_id) / "logs" / repo_id / "archive-final.log",
            profile.timeout_seconds,
        )
        from specrunway.worktrees import head_oid

        head = head_oid(worktree)
        expected_head = results[repo_id]["head_commit"]
        if receipt["status"] != "passed" or head != expected_head:
            raise ArchiveError(
                "verification-stale",
                f"final verification for {repo_id} is not fresh "
                f"(tests {receipt['status']}, head {head[:12]} vs accepted "
                f"{expected_head[:12]})",
            )
        final_rows.append({"repo_id": repo_id, "head_commit": head, "status": "passed"})
    return {
        "config": config,
        "snapshot": snapshot,
        "state": state,
        "change_path": change_path,
        "final_rows": final_rows,
    }


def _repo_entry(manifest: dict, repo_id: str) -> dict:
    for entry in manifest["repos"]:
        if entry["repo_id"] == repo_id:
            return entry
    raise ArchiveError("repo-unknown", f"repo {repo_id!r} is not in the manifest")


def _check_policy_merges(preflight: dict, repos_cfg: dict) -> list:
    manifest = preflight["snapshot"]["manifest"]
    results = preflight["state"].get("results") or {}
    unmerged = []
    for repo_id in manifest["repo_order"]:
        entry = _repo_entry(manifest, repo_id)
        repo_path = Path((repos_cfg.get(repo_id) or {}).get("path") or "")
        if not repo_path.is_dir():
            unmerged.append(repo_id)
            continue
        from specrunway.freezer import resolve_base_oid

        tip = resolve_base_oid(repo_path, entry["base_ref"])
        if not is_ancestor(repo_path, results[repo_id]["head_commit"], tip):
            unmerged.append(repo_id)
    return unmerged


def archive_execution(
    control_root: Path,
    execution_id: str,
    *,
    policy: str | None = None,
    confirm_validated: bool = False,
) -> dict:
    """Explicit archive: preflight, backup, intent, apply deltas, receipt."""
    control_root = Path(control_root)
    store = FileRunStore(control_root / ".specrunway")
    snapshot = _read_json_or_none(store.run_dir(execution_id) / "snapshot.json")
    if snapshot is None:
        raise ArchiveError("snapshot-missing", "no frozen snapshot for this execution")
    op_key = f"{execution_id}:archive:{snapshot['planning_digest'][:16]}"
    for op in store.operations(execution_id):
        if op.get("operation_key") == op_key and op.get("status") == "recorded":
            return {"archived": True, "already_archived": True, "operation": op}
    preflight = _preflight(control_root, store, execution_id)
    snapshot = preflight["snapshot"]
    manifest = snapshot["manifest"]
    repos_cfg = preflight["config"].get("repos") or {}
    manifest_policy = manifest.get("completion_policy", "merged_commits")
    selected = policy or manifest_policy
    if selected not in POLICIES:
        raise ArchiveError("policy-unknown", f"unknown completion policy {selected!r}")
    if selected == "validated_commits" and not confirm_validated:
        raise ArchiveError(
            "confirmation-required",
            "validated_commits requires explicit --confirm-validated; "
            "it records reviewed commits without claiming a main-branch merge",
        )
    if selected == "merged_commits":
        unmerged = _check_policy_merges(preflight, repos_cfg)
        if unmerged:
            raise ArchiveError(
                "partial-merge",
                f"accepted commits are not merged into the base ref for: {', '.join(unmerged)}",
            )

    store_path = Path(preflight["config"]["store"]["path"])

    stamp = _now().replace(":", "").replace("-", "")
    backup_dir = store.run_dir(execution_id) / "archive-backup" / stamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(preflight["change_path"], backup_dir / "change")
    specs_root = store_path / "openspec" / "specs"
    atomic_write_json(
        backup_dir / "before.json",
        {
            "change_path": str(preflight["change_path"]),
            "specs_digest": _digest_tree(specs_root),
            "specs_root": str(specs_root),
            "created_at": _now(),
        },
    )

    store.write_intent(
        execution_id,
        {
            "operation_key": op_key,
            "kind": "archive",
            "execution_id": execution_id,
            "scope": {"change_id": snapshot["change_id"], "policy": selected},
            "before": {
                "change_path": str(preflight["change_path"]),
                "backup_dir": str(backup_dir),
                "specs_digest": _digest_tree(specs_root),
                "policy": selected,
            },
        },
    )

    from specrunway.openspec_adapter import OpenSpecAdapter

    adapter = OpenSpecAdapter(
        store_path=store_path,
        store_id=preflight["config"]["store"]["id"],
        openspec_bin=resolve_tool_bin(control_root, None, "openspec"),
    )
    adapter.store_setup()
    try:
        outcome = adapter.archive(snapshot["change_id"])
    except Exception as exc:
        store.mark_uncertain(
            execution_id,
            op_key,
            {"phase": "archive", "error": str(exc), "backup_dir": str(backup_dir)},
        )

        def uncertain(next_state: dict) -> None:
            next_state["phase"] = "blocked"
            next_state["blocked_reason"] = "uncertain archive outcome"

        current = store.read_state(execution_id)
        store.update_state(execution_id, uncertain, current["revision"])
        raise ArchiveError(
            "archive-uncertain",
            f"openspec archive failed; outcome preserved for reconciliation: {exc}",
        ) from exc

    after_specs = _digest_tree(specs_root)
    archived_path = Path(outcome.get("path") or "")
    if not archived_path.is_dir():
        store.mark_uncertain(
            execution_id,
            op_key,
            {"phase": "verify", "outcome": outcome, "specs_digest": after_specs},
        )
        raise ArchiveError(
            "archive-uncertain",
            "archive returned success but the archived change path is missing",
        )
    if preflight["change_path"].exists():
        store.mark_uncertain(
            execution_id,
            op_key,
            {"phase": "mixed", "outcome": outcome, "specs_digest": after_specs},
        )
        raise ArchiveError(
            "archive-mixed",
            "both active and archived change paths exist; block automatic replay",
        )
    store.record_receipt(
        execution_id,
        op_key,
        {
            "archived_as": outcome.get("archived_as"),
            "path": outcome.get("path"),
            "specs_updated": outcome.get("specs_updated"),
            "specs_digest": after_specs,
            "change_removed": True,
        },
    )
    atomic_write_json(
        backup_dir / "after.json",
        {
            "archived_as": outcome.get("archived_as"),
            "path": outcome.get("path"),
            "specs_digest": after_specs,
            "created_at": _now(),
        },
    )

    def finish(next_state: dict) -> None:
        next_state["phase"] = "archived"
        next_state["archived_as"] = outcome.get("archived_as")

    current = store.read_state(execution_id)
    store.update_state(execution_id, finish, current["revision"])
    return {
        "archived": True,
        "archived_as": outcome.get("archived_as"),
        "path": outcome.get("path"),
        "policy": selected,
        "backup_dir": str(backup_dir),
        "operation_key": op_key,
    }


def reconcile_pending_archive(store: FileRunStore, execution_id: str, snapshot: dict) -> dict:
    """Prove the actual archive outcome before allowing another attempt."""
    pending = [
        op
        for op in store.operations(execution_id)
        if op.get("kind") == "archive" and op.get("status") in ("pending", "uncertain")
    ]
    if not pending:
        return {"outcome": "none"}
    op = pending[0]
    before = op.get("before") or {}
    change_path = Path(before.get("change_path") or "")
    archived_candidates = sorted(change_path.parent.glob(f"archive/*-{snapshot['change_id']}"))
    active_exists = change_path.exists()
    archived_exists = bool(archived_candidates)
    if active_exists and archived_exists:
        raise ArchiveError(
            "archive-mixed",
            "active and archived change paths both exist; preserve evidence and block replay",
        )
    if not active_exists and archived_exists:
        archived = archived_candidates[-1]
        store.record_receipt(
            execution_id,
            op["operation_key"],
            {
                "archived_as": archived.name,
                "path": str(archived),
                "reconciled": True,
                "specs_digest": _digest_tree(change_path.parents[1] / "specs"),
            },
        )

        def finish(next_state: dict) -> None:
            next_state["phase"] = "archived"
            next_state["archived_as"] = archived.name

        current = store.read_state(execution_id)
        store.update_state(execution_id, finish, current["revision"])
        return {"outcome": "archived", "path": str(archived)}
    if active_exists and not archived_exists:
        store.mark_uncertain(execution_id, op["operation_key"], {"outcome": "not-applied"})
        store.reconcile(execution_id, op["operation_key"], {"outcome": "not-applied"})

        def reopen(next_state: dict) -> None:
            if next_state.get("phase") == "blocked":
                next_state["phase"] = "ready_for_review"
                next_state.pop("blocked_reason", None)

        current = store.read_state(execution_id)
        store.update_state(execution_id, reopen, current["revision"])
        return {"outcome": "not-applied"}
    raise ArchiveError(
        "archive-lost",
        "archive intent exists but neither active nor archived change path remains",
    )


__all__ = [
    "ArchiveError",
    "archive_execution",
    "reconcile_pending_archive",
]
