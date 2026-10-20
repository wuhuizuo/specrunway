"""Freeze execution context — planning/rules digests, base OIDs, tool identities."""

from __future__ import annotations

import json
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from hubcoord.models.common import ValidationError, json_digest, strip_checkbox_markers
from hubcoord.models.records import validate_snapshot

#: Rule files frozen into the context digest when present at a repo root.
RULE_FILES = ("AGENTS.md", "CLAUDE.md")

#: Planning artifact files that make up the planning digest.
PLANNING_TOP_FILES = ("proposal.md", "design.md", "tasks.md")


class FreezeError(ValidationError):
    """Freeze-stage validation failure with a stable code."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as exc:  # pragma: no cover - permission corner
        raise FreezeError("freeze-read", f"cannot read {path}: {exc}") from exc


def _planning_pairs(change_path: Path) -> list:
    """Canonical [relpath, checked-input] pairs from the Store change directory."""
    pairs: list = []
    for name in PLANNING_TOP_FILES:
        text = _read_text(change_path / name)
        if text is None:
            raise FreezeError("plan-missing", f"planning artifact missing: {name}")
        if name == "tasks.md":
            text = strip_checkbox_markers(text)
        pairs.append([name, text])
    spec_root = change_path / "specs"
    if spec_root.is_dir():
        for spec_file in sorted(spec_root.rglob("*.md")):
            rel = str(spec_file.relative_to(change_path))
            pairs.append([rel, spec_file.read_text(encoding="utf-8")])
    return sorted(pairs, key=lambda pair: pair[0])


def _rule_pairs(repo_paths: dict) -> list:
    pairs: list = []
    for repo_id in sorted(repo_paths):
        repo_path = Path(repo_paths[repo_id])
        for rule_name in RULE_FILES:
            rule_path = repo_path / rule_name
            text = _read_text(rule_path)
            if text is not None:
                pairs.append([f"{repo_id}/{rule_name}", text])
    return sorted(pairs, key=lambda pair: pair[0])


def compute_planning_digest(change_path: Path, manifest: dict) -> str:
    """Digest over proposal/design/tasks text, delta specs, and manifest routing."""
    payload = {
        "planning": _planning_pairs(change_path),
        "manifest": manifest,
    }
    return json_digest(payload)


def compute_context_digest(change_path: Path, manifest: dict, repos_config: dict) -> str:
    """Planning digest content plus organization rules (repo constraint files)."""
    repo_paths = {rid: entry.get("path", "") for rid, entry in repos_config.items()}
    payload = {
        "planning": _planning_pairs(change_path),
        "manifest": manifest,
        "rules": _rule_pairs(repo_paths),
    }
    return json_digest(payload)


def resolve_base_oid(repo_path: Path, base_ref: str) -> str:
    """Current commit of *base_ref* inside the existing repo checkout."""
    if not (repo_path / ".git").exists():
        raise FreezeError("repo-not-git", f"repo checkout missing .git: {repo_path}")
    probe = subprocess.run(
        ["git", "--no-pager", "-C", str(repo_path), "rev-parse", "--verify", base_ref],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    oid = probe.stdout.strip()
    if probe.returncode != 0 or not (
        len(oid) == 40 and all(c in "0123456789abcdef" for c in oid)
    ):
        raise FreezeError(
            "base-ref-unknown",
            f"{base_ref!r} does not resolve in {repo_path}: "
            f"exit {probe.returncode} {probe.stderr.strip()[:200]}",
        )
    return oid


def freeze_execution(
    execution_id: str,
    change_path: Path,
    manifest: dict,
    repos_config: dict,
    tool_versions: dict,
) -> dict:
    """Build and machine-validate snapshot.json content for the execution.

    *repos_config* maps repo_id -> {"path": checkout path, "remote_identity": id}.
    """
    repos = {}
    for repo in manifest["repos"]:
        repo_id = repo["repo_id"]
        base_ref = repo["base_ref"]
        entry = repos_config.get(repo_id) or {}
        repo_path = Path(entry.get("path", ""))
        remote_identity = entry.get("remote_identity", "")
        repos[repo_id] = {
            "base_ref": base_ref,
            "base_oid": resolve_base_oid(repo_path, base_ref),
            "remote_identity": remote_identity,
        }
    snapshot = {
        "api_version": "hub/v1",
        "execution_id": execution_id,
        "store_uid": manifest["store_uid"],
        "change_id": manifest["change_id"],
        "change_uid": manifest["change_uid"],
        "manifest": manifest,
        "manifest_digest": json_digest(manifest),
        "planning_digest": compute_planning_digest(change_path, manifest),
        "context_digest": compute_context_digest(change_path, manifest, repos_config),
        "repos": repos,
        "tools": tool_versions,
        "created_at": _now(),
    }
    validate_snapshot(snapshot)
    return snapshot


def new_execution_id() -> str:
    return str(uuid.uuid4())


def is_snapshot_immutable(existing: dict, fresh: dict) -> bool:
    """Snapshot immutability check: digest rows except created_at must match."""
    mutable = {"created_at"}
    left = {k: v for k, v in existing.items() if k not in mutable}
    right = {k: v for k, v in fresh.items() if k not in mutable}
    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


__all__ = [
    "FreezeError",
    "compute_context_digest",
    "compute_planning_digest",
    "freeze_execution",
    "is_snapshot_immutable",
    "new_execution_id",
    "resolve_base_oid",
]
