"""Guided onboarding: control configuration plus a reviewable change request."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from .models import load_local_config, validate_local_config
from .models.common import ValidationError, is_safe_relpath, is_slug
from .models.manifest import validate_manifest
from .planning import plan, spec_uid

DEFAULT_AGENT_PROFILE = "primary-coding-agent"
DEFAULT_ALLOWED_PATHS = ["src", "tests"]
DEFAULT_STORE_DIR = "openspec-store"
DEFAULT_INTEGRATION_PROFILE = "specrunway-integration"


class WizardIO:
    """Prompt helpers with an injectable input source for deterministic tests."""

    def __init__(self, *, input_fn=input, output=None):
        self._input = input_fn
        self.output = output if output is not None else sys.stdout

    def say(self, text: str = "") -> None:
        self.output.write(text + "\n")
        self.output.flush()

    def ask(
        self,
        prompt: str,
        *,
        default: str | None = None,
        required: bool = True,
        allow_blank: bool = False,
    ) -> str:
        while True:
            suffix = f" [{default}]" if default not in (None, "") else ""
            self.output.write(f"{prompt}{suffix}: ")
            self.output.flush()
            try:
                raw = self._input()
            except EOFError as exc:
                raise ValidationError(
                    "wizard-eof", "input ended before the wizard completed"
                ) from exc
            value = raw.strip()
            if not value and default is not None:
                value = default
            if value:
                return value
            if allow_blank:
                return ""
            if not required:
                return ""
            self.say("A value is required (or press Ctrl-D to cancel).")

    def confirm(self, prompt: str, *, default: bool = False) -> bool:
        marker = "Y/n" if default else "y/N"
        while True:
            answer = self.ask(f"{prompt} ({marker})", default="y" if default else "n")
            normalized = answer.strip().lower()
            if normalized in {"y", "yes"}:
                return True
            if normalized in {"n", "no"}:
                return False
            self.say("Answer yes or no.")


def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (value or "change")[:60].strip("-")


def atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def discover_repositories(control_root: Path) -> list:
    """Sibling Git checkouts that may belong to the central change."""
    root = Path(control_root).resolve()
    candidates: list = []
    for child in sorted(root.parent.iterdir()):
        if child == root or not child.is_dir() or child.name.startswith("."):
            continue
        if (child / ".git").exists():
            candidates.append(str(child))
    return candidates


def _git(repo_path: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def resolve_repository(raw: str, control_root: Path) -> Path:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = Path(control_root) / candidate
    if not candidate.is_dir():
        raise ValidationError("wizard-repo-missing", f"repository path does not exist: {candidate}")
    top = _git(candidate, "rev-parse", "--show-toplevel")
    if not top:
        raise ValidationError(
            "wizard-repo-not-git", f"repository path is not a Git checkout: {candidate}"
        )
    return Path(top).resolve()


def detect_base_ref(repo_path: Path) -> str:
    branch = _git(repo_path, "symbolic-ref", "--short", "-q", "HEAD")
    if not branch or branch == "HEAD":
        branch = _git(repo_path, "rev-parse", "--abbrev-ref", "HEAD")
    return branch if branch and branch != "HEAD" else "main"


def detect_remote_identity(repo_path: Path) -> str:
    return _git(repo_path, "config", "--get", "remote.origin.url")


def suggest_test_argv(repo_path: Path) -> list:
    repo_path = Path(repo_path)
    if (repo_path / "go.mod").is_file():
        return ["go", "test", "./..."]
    if (repo_path / "Cargo.toml").is_file():
        return ["cargo", "test"]
    if (repo_path / "package.json").is_file():
        return ["npm", "test"]
    if (repo_path / "Makefile").is_file():
        return ["make", "test"]
    return ["python", "-m", "pytest", "-q"]


def suggest_allowed_paths(repo_path: Path) -> list:
    repo_path = Path(repo_path)
    ignored = {
        ".git",
        ".github",
        "node_modules",
        "vendor",
        "target",
        "dist",
        "build",
        "__pycache__",
    }
    found = [
        child.name
        for child in sorted(repo_path.iterdir())
        if not child.name.startswith(".") and child.name not in ignored
    ]
    return found or list(DEFAULT_ALLOWED_PATHS)


def _split_commands(raw: str) -> list:
    try:
        return shlex.split(raw)
    except ValueError as exc:
        raise ValidationError("wizard-command", f"cannot parse command {raw!r}: {exc}") from exc


def _split_paths(raw: str) -> list:
    paths = [part.strip().rstrip("/") for part in raw.split(",") if part.strip()]
    normalized: list = []
    for path in paths:
        if not is_safe_relpath(path):
            raise ValidationError(
                "wizard-allowed-path",
                f"allowed path {path!r} must be relative and must not escape the repository",
            )
        if path not in normalized:
            normalized.append(path)
    if not normalized:
        raise ValidationError("wizard-allowed-path", "at least one allowed path is required")
    return normalized


def collect_local_config(control_root: Path, io: WizardIO) -> dict:
    control_root = Path(control_root).resolve()
    io.say("Configure the control checkout (machine-only local.yaml).")
    store_id = io.ask("Store id", default="specrunway-store")
    while not is_slug(store_id):
        io.say("Store id must be a lowercase slug (letters, digits, dashes).")
        store_id = io.ask("Store id", default="specrunway-store")
    store_default = str(control_root / DEFAULT_STORE_DIR)
    store_path = Path(io.ask("Store path", default=store_default)).expanduser()
    if not store_path.is_absolute():
        store_path = control_root / store_path
    store_path = store_path.resolve()

    discovered = discover_repositories(control_root)
    if discovered:
        io.say("Detected sibling Git checkouts: " + ", ".join(discovered))
    io.say("Add the business repositories in execution order (blank to finish).")

    repos: dict = {}
    test_profiles: dict = {}
    while True:
        raw = io.ask("Repository path", allow_blank=True, required=False)
        if not raw:
            break
        repo_path = resolve_repository(raw, control_root)
        default_id = slugify(repo_path.name)
        repo_id = io.ask("Repository id", default=default_id)
        while not is_slug(repo_id) or repo_id in repos:
            reason = "a lowercase slug" if not is_slug(repo_id) else "unique"
            io.say(f"Repository id must be {reason}.")
            repo_id = io.ask("Repository id", default=default_id)
        identity = detect_remote_identity(repo_path)
        if not identity:
            identity = io.ask(
                f"Remote identity for {repo_id} (origin is missing; e.g. github:owner/repo)"
            )
        repos[repo_id] = {"path": str(repo_path), "remote_identity": identity}
        suggested = shlex.join(suggest_test_argv(repo_path))
        command = io.ask(
            f"Test command for {repo_id} (Enter accepts the suggestion)",
            default=suggested,
        )
        if command:
            test_profiles[f"{repo_id}-unit"] = {"command": _split_commands(command)}

    if not repos:
        raise ValidationError(
            "wizard-repos-required", "at least one existing Git repository is required"
        )

    first_repo = next(iter(repos))
    first_path = Path(repos[first_repo]["path"])
    default_integration = shlex.join(suggest_test_argv(first_path))
    integration_command = io.ask(
        "Combined integration command", default=default_integration
    )
    integration_repo = io.ask("Integration repository", default=first_repo)
    if integration_repo not in repos:
        raise ValidationError(
            "wizard-integration-repo",
            f"integration repository {integration_repo!r} is not one of {sorted(repos)}",
        )
    agent_profile = io.ask("Agent profile", default=DEFAULT_AGENT_PROFILE)

    config = {
        "store": {"id": store_id, "path": str(store_path)},
        "repos": repos,
        "agent_profile": agent_profile,
        "max_workers": 1,
        "test_profiles": test_profiles,
        "integration_profiles": {
            DEFAULT_INTEGRATION_PROFILE: {
                "command": _split_commands(integration_command),
                "repo": integration_repo,
            }
        },
    }
    validate_local_config(config)
    return config


def _write_config(config_path: Path, config: dict, io: WizardIO, force: bool) -> None:
    if (
        config_path.exists()
        and not force
        and not io.confirm(f"{config_path} exists; replace it?", default=False)
    ):
        raise ValidationError("wizard-overwrite-declined", f"{config_path} was not replaced")
    atomic_write_text(config_path, yaml.safe_dump(config, sort_keys=False))


def _split_task_text(raw: str) -> list:
    parts = [part.strip() for part in re.split(r"[;\n]", raw) if part.strip()]
    return [part for part in parts if part]


def collect_change_inputs(
    config: dict, description: str, io: WizardIO
) -> tuple[dict, dict, dict, dict]:
    tasks_by_repo: dict = {}
    base_refs: dict = {}
    allowed_paths: dict = {}
    depends_on: dict = {}
    previous: str | None = None
    task_number = 0
    for repo_id, entry in config["repos"].items():
        raw_tasks = io.ask(
            f"Tasks for {repo_id} (separate with ';')", default=description
        )
        texts = _split_task_text(raw_tasks)
        if not texts:
            raise ValidationError(
                "wizard-tasks-required", f"repository {repo_id!r} needs at least one task"
            )
        ids = []
        for text in texts:
            task_number += 1
            ids.append((f"T{task_number:03d}", text))
        tasks_by_repo[repo_id] = ids
        base_refs[repo_id] = io.ask(
            f"Base ref for {repo_id}", default=detect_base_ref(Path(entry["path"]))
        )
        default_paths = ",".join(suggest_allowed_paths(Path(entry["path"])))
        raw_paths = io.ask(f"Allowed paths for {repo_id}", default=default_paths)
        allowed_paths[repo_id] = _split_paths(raw_paths)
        if previous is not None:
            depends_on[repo_id] = (
                [previous]
                if io.confirm(f"Does {repo_id} depend on {previous}?", default=True)
                else []
            )
        else:
            depends_on[repo_id] = []
        previous = repo_id
    return tasks_by_repo, base_refs, allowed_paths, depends_on


def render_request(
    *,
    change_id: str,
    why: str,
    what: str,
    context: str,
    acceptance: str,
    tasks_by_repo: dict,
) -> str:
    lines = [
        f"# {change_id}",
        "",
        "## Why",
        "",
        why.strip(),
        "",
        "## What Changes",
        "",
        what.strip(),
        "",
        "## Context",
        "",
        context.strip() or "Collected by the SpecRunway onboarding wizard.",
        "",
        "## Goals/Non-Goals",
        "",
        f"- Goals: {acceptance.strip()}",
        "- Non-Goals: deferred to the manifest and later planning content.",
        "",
        "## Tasks",
        "",
    ]
    for repo_id, tasks in tasks_by_repo.items():
        lines.append(f"### {repo_id}")
        for task_id, text in tasks:
            lines.append(f"{task_id}: {text}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_manifest(
    *,
    config: dict,
    change_id: str,
    tasks_by_repo: dict,
    base_refs: dict,
    allowed_paths: dict,
    depends_on: dict,
    acceptance: str,
) -> dict:
    profiles = config.get("test_profiles") or {}
    integration_profiles = config.get("integration_profiles") or {}
    integration_profile = next(iter(integration_profiles), DEFAULT_INTEGRATION_PROFILE)
    if integration_profile not in integration_profiles:
        raise ValidationError(
            "integration-profile-missing",
            "local.yaml declares no integration profile; run `specrunway wizard --reconfigure`",
        )
    repos = []
    all_tasks: list = []
    for repo_id in config["repos"]:
        tasks = tasks_by_repo[repo_id]
        all_tasks.extend(task_id for task_id, _text in tasks)
        profile = f"{repo_id}-unit" if f"{repo_id}-unit" in profiles else "unit"
        repos.append(
            {
                "repo_id": repo_id,
                "base_ref": base_refs[repo_id],
                "task_ids": [task_id for task_id, _text in tasks],
                "depends_on": depends_on[repo_id],
                "allowed_paths": allowed_paths[repo_id],
                "test_profile": profile,
            }
        )
    manifest = {
        "api_version": "specrunway/v1",
        "store_uid": spec_uid(str(Path(config["store"]["path"]).resolve())),
        "change_id": change_id,
        "change_uid": spec_uid(change_id),
        "repo_order": list(config["repos"]),
        "repos": repos,
        "acceptance": [
            {"id": "AC01", "requirement": acceptance.strip(), "verifies": all_tasks}
        ],
        "integration_profile": integration_profile,
        "completion_policy": "merged_commits",
        "budget": {
            "repo_max_attempts": 3,
            "integration_max_repairs": 2,
            "total_minutes": 120,
        },
    }
    validate_manifest(
        manifest,
        known_profiles=set(profiles) | {"unit"},
    )
    return manifest


def _confirm_overwrite(paths: list, io: WizardIO, force: bool) -> None:
    existing = [str(path) for path in paths if Path(path).exists()]
    if (
        existing
        and not force
        and not io.confirm("Replace existing " + ", ".join(existing) + "?", default=False)
    ):
        raise ValidationError(
            "wizard-overwrite-declined", "existing artifacts were not replaced"
        )


def run_wizard(
    control_root: Path,
    *,
    io: WizardIO | None = None,
    reconfigure: bool = False,
    change_id: str | None = None,
    description: str | None = None,
    request_path: Path | str | None = None,
    manifest_path: Path | str | None = None,
    skip_init: bool = False,
    skip_plan: bool = False,
    force: bool = False,
) -> dict:
    """Run configuration then request phases and hand off to ``plan``."""
    from .bootstrap import initialize_control

    root = Path(control_root).expanduser().resolve()
    if not root.is_dir():
        raise ValidationError("wizard-root-missing", f"control root does not exist: {root}")
    wizard = io or WizardIO()
    config_path = root / "local.yaml"
    config_created = False

    if reconfigure or not config_path.is_file():
        if not config_path.is_file():
            wizard.say(f"No local.yaml found; using {root} as the control checkout.")
        config = collect_local_config(root, wizard)
        _write_config(config_path, config, wizard, force)
        config_created = True
    else:
        config = load_local_config(root)
        wizard.say(f"Using existing control configuration: {config_path}")

    initialized = None
    if not skip_init:
        initialized = initialize_control(root, config)
        wizard.say("Control checkout initialized (Store, Specify workspace, bundled step).")

    generated_request: Path | None = None
    generated_manifest: Path | None = None
    if request_path is not None:
        generated_request = Path(request_path).expanduser()
        if not generated_request.is_absolute():
            generated_request = root / generated_request
        generated_request = generated_request.resolve()
        if not generated_request.is_file():
            raise ValidationError(
                "wizard-request-missing", f"request file does not exist: {generated_request}"
            )
        if change_id is None:
            change_id = slugify(generated_request.stem)
        if manifest_path is not None:
            generated_manifest = Path(manifest_path).expanduser()
            if not generated_manifest.is_absolute():
                generated_manifest = root / generated_manifest
            generated_manifest = generated_manifest.resolve()
    elif skip_plan:
        change_id = change_id or ""
    else:
        description = description or wizard.ask("Change summary")
        if change_id is None:
            change_id = slugify(description)
        while not is_slug(change_id):
            wizard.say("Change id must be a lowercase slug.")
            change_id = wizard.ask("Change id", default=slugify(description))
        why = wizard.ask("Why is this needed?", default=f"Implement: {description}")
        what = wizard.ask("What should change?", default=description)
        context = wizard.ask("Additional context", required=False, allow_blank=True)
        acceptance = wizard.ask(
            "Acceptance criteria",
            default=f"{description} is delivered with trusted verification.",
        )
        tasks_by_repo, base_refs, allowed, depends = collect_change_inputs(
            config, description, wizard
        )
        generated_request = root / "requests" / f"{change_id}.md"
        generated_manifest = (
            root / ".specrunway" / "requests" / f"{change_id}.manifest.yaml"
        )
        _confirm_overwrite([generated_request, generated_manifest], wizard, force)
        atomic_write_text(
            generated_request,
            render_request(
                change_id=change_id,
                why=why,
                what=what,
                context=context,
                acceptance=acceptance,
                tasks_by_repo=tasks_by_repo,
            ),
        )
        manifest = build_manifest(
            config=config,
            change_id=change_id,
            tasks_by_repo=tasks_by_repo,
            base_refs=base_refs,
            allowed_paths=allowed,
            depends_on=depends,
            acceptance=acceptance,
        )
        atomic_write_text(
            generated_manifest, yaml.safe_dump(manifest, sort_keys=False)
        )
        wizard.say(f"Wrote request: {generated_request}")
        wizard.say(f"Wrote routing manifest: {generated_manifest}")

    result: dict = {
        "control_root": str(root),
        "config_path": str(config_path),
        "config_created": config_created,
        "request_path": str(generated_request) if generated_request else None,
        "manifest_path": str(generated_manifest) if generated_manifest else None,
        "change_id": change_id or "",
        "planned": False,
        "next": [],
    }
    if initialized is not None:
        result["specify_initialized"] = initialized["specify_initialized"]
        result["step_package"] = initialized["step_package"]

    if skip_plan:
        return result
    if generated_request is None:
        raise ValidationError("wizard-request-missing", "no request file was produced")

    outcome = plan(
        control_root=root,
        store_id=config["store"]["id"],
        change_id=change_id or "",
        request_path=generated_request,
        manifest_path=generated_manifest,
    )
    result.update(
        {
            "planned": True,
            "change_id": outcome.change_id,
            "change_path": outcome.change_path,
            "planning_complete": outcome.planning_complete,
            "task_ids": outcome.task_ids,
            "generated": outcome.generated,
            "next": [
                f"specrunway run --change {outcome.change_id}",
                "specrunway approve --execution <id> --kind plan --actor <you>",
                "specrunway run --execution <id> --continue",
            ],
        }
    )
    return result


__all__ = [
    "WizardIO",
    "atomic_write_text",
    "build_manifest",
    "collect_change_inputs",
    "collect_local_config",
    "detect_base_ref",
    "discover_repositories",
    "render_request",
    "resolve_repository",
    "run_wizard",
    "slugify",
    "suggest_allowed_paths",
    "suggest_test_argv",
]
