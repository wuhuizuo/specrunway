"""local.yaml (machine-only wiring) validation and control-checkout loading."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from specrunway.models.common import ErrorCollector, GroupedValidationError, is_slug
from specrunway.remotes import normalize_identity, remote_matches

LOCAL_KEYS = {"store", "repos", "agent_profile", "max_workers", "integration_profiles"}
INTEGRATION_PROFILE_KEYS = {"command", "repo", "timeout_seconds"}
STORE_KEYS = {"id", "path"}
REPO_ENTRY_KEYS = {"path", "remote_identity"}


def validate_local_config(config: dict) -> dict:
    """Shape-validate local.yaml content (no filesystem side effects)."""
    err = ErrorCollector()
    if not isinstance(config, dict):
        err.fail("local-type", "local.yaml content must be a YAML mapping")
        raise GroupedValidationError(err.errors)
    unknown = set(config) - LOCAL_KEYS
    err.require(not unknown, "unknown-key", f"unknown local.yaml keys: {sorted(unknown)}")

    store = config.get("store")
    if not isinstance(store, dict):
        err.fail("store-type", "store must be a mapping")
    else:
        err.push_base("store")
        store_unknown = set(store) - STORE_KEYS
        err.require(
            not store_unknown, "unknown-key", f"store has unknown keys: {sorted(store_unknown)}"
        )
        err.require(is_slug(store.get("id")), "store-id", "store.id must be a slug")
        path = store.get("path")
        err.require(
            isinstance(path, str) and bool(Path(path.strip()).is_absolute()),
            "store-path",
            "store.path must be an absolute path (resolve relative paths at load time)",
        )
        err.pop_base()
    agent_profile = config.get("agent_profile")
    err.require(
        isinstance(agent_profile, str) and bool(agent_profile.strip()),
        "agent-profile",
        "agent_profile must be a non-empty string",
    )
    max_workers = config.get("max_workers", 1)
    if max_workers != 1:
        err.require(
            False,
            "not-supported-in-v1",
            "v1 runs one execution per control/Store checkout; max_workers must be 1",
        )
    repos = config.get("repos")
    if not isinstance(repos, dict) or not repos:
        err.fail("repos-type", "repos must be a non-empty mapping of repo_id -> entry")
    else:
        err.push_base("repos")
        for repo_id, entry in repos.items():
            err.push_base(str(repo_id))
            if not is_slug(str(repo_id)):
                err.require(False, "repo-id-format", f"repo key {repo_id!r} is not a slug")
            if not isinstance(entry, dict):
                err.fail("repo-entry-type", "repo entry must be a mapping")
                err.pop_base()
                continue
            entry_unknown = set(entry) - REPO_ENTRY_KEYS
            err.require(
                not entry_unknown,
                "unknown-key",
                f"repo {repo_id!r} has unknown keys: {sorted(entry_unknown)}",
            )
            repo_path = entry.get("path")
            err.require(
                isinstance(repo_path, str) and bool(Path(repo_path.strip()).is_absolute()),
                "repo-path",
                f"repo {repo_id!r} path must be absolute",
            )
            identity = entry.get("remote_identity")
            err.require(
                isinstance(identity, str) and bool(identity.strip()),
                "remote-identity",
                f"repo {repo_id!r} remote_identity must be a non-empty string",
            )
            if isinstance(identity, str) and identity.strip():
                host, id_path = normalize_identity(identity)
                err.require(
                    bool(host) and bool(id_path),
                    "remote-identity",
                    f"repo {repo_id!r} remote_identity {identity!r} is not a parseable "
                    "form (github:owner/repo, https://host/path, git@host:path)",
                )
            err.pop_base()
    profiles = config.get("integration_profiles")
    if profiles is not None:
        err.require(
            isinstance(profiles, dict),
            "integration-profiles-type",
            "integration_profiles must be a mapping of profile name -> entry",
        )
        if isinstance(profiles, dict):
            err.push_base("integration_profiles")
            for name, entry in profiles.items():
                err.push_base(str(name))
                err.require(
                    is_slug(str(name)),
                    "integration-profile-name",
                    f"integration profile {name!r} is not a slug",
                )
                if not isinstance(entry, dict):
                    err.fail("integration-profile-type", "profile entry must be a mapping")
                    err.pop_base()
                    continue
                unknown = set(entry) - INTEGRATION_PROFILE_KEYS
                err.require(
                    not unknown,
                    "unknown-key",
                    f"integration profile {name!r} has unknown keys: {sorted(unknown)}",
                )
                command = entry.get("command")
                err.require(
                    isinstance(command, list)
                    and len(command) > 0
                    and all(isinstance(part, str) and part.strip() for part in command),
                    "integration-command",
                    "command must be a non-empty argv list of strings",
                )
                repo = entry.get("repo")
                if repo is not None:
                    err.require(
                        isinstance(repo, str) and is_slug(repo),
                        "integration-repo",
                        "repo must be a repository id slug",
                    )
                timeout = entry.get("timeout_seconds")
                if timeout is not None:
                    err.require(
                        isinstance(timeout, int)
                        and not isinstance(timeout, bool)
                        and timeout > 0,
                        "integration-timeout",
                        "timeout_seconds must be a positive integer",
                    )
                err.pop_base()
            err.pop_base()
    if err.errors:
        raise GroupedValidationError(err.errors)
    return config


def load_local_config(control_root: Path) -> dict:
    """Load and validate control checkout local.yaml, resolving relative paths."""
    path = control_root / "local.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found")
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise GroupedValidationError(
            [
                {
                    "code": "local-yaml",
                    "message": f"local.yaml is not valid YAML: {exc}",
                    "path": None,
                }
            ]
        ) from exc
    root_resolved = control_root.resolve()
    if isinstance(parsed, dict):
        store = parsed.get("store")
        if isinstance(store, dict) and isinstance(store.get("path"), str):
            path_value = Path(store["path"].strip())
            if not path_value.is_absolute():
                store["path"] = str((root_resolved / path_value).resolve())
        repos = parsed.get("repos")
        if isinstance(repos, dict):
            for entry in repos.values():
                if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                    path_value = Path(entry["path"].strip())
                    if not path_value.is_absolute():
                        entry["path"] = str((root_resolved / path_value).resolve())
    return validate_local_config(parsed if isinstance(parsed, dict) else {})


def validate_checkout_wiring(config: dict, known_profiles: set | None = None) -> list:
    """Cross-checks before any agent invocation: store/repo existence, git, remotes.

    Returns a list of machine error dicts (empty when wiring is sound).
    L03 uses this to verify first-plan/run preconditions per change 03.
    """
    from specrunway.models.manifest import validate_manifest  # local import avoids cycle

    errors: list = []
    store_path = Path(config["store"]["path"])
    if not store_path.is_dir():
        errors.append(
            {"code": "store-missing", "message": f"{store_path} missing", "path": "store"}
        )
    else:
        openspec_dir = store_path / "openspec"
        if not openspec_dir.is_dir():
            errors.append(
                {
                    "code": "store-uninitialized",
                    "message": f"{store_path} lacks openspec/",
                    "path": "store",
                }
            )
    for repo_id, entry in sorted(config["repos"].items()):
        repo_path = Path(entry["path"])
        base = f"repos/{repo_id}/path"
        if not repo_path.is_dir():
            errors.append(
                {"code": "repo-missing", "message": f"{repo_path} missing", "path": base}
            )
            continue
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            errors.append(
                {
                    "code": "repo-not-git",
                    "message": f"{repo_path} is not a Git repository",
                    "path": base,
                }
            )
            continue
        identity = entry.get("remote_identity", "")
        url_proc = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if url_proc.returncode != 0:
            errors.append(
                {
                    "code": "remote-missing",
                    "message": f"{repo_path} has no origin remote",
                    "path": base,
                }
            )
        elif identity and not remote_matches(identity, url_proc.stdout.strip()):
            errors.append(
                {
                    "code": "wrong-checkout",
                    "message": (
                        f"repo {repo_id!r} origin {url_proc.stdout.strip()!r} does not "
                        f"match declared remote_identity {identity!r}"
                    ),
                    "path": f"repos/{repo_id}/remote_identity",
                }
            )
    manifest_check = config.get("_manifest")
    if manifest_check is not None:
        try:
            validate_manifest(manifest_check, known_profiles=known_profiles or None)
            for row in manifest_check["repos"]:
                if row["repo_id"] not in config["repos"]:
                    errors.append(
                        {
                            "code": "unknown-repo",
                            "message": f"manifest repo {row['repo_id']!r} is missing from local.yaml",
                            "path": "repos",
                        }
                    )
        except Exception as exc:  # noqa: BLE001 - surfaced verbatim, no retries
            errors.append({"code": "manifest-invalid", "message": str(exc), "path": "manifest"})
    return errors


__all__ = ["load_local_config", "validate_checkout_wiring", "validate_local_config"]
