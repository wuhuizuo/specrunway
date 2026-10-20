"""Separate execution worktrees from frozen base commits, original checkout preserved."""

from __future__ import annotations

import subprocess
from pathlib import Path

from specrunway.models.common import ValidationError


class WorktreeError(ValidationError):
    """Worktree creation/preservation failure with a stable code."""


def _git(repo_path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "--no-pager", "-C", str(repo_path), *args],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )


def create_worktree(repo_path: Path, base_oid: str, execution_dir: Path, repo_id: str) -> Path:
    """Add a detached worktree at the frozen base commit for one repository."""
    if not (Path(repo_path) / ".git").exists():
        raise WorktreeError("repo-not-git", f"repo checkout missing .git: {repo_path}")
    target = Path(execution_dir) / "worktrees" / repo_id
    if target.exists():
        raise WorktreeError("worktree-exists", f"worktree path already present: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    done = _git(repo_path, "worktree", "add", "--detach", str(target), base_oid)
    if done.returncode != 0:
        raise WorktreeError(
            "worktree-create",
            f"git worktree add failed for {repo_id}: {done.stderr.strip()[:300]}",
        )
    return target


def original_status(repo_path: Path) -> str:
    """Porcelain snapshot of the original checkout (tracked + untracked)."""
    done = _git(repo_path, "status", "--porcelain")
    if done.returncode != 0:
        raise WorktreeError("repo-status-failed", done.stderr.strip()[:300])
    return done.stdout


def assert_original_preserved(repo_path: Path, before_status: str) -> None:
    """Original checkout contents must not change just by worktree creation."""
    after = original_status(repo_path)
    if after != before_status:
        raise WorktreeError(
            "original-modified",
            f"original checkout status changed during the operation:\n"
            f"before={before_status!r}\nafter={after!r}",
        )


def head_oid(repo_path: Path) -> str:
    done = _git(repo_path, "rev-parse", "HEAD")
    if done.returncode != 0:
        raise WorktreeError("head-unresolved", done.stderr.strip()[:200])
    return done.stdout.strip()


def commit_all(repo_path: Path, message: str, author: str = "specrunway fixture") -> str:
    """Commit everything in the worktree; return the resulting commit OID."""
    add = _git(repo_path, "add", "-A")
    if add.returncode != 0:
        raise WorktreeError("commit-failed", add.stderr.strip()[:300])
    done = _git(
        repo_path,
        "-c",
        f"user.name={author}",
        "-c",
        "user.email=specrunway@example.org",
        "commit",
        "--allow-empty",
        "-m",
        message,
    )
    if done.returncode != 0:
        raise WorktreeError("commit-failed", done.stderr.strip()[:300])
    return head_oid(repo_path)


def is_ancestor(repo_path: Path, base_oid: str, head_oid_value: str) -> bool:
    """True when head_oid descends from base_oid in the recorded history."""
    done = _git(repo_path, "merge-base", "--is-ancestor", base_oid, head_oid_value)
    if done.returncode == 0:
        return True
    if done.returncode == 1:
        return False
    raise WorktreeError(
        "ancestry-check-failed", f"exit {done.returncode}: {done.stderr.strip()[:200]}"
    )


__all__ = [
    "WorktreeError",
    "assert_original_preserved",
    "commit_all",
    "create_worktree",
    "head_oid",
    "is_ancestor",
    "original_status",
]
