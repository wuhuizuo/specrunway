"""Planning entry point: generate or accept complete OpenSpec planning artifacts."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import yaml

from specrunway.models import ValidationError, load_local_config, validate_manifest
from specrunway.openspec_adapter import OpenSpecAdapter, OpenSpecCommandError
from specrunway.runstore import atomic_write_json

TASK_LABEL_RE = re.compile(r"^-\s+\[[ xX]\]\s+([\d.]+)\s+\[([A-Z0-9][A-Z0-9-]*)\]\s+(.+)$")

PROPOSAL_TEMPLATE = """# {change_id}

## Why

{why}

## What Changes

{what}
"""

DESIGN_TEMPLATE = """# {change_id} Design

## Context

{context}

## Goals/Non-Goals

- Goals: {goals}
- Non-Goals: deferred to the manifest and later planning content.
"""


@dataclass
class PlanOutcome:
    change_id: str
    change_path: str
    store_id: str
    planning_complete: bool
    generated: list
    manifest_path: str | None
    task_ids: list


def load_manifest_file(path: Path) -> dict:
    """Load and validate routing manifest YAML before touching any Store."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValidationError("manifest-unreadable", f"{path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValidationError("manifest-type", f"{path} is not a YAML mapping")
    validate_manifest(raw)
    return raw


def parse_task_texts(request_text: str) -> dict:
    """Extract ``T001: description``-style task text from the request."""
    texts: dict = {}
    for line in request_text.splitlines():
        match = re.match(r"^\s*([A-Z0-9][A-Z0-9-]*)\s*[:;]\s*(.+)$", line)
        if match:
            texts[match.group(1)] = match.group(2).strip()
    return texts


def render_tasks(manifest: dict, task_texts: dict) -> str:
    """Render tasks.md directly from manifest routing (stable task mapping)."""
    lines = ["# Tasks", ""]
    for repo_pos, repo in enumerate(manifest["repos"], start=1):
        lines.append(f"## Repo: {repo['repo_id']}")
        for slot, task_id in enumerate(sorted(repo["task_ids"]), start=1):
            description = task_texts.get(task_id, f"work item {task_id}")
            lines.append(f"- [ ] {repo_pos}.{slot} [{task_id}] {description}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def extract_task_ids(tasks_md_text: str) -> list:
    ids: list = []
    for line in tasks_md_text.splitlines():
        match = TASK_LABEL_RE.match(line.strip())
        if match:
            ids.append(match.group(2))
    return ids


def crosscheck_task_routing(manifest: dict, found_ids: list) -> list:
    """Declared tasks must appear exactly; stray ids reject the plan."""
    declared = [task for repo in manifest["repos"] for task in repo["task_ids"]]
    found_set, declared_set = set(found_ids), set(declared)
    problems: list = []
    seen: set = set()
    for task_id in found_ids:
        if task_id in seen:
            problems.append(f"tasks.md repeats task {task_id}")
        seen.add(task_id)
    for missing in sorted(declared_set - found_set):
        problems.append(f"tasks.md misses manifest task {missing}")
    for extra in sorted(found_set - declared_set):
        problems.append(f"tasks.md declares undeclared task {extra}")
    if problems:
        raise ValidationError("task-routing", "; ".join(problems))
    return found_ids


def spec_uid(seed: str) -> str:
    """Deterministic specrunway/v1 uid from a stable seed."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return str(uuid.UUID(bytes=digest[:16], version=4))


def plan(
    control_root: Path,
    store_id: str,
    change_id: str,
    request_path: Path | None = None,
    manifest_path: Path | None = None,
    openspec_bin: str | None = None,
) -> PlanOutcome:
    """Create or accept planning artifacts for *change_id* in the mapped Store."""
    config = load_local_config(control_root)
    configured_store = config["store"]
    if store_id and store_id != configured_store["id"]:
        raise ValidationError(
            "store-unknown",
            f"--store {store_id!r} does not match local.yaml store id {configured_store['id']!r}",
        )

    manifest: dict | None = None
    if manifest_path is not None:
        manifest = load_manifest_file(manifest_path)

    adapter = OpenSpecAdapter(
        store_path=Path(configured_store["path"]),
        store_id=configured_store["id"],
        openspec_bin=_resolve_openspec_bin(control_root, openspec_bin),
    )
    adapter.store_setup()

    request_text = request_path.read_text(encoding="utf-8") if request_path else None
    generated: list = []

    existing: dict | None = None
    try:
        existing = adapter.status(change_id)
    except OpenSpecCommandError as exc:
        if "not found" not in str(exc.message).lower():
            raise

    if existing is None:
        if request_text is None:
            raise ValidationError(
                "plan-request-required",
                f"change {change_id} is new; pass --request to generate its artifacts",
            )
        created = adapter.new_change(change_id)
        change_path = Path(created["change_path"])
        manifest = _write_generation(
            adapter, change_path, change_id, request_text, manifest, generated, config
        )
    elif not existing["planning_complete"]:
        if request_text is None:
            raise ValidationError(
                "plan-incomplete",
                f"change {change_id} exists but lacks artifacts; pass --request to generate them",
            )
        change_path = Path(existing["change_root"])
        manifest = _write_generation(
            adapter, change_path, change_id, request_text, manifest, generated, config
        )
    else:
        # Manual plan accepted: complete artifacts were already prepared.
        change_path = Path(existing["change_root"])
        if manifest is None:
            found_ids = extract_task_ids((change_path / "tasks.md").read_text(encoding="utf-8"))
            if not found_ids:
                raise ValidationError(
                    "manifest-required",
                    "manual plan without mapped routing: supply --manifest (or task labels)",
                )
            manifest = _manual_manifest(adapter, change_id, found_ids, config)

    planning = adapter.status(change_id)
    if not planning["planning_complete"]:
        missing = [a for a, v in planning["artifacts"].items() if not v]
        raise ValidationError(
            "plan-incomplete",
            f"planning still incomplete; missing {missing}",
        )
    found_ids = extract_task_ids((change_path / "tasks.md").read_text(encoding="utf-8"))
    crosscheck_task_routing(manifest, found_ids)

    pending_root = control_root / ".specrunway" / "plans" / change_id
    pending_root.mkdir(parents=True, exist_ok=True)
    manifest_target = pending_root / "manifest.yaml"
    manifest_target.write_text(yaml.safe_dump(manifest, sort_keys=True), encoding="utf-8")
    atomic_write_json(
        pending_root / "plan-summary.json",
        {
            "api_version": "specrunway/v1",
            "change_id": change_id,
            "store_id": configured_store["id"],
            "store_path": str(adapter.store_path),
            "manifest_path": str(manifest_target),
            "manifest": manifest,
            "task_ids": found_ids,
            "planning_complete": True,
            "generated": generated,
        },
    )

    return PlanOutcome(
        change_id=change_id,
        change_path=str(change_path),
        store_id=configured_store["id"],
        planning_complete=True,
        generated=generated,
        manifest_path=str(manifest_target),
        task_ids=found_ids,
    )


def _write_generation(
    adapter: OpenSpecAdapter,
    change_path: Path,
    change_id: str,
    request_text: str,
    manifest: dict | None,
    generated: list,
    config: dict,
) -> dict:
    """Materialize proposal/design/tasks/specs from the request + routing."""
    task_texts = parse_task_texts(request_text)
    if manifest is None:
        manifest = _minimal_manifest(adapter, change_id, task_texts, config)
    (change_path / "proposal.md").write_text(
        PROPOSAL_TEMPLATE.format(
            change_id=change_id,
            why=_section(request_text, "why", fallback="Implement the requested change."),
            what=_section(request_text, "what", fallback="See design and tasks."),
        ),
        encoding="utf-8",
    )
    generated.append("proposal.md")
    (change_path / "design.md").write_text(
        DESIGN_TEMPLATE.format(
            change_id=change_id,
            context=_section(request_text, "context", fallback="As discussed in the request."),
            goals=_section(request_text, "goals", fallback="completed verified delivery"),
        ),
        encoding="utf-8",
    )
    generated.append("design.md")
    (change_path / "tasks.md").write_text(render_tasks(manifest, task_texts), encoding="utf-8")
    generated.append("tasks.md")
    _write_spec_deltas(change_path, request_text, manifest, generated)
    return manifest


def _section(text: str, name: str, *, fallback: str) -> str:
    match = re.search(
        rf"^#+\s*{re.escape(name)}\s*$\n(?P<body>.*?)(?=^#+\s|\Z)",
        text,
        re.MULTILINE | re.IGNORECASE | re.DOTALL,
    )
    if match:
        body = match.group("body").strip()
        if body:
            return body
    return fallback


def _write_spec_deltas(
    change_path: Path, request_text: str, manifest: dict, generated: list
) -> None:
    """Scaffold one capability delta per repo (request may override via Spec blocks)."""
    capability_blocks = _parse_spec_blocks(request_text)
    shared = next(iter(capability_blocks.values()), None)
    spec_root = change_path / "specs"
    spec_root.mkdir(parents=True, exist_ok=True)
    for repo in manifest["repos"]:
        block = shared or {
            "title": f"{repo['repo_id']} delivery",
            "body": "The requested capability SHALL complete with trusted verification.",
            "scenario_title": f"{repo['repo_id']} tasks accepted",
            "when": "the implementation completes in a separate worktree",
            "then": "the tasks attach to accepted commit evidence",
        }
        target = spec_root / f"{repo['repo_id']}-delivery"
        target.mkdir(parents=True, exist_ok=True)
        (target / "spec.md").write_text(
            f"# {target.name} Specification\n\n"
            "## ADDED Requirements\n\n"
            f"### Requirement: {block['title']}\n\n"
            f"{block['body']}\n\n"
            f"#### Scenario: {block['scenario_title']}\n\n"
            f"- **WHEN** {block['when']}\n"
            f"- **THEN** {block['then']}\n",
            encoding="utf-8",
        )
        generated.append(f"specs/{target.name}/spec.md")


def _parse_spec_blocks(text: str) -> dict:
    blocks: dict = {}
    pattern = re.compile(
        r"^Spec-Head:\s*(?P<capability>[a-z0-9-]+)\s*$\n"
        r"^Spec-Title:\s*(?P<title>.+?)\s*$\n"
        r"^Spec-Body:\s*(?P<body>.+?)\s*$\n"
        r"^Spec-When:\s*(?P<when>.+?)\s*$\n"
        r"^Spec-Then:\s*(?P<then>.+?)\s*$",
        re.MULTILINE,
    )
    for match in pattern.finditer(text):
        blocks[match.group("capability")] = {
            "title": match.group("title"),
            "body": match.group("body"),
            "scenario_title": f"{match.group('title')} accepted",
            "when": match.group("when"),
            "then": match.group("then"),
        }
    return blocks


def _resolve_openspec_bin(control_root: Path, explicit: str | None) -> str | None:
    from specrunway.toolresolvers import resolve_tool_bin

    return resolve_tool_bin(control_root, explicit, "openspec")


def _minimal_manifest(
    adapter: OpenSpecAdapter, change_id: str, task_texts: dict, config: dict
) -> dict:
    tasks = sorted(task_texts) or ["T001"]
    return _default_manifest(adapter, change_id, tasks, config, task_texts)


def _manual_manifest(
    adapter: OpenSpecAdapter, change_id: str, task_ids: list, config: dict
) -> dict:
    """Manual-plan routing over the repositories declared by the control checkout."""
    tasks = sorted(set(task_ids)) or ["T001"]
    return _default_manifest(adapter, change_id, tasks, config, {})


def _default_manifest(
    adapter: OpenSpecAdapter,
    change_id: str,
    tasks: list,
    config: dict,
    task_texts: dict,
) -> dict:
    repo_ids = list(config["repos"])
    selected = repo_ids[: max(1, min(len(tasks), len(repo_ids)))]
    chunks: list = []
    start = 0
    base_size, remainder = divmod(len(tasks), len(selected))
    for index in range(len(selected)):
        size = base_size + (1 if index < remainder else 0)
        chunks.append(tasks[start : start + size])
        start += size
    repos = []
    profiles = config.get("test_profiles") or {}
    for index, repo_id in enumerate(selected):
        entry = config["repos"][repo_id]
        repo_path = Path(entry["path"])
        profile = f"{repo_id}-unit" if f"{repo_id}-unit" in profiles else "unit"
        repos.append(
            {
                "repo_id": repo_id,
                "base_ref": _repo_base_ref(repo_path),
                "task_ids": chunks[index] or [tasks[min(index, len(tasks) - 1)]],
                "depends_on": [selected[index - 1]] if index else [],
                "allowed_paths": _repo_allowed_paths(repo_path),
                "test_profile": profile,
            }
        )
    integration_profiles = config.get("integration_profiles") or {}
    integration_profile = next(iter(integration_profiles), None)
    manifest = {
        "api_version": "specrunway/v1",
        "store_uid": spec_uid(str(adapter.store_path)),
        "change_id": change_id,
        "change_uid": spec_uid(change_id),
        "repo_order": [repo["repo_id"] for repo in repos],
        "repos": repos,
        "acceptance": [
            {
                "id": f"AC{index:02d}",
                "requirement": task_texts.get(task_id, f"{task_id} completes verification."),
                "verifies": [task_id],
            }
            for index, task_id in enumerate(tasks, start=1)
        ],
        "completion_policy": "merged_commits",
        "budget": {"repo_max_attempts": 3, "integration_max_repairs": 2, "total_minutes": 120},
    }
    if integration_profile:
        manifest["integration_profile"] = integration_profile
    validate_manifest(manifest, known_profiles=set(profiles) | {"unit"})
    return manifest


def _repo_base_ref(repo_path: Path) -> str:
    import subprocess

    for args in (("symbolic-ref", "--short", "-q", "HEAD"), ("rev-parse", "--abbrev-ref", "HEAD")):
        done = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        value = done.stdout.strip()
        if done.returncode == 0 and value and value != "HEAD":
            return value
    return "main"


def _repo_allowed_paths(repo_path: Path) -> list:
    candidates = [
        "src",
        "tests",
        "docs",
        "scripts",
        "cmd",
        "internal",
        "pkg",
        "controllers",
        "api",
    ]
    found = [name for name in candidates if (Path(repo_path) / name).is_dir()]
    return found or ["src", "tests"]


__all__ = [
    "PlanOutcome",
    "crosscheck_task_routing",
    "extract_task_ids",
    "load_manifest_file",
    "parse_task_texts",
    "plan",
    "render_tasks",
    "spec_uid",
]
