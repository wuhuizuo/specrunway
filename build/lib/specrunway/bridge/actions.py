"""Production specrunway bridge actions, delegating to specrunway core functions.

Every action returns the standardized specrunway/v1 envelope used as the step's
``output.data``: ``api_version, action, ok, business IDs, data, evidence,
warnings`` (+ ``error`` when failed). Agent output never becomes shell text.
"""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

from specrunway.approvals import GateError, require_gate
from specrunway.launcher import resolve_profile
from specrunway.launcher import run_agent as launcher_run_agent
from specrunway.models.common import GroupedValidationError, ValidationError, json_digest
from specrunway.models.local import load_local_config
from specrunway.results import (
    ResultRejected,
    accept_result,
    persist_result,
)
from specrunway.runstore import FileRunStore, _read_json_or_none, atomic_write_json
from specrunway.testprofiles import resolve_test_profile, run_test_command
from specrunway.worktrees import create_worktree, head_oid


def envelope(
    action: str,
    ok: bool,
    data: dict,
    evidence: list | None = None,
    warnings: list | None = None,
    store_uid: str = "",
    change_uid: str = "",
    execution_id: str = "",
    error: dict | None = None,
) -> dict:
    result = {
        "api_version": "specrunway/v1",
        "action": action,
        "ok": bool(ok),
        "store_uid": store_uid,
        "change_uid": change_uid,
        "execution_id": execution_id,
        "data": data,
        "evidence": list(evidence or []),
        "warnings": list(warnings or []),
    }
    if not ok:
        result["error"] = error or {
            "code": "specrunway-action-failed",
            "message": "action failed",
            "retryable": False,
        }
    return result


class SpecRunwayActionError(Exception):
    def __init__(self, message: str, output: dict):
        super().__init__(message)
        self.message = message
        self.output = output


def _control_root(config: dict) -> Path:
    root = Path(str(config.get("root") or "")).expanduser()
    if not root.is_dir():
        raise SpecRunwayActionError(
            "root-missing",
            envelope(
                str(config.get("action") or "unknown"),
                False,
                {},
                error={
                    "code": "root-missing",
                    "message": f"control root missing: {root}",
                    "retryable": False,
                },
            ),
        )
    return root


def _load_execution(root: Path, config: dict) -> tuple:
    execution_id = str(config.get("execution") or "")
    if not execution_id:
        raise SpecRunwayActionError(
            "execution-required",
            envelope(
                str(config.get("action") or "unknown"),
                False,
                {},
                error={
                    "code": "execution-required",
                    "message": "specrunway step requires 'execution'",
                    "retryable": False,
                },
            ),
        )
    store = FileRunStore(root / ".specrunway")
    run_dir = store.run_dir(execution_id)
    snapshot = _read_json_or_none(run_dir / "snapshot.json")
    if snapshot is None:
        raise SpecRunwayActionError(
            "snapshot-missing",
            envelope(
                str(config.get("action") or "unknown"),
                False,
                {},
                error={
                    "code": "snapshot-missing",
                    "message": f"no frozen snapshot.json for execution {execution_id}",
                    "retryable": False,
                },
            ),
        )
    return store, run_dir, snapshot


def _repo_row(manifest: dict, repo_id: str) -> dict:
    for entry in manifest["repos"]:
        if entry["repo_id"] == repo_id:
            return entry
    raise SpecRunwayActionError(
        "repo-unknown",
        envelope(
            "run-repo",
            False,
            {},
            error={
                "code": "repo-unknown",
                "message": f"repo {repo_id!r} not in manifest",
                "retryable": False,
            },
        ),
    )


DEFAULT_BUDGET = {
    "repo_max_attempts": 3,
    "integration_max_repairs": 2,
    "total_minutes": 120,
}


def _budget(manifest: dict) -> dict:
    configured = manifest.get("budget") or {}
    return {key: int(configured.get(key, default)) for key, default in DEFAULT_BUDGET.items()}


def _elapsed_minutes(created_at: str) -> float:
    from datetime import datetime

    started = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    return (datetime.now(UTC) - started).total_seconds() / 60.0


def _block(store: FileRunStore, execution_id: str, reason: str) -> None:
    current = store.read_state(execution_id)

    def mutate(next_state: dict) -> None:
        next_state["phase"] = "blocked"
        next_state["blocked_reason"] = reason

    store.update_state(execution_id, mutate, current["revision"])


def _norm_item(item: object) -> str:
    if isinstance(item, dict):
        return str(item.get("repo_id") or "")
    return str(item)


def action_prepare(config: dict, context) -> dict:
    root = _control_root(config)
    store, _run_dir, snapshot = _load_execution(root, config)
    manifest = snapshot["manifest"]
    rows = []
    for repo_id in manifest["repo_order"]:
        entry = _repo_row(manifest, repo_id)
        rows.append(
            {
                "repo_id": repo_id,
                "task_ids": list(entry["task_ids"]),
                "depends_on": list(entry.get("depends_on") or []),
                "allowed_paths": list(entry.get("allowed_paths") or []),
                "test_profile": entry.get("test_profile", ""),
                "base_oid": snapshot["repos"][repo_id]["base_oid"],
                "base_ref": snapshot["repos"][repo_id]["base_ref"],
            }
        )
    state = store.read_state(config["execution"])
    return envelope(
        "prepare",
        True,
        {
            "repos": rows,
            "change_id": snapshot["change_id"],
            "planning_digest": snapshot["planning_digest"],
            "context_digest": snapshot["context_digest"],
            "phase": state.get("phase", "planning"),
        },
        store_uid=snapshot["store_uid"],
        change_uid=snapshot["change_uid"],
        execution_id=config["execution"],
    )


def action_run_repo(config: dict, context) -> dict:
    root = _control_root(config)
    store, run_dir, snapshot = _load_execution(root, config)
    execution_id = config["execution"]
    manifest = snapshot["manifest"]
    repo_id = _norm_item(config.get("repo") or context.item)
    if not repo_id:
        raise SpecRunwayActionError(
            "repo-unknown",
            envelope(
                "run-repo",
                False,
                {},
                error={
                    "code": "repo-unknown",
                    "message": "run-repo requires repo or item",
                    "retryable": False,
                },
            ),
        )
    entry = _repo_row(manifest, repo_id)
    local_cfg = load_local_config(root)
    repo_cfg = local_cfg["repos"].get(repo_id) or {}
    repo_path = Path(repo_cfg.get("path") or "")
    if not (repo_path / ".git").exists():
        raise SpecRunwayActionError(
            "repo-not-git",
            envelope(
                "run-repo",
                False,
                {},
                error={
                    "code": "repo-not-git",
                    "message": f"configured repo missing .git: {repo_path}",
                    "retryable": False,
                },
            ),
        )

    worktree = run_dir / "worktrees" / repo_id
    if not worktree.is_dir():
        worktree = create_worktree(
            repo_path, snapshot["repos"][repo_id]["base_oid"], run_dir, repo_id
        )

    from specrunway.recovery import reusable_result

    reused = reusable_result(
        store, snapshot, repo_id, {rid: dict(cfg) for rid, cfg in local_cfg["repos"].items()}
    )
    if reused is not None:
        return envelope(
            "run-repo",
            True,
            reused,
            store_uid=snapshot["store_uid"],
            change_uid=snapshot["change_uid"],
            execution_id=execution_id,
            warnings=["reused verified result from an earlier attempt"],
        )

    state = store.read_state(execution_id)
    budget = _budget(manifest)
    budgets = dict(state.get("budgets") or {})
    repo_budget = dict(budgets.get(repo_id) or {})
    attempt = int(repo_budget.get("attempts_used", 0)) + 1
    if attempt > budget["repo_max_attempts"]:
        _block(store, execution_id, f"repo budget exhausted for {repo_id}")
        raise SpecRunwayActionError(
            "budget-exhausted",
            envelope(
                "run-repo",
                False,
                {"repo_id": repo_id, "max_attempts": budget["repo_max_attempts"]},
                store_uid=snapshot["store_uid"],
                change_uid=snapshot["change_uid"],
                execution_id=execution_id,
                error={
                    "code": "budget-exhausted",
                    "message": (
                        f"{repo_id} already used {attempt - 1} of "
                        f"{budget['repo_max_attempts']} attempts"
                    ),
                    "retryable": False,
                },
            ),
        )
    if _elapsed_minutes(state["created_at"]) > budget["total_minutes"]:
        _block(store, execution_id, "total time budget exhausted")
        raise SpecRunwayActionError(
            "budget-exhausted",
            envelope(
                "run-repo",
                False,
                {"repo_id": repo_id, "total_minutes": budget["total_minutes"]},
                store_uid=snapshot["store_uid"],
                change_uid=snapshot["change_uid"],
                execution_id=execution_id,
                error={
                    "code": "budget-exhausted",
                    "message": (
                        f"execution exceeded the {budget['total_minutes']} minute total budget"
                    ),
                    "retryable": False,
                },
            ),
        )
    change_path = (
        Path(local_cfg["store"]["path"]) / "openspec" / "changes" / snapshot["change_id"]
    )

    def bump_budget() -> None:
        newest = store.read_state(execution_id)

        def mutate(next_state: dict) -> None:
            next_budgets = dict(next_state.get("budgets") or {})
            next_budgets[repo_id] = {"attempts_used": attempt}
            next_state["budgets"] = next_budgets

        store.update_state(execution_id, mutate, newest["revision"])

    bump_budget()

    from specrunway.bridge.prompt import build_prompt

    prior_result = None
    prior_test = None
    if attempt > 1:
        prior_result = _read_json_or_none(
            run_dir / "results" / repo_id / str(attempt - 1) / "result.json"
        )
        prior_test = _read_json_or_none(
            run_dir / "tests_receipts" / repo_id / f"{attempt - 1}.json"
        )
    prompt_text = build_prompt(
        change_path=change_path,
        manifest=manifest,
        repo_entry=entry,
        snapshot=snapshot,
        rule_files=_rule_file_paths(repo_path),
        dependency_results=_dependency_results(store, execution_id, manifest, entry),
        prior_result=prior_result,
        prior_test=prior_test,
        attempt=attempt,
    )
    prompt_file = run_dir / "prompts" / f"{repo_id}-{attempt}.md"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(prompt_text, encoding="utf-8")

    input_digest = json_digest(
        {
            "prompt": prompt_file.read_text(encoding="utf-8"),
            "base": snapshot["repos"][repo_id]["base_oid"],
        }
    )
    operation = {
        "api_version": "specrunway/v1",
        "operation_key": f"{execution_id}:repo:{repo_id}:{attempt}:{input_digest}",
        "execution_id": execution_id,
        "action": "repo-attempt",
        "scope": {"repo_id": repo_id, "attempt": attempt},
        "intent": {"input_digest": input_digest},
        "status": "pending",
    }
    store.write_intent(execution_id, operation)

    profile = resolve_profile(local_cfg["agent_profile"])
    outcome = launcher_run_agent(
        profile,
        cwd=worktree,
        prompt_file=prompt_file,
        log_dir=run_dir / "logs" / repo_id / str(attempt),
        timeout_seconds=profile.timeout_seconds,
    )
    if outcome.status != "completed":
        store.mark_uncertain(
            execution_id,
            operation["operation_key"],
            {"outcome": dict(outcome), "worktree": str(worktree)},
        )
        raise SpecRunwayActionError(
            f"agent did not complete: {outcome.reason or outcome.status}",
            envelope(
                "run-repo",
                False,
                {"repo_id": repo_id, "attempt": attempt, "outcome": dict(outcome)},
                store_uid=snapshot["store_uid"],
                change_uid=snapshot["change_uid"],
                execution_id=execution_id,
                error={
                    "code": "agent-" + outcome.status,
                    "message": outcome.reason or outcome.status,
                    "retryable": True,
                },
            ),
        )

    try:
        test_profile = resolve_test_profile(entry.get("test_profile") or "unit")
    except ValidationError as exc:
        raise SpecRunwayActionError(
            str(exc),
            envelope(
                "run-repo",
                False,
                {},
                error={
                    "code": exc.code or "unknown-profile",
                    "message": str(exc),
                    "retryable": False,
                },
            ),
        ) from exc
    receipt = run_test_command(
        test_profile.command(),
        worktree,
        run_dir / "logs" / repo_id / str(attempt) / "tests.log",
    )
    receipt_path = run_dir / "tests_receipts" / repo_id / f"{attempt}.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(receipt_path, receipt)

    try:
        accepted = accept_result(
            result_path=worktree / "result.json",
            execution_id=execution_id,
            repo_id=repo_id,
            manifest=manifest,
            snapshot=snapshot,
            repo_checkout=repo_path,
            run_dir=run_dir,
        )
    except (ResultRejected, GroupedValidationError) as exc:
        store.mark_uncertain(
            execution_id, operation["operation_key"], {"status": "rejected", "reason": str(exc)}
        )
        raise SpecRunwayActionError(
            f"result rejected: {exc}",
            envelope(
                "run-repo",
                False,
                {"repo_id": repo_id, "attempt": attempt},
                store_uid=snapshot["store_uid"],
                change_uid=snapshot["change_uid"],
                execution_id=execution_id,
                error={"code": "result-rejected", "message": str(exc), "retryable": True},
            ),
        ) from exc

    stored_ref = persist_result(run_dir, repo_id, accepted)
    store.record_receipt(
        execution_id,
        operation["operation_key"],
        {
            "head_commit": accepted["head_commit"],
            "result_ref": str(stored_ref),
            "tests": receipt["status"],
        },
    )

    def set_results(next_state: dict) -> None:
        rows = dict(next_state.get("results") or {})
        rows[repo_id] = {
            "attempt": attempt,
            "head_commit": accepted["head_commit"],
            "result_ref": str(stored_ref),
            "passed": receipt["status"] == "passed",
            "result_digest": accepted["result_digest"],
        }
        next_state["results"] = rows

    newest = store.read_state(execution_id)
    store.update_state(execution_id, set_results, newest["revision"])

    tasks = [row["task_id"] for row in accepted["tasks"]]
    return envelope(
        "run-repo",
        True,
        {
            "repo_id": repo_id,
            "task_ids": tasks,
            "passed": receipt["status"] == "passed",
            "attempt": attempt,
            "result_ref": str(stored_ref),
            "head_commit": accepted["head_commit"],
        },
        store_uid=snapshot["store_uid"],
        change_uid=snapshot["change_uid"],
        execution_id=execution_id,
        evidence=[str(stored_ref), receipt_path.name],
    )


def _rule_file_paths(repo_path: Path) -> list:
    found = []
    for rule_name in ("AGENTS.md", "CLAUDE.md"):
        rule = repo_path / rule_name
        if rule.is_file():
            found.append(rule)
    return found


def _dependency_results(
    store: FileRunStore, execution_id: str, manifest: dict, entry: dict
) -> dict:
    state = store.read_state(execution_id)
    rows = {}
    for dep in entry.get("depends_on") or []:
        accepted = (state.get("results") or {}).get(dep)
        if accepted:
            rows[dep] = {
                "head_commit": accepted.get("head_commit"),
                "result_digest": accepted.get("result_digest"),
                "passed": bool(accepted.get("passed")),
            }
    return rows


def _run_verification(
    store: FileRunStore,
    run_dir: Path,
    snapshot: dict,
    execution_id: str,
    round_label: str,
) -> list:
    """Trusted tests per repo worktree; persist head + status in run state."""
    manifest = snapshot["manifest"]
    statuses = []
    for repo_id in manifest["repo_order"]:
        entry = _repo_row(manifest, repo_id)
        worktree = run_dir / "worktrees" / repo_id
        if not worktree.is_dir():
            statuses.append({"repo_id": repo_id, "status": "not-started", "head_commit": None})
            continue
        profile = resolve_test_profile(entry.get("test_profile") or "unit")
        receipt = run_test_command(
            profile.command(),
            worktree,
            run_dir / "logs" / repo_id / "verify-rounds" / f"{round_label}.log",
        )
        statuses.append(
            {
                "repo_id": repo_id,
                "status": receipt["status"],
                "exit_code": receipt.get("exit_code"),
                "head_commit": head_oid(worktree),
            }
        )

    def persist(next_state: dict) -> None:
        next_state["verification"] = {row["repo_id"]: row for row in statuses}
        next_state["verify_rounds"] = int(next_state.get("verify_rounds") or 0) + 1

    current = store.read_state(execution_id)
    store.update_state(execution_id, persist, current["revision"])
    return statuses


def action_verify_round(config: dict, context) -> dict:
    root = _control_root(config)
    store, run_dir, snapshot = _load_execution(root, config)
    rounds = int(config.get("round") or 1)
    statuses = _run_verification(
        store, run_dir, snapshot, config["execution"], f"round-{rounds}"
    )
    return envelope(
        "verify-round",
        True,
        {
            "round": rounds,
            "needs_repair": any(row["status"] != "passed" for row in statuses),
            "repos": statuses,
        },
        store_uid=snapshot["store_uid"],
        change_uid=snapshot["change_uid"],
        execution_id=config["execution"],
    )


def action_repair_round(config: dict, context) -> dict:
    """Bounded repair: re-attempt failing repos, stop on no-progress/exhaustion."""
    root = _control_root(config)
    store, run_dir, snapshot = _load_execution(root, config)
    execution_id = config["execution"]
    manifest = snapshot["manifest"]
    budget = _budget(manifest)

    def failing_repos() -> list:
        state = store.read_state(execution_id)
        verification = state.get("verification") or {}
        return [
            repo_id
            for repo_id in manifest["repo_order"]
            if (verification.get(repo_id) or {}).get("status") != "passed"
        ]

    failing = failing_repos()
    if not failing:
        return envelope(
            "repair-round",
            True,
            {"repaired": False, "rounds_used": 0, "repos": []},
            store_uid=snapshot["store_uid"],
            change_uid=snapshot["change_uid"],
            execution_id=execution_id,
        )
    repairs = 0
    while failing and repairs < budget["integration_max_repairs"]:
        repairs += 1
        before = {
            repo_id: (store.read_state(execution_id).get("verification") or {}).get(repo_id, {})
            for repo_id in failing
        }
        for repo_id in failing:
            action_run_repo(
                {
                    "action": "run-repo",
                    "root": str(root),
                    "execution": execution_id,
                    "repo": repo_id,
                },
                context,
            )
        _run_verification(store, run_dir, snapshot, execution_id, f"repair-{repairs}")
        still_failing = failing_repos()
        for repo_id in still_failing:
            row = (store.read_state(execution_id).get("verification") or {}).get(repo_id, {})
            if row.get("head_commit") == before.get(repo_id, {}).get("head_commit"):
                _block(store, execution_id, f"no progress repairing {repo_id}")
                raise SpecRunwayActionError(
                    "no-progress",
                    envelope(
                        "repair-round",
                        False,
                        {"repo_id": repo_id, "rounds_used": repairs},
                        store_uid=snapshot["store_uid"],
                        change_uid=snapshot["change_uid"],
                        execution_id=execution_id,
                        error={
                            "code": "no-progress",
                            "message": (
                                f"{repo_id} failed verification again at the same "
                                "head commit; stop instead of burning the budget"
                            ),
                            "retryable": False,
                        },
                    ),
                )
        failing = still_failing
    if failing:
        _block(store, execution_id, "integration repair budget exhausted")
        raise SpecRunwayActionError(
            "budget-exhausted",
            envelope(
                "repair-round",
                False,
                {"repos": failing, "rounds_used": repairs},
                store_uid=snapshot["store_uid"],
                change_uid=snapshot["change_uid"],
                execution_id=execution_id,
                error={
                    "code": "budget-exhausted",
                    "message": (
                        f"still failing after {repairs} of "
                        f"{budget['integration_max_repairs']} repair rounds: "
                        f"{', '.join(failing)}"
                    ),
                    "retryable": False,
                },
            ),
        )
    return envelope(
        "repair-round",
        True,
        {"repaired": True, "rounds_used": repairs, "repos": []},
        store_uid=snapshot["store_uid"],
        change_uid=snapshot["change_uid"],
        execution_id=execution_id,
    )


def action_collect_summary(config: dict, context) -> dict:
    root = _control_root(config)
    store, _run_dir, snapshot = _load_execution(root, config)
    manifest = snapshot["manifest"]
    state = store.read_state(config["execution"])
    rows = []
    for repo_id in manifest["repo_order"]:
        accepted = (state.get("results") or {}).get(repo_id)
        rows.append(
            {
                "repo_id": repo_id,
                "head_commit": None if not accepted else accepted.get("head_commit"),
                "passed": bool(accepted and accepted.get("passed")),
                "result_digest": None if not accepted else accepted.get("result_digest"),
            }
        )
    gate_status = (state.get("approvals") or {}).get("implementation")
    return envelope(
        "collect-summary",
        True,
        {
            "repos": rows,
            "implementation_approved": bool(
                gate_status and gate_status.get("decision") == "approve"
            ),
            "ready_for_review": False,
        },
        store_uid=snapshot["store_uid"],
        change_uid=snapshot["change_uid"],
        execution_id=config["execution"],
    )


def action_accept_tasks(config: dict, context) -> dict:
    """Single SpecRunway writer flips the mapped tasks.md checkboxes after acceptance."""
    import hashlib

    from specrunway.checkboxes import accept_tasks

    root = _control_root(config)
    store, _run_dir, snapshot = _load_execution(root, config)
    execution_id = config["execution"]
    manifest = snapshot["manifest"]
    state = store.read_state(execution_id)
    results = state.get("results") or {}
    incomplete = [
        repo_id
        for repo_id in manifest["repo_order"]
        if not (results.get(repo_id) or {}).get("passed")
    ]
    if incomplete:
        raise SpecRunwayActionError(
            "results-incomplete",
            envelope(
                "accept-tasks",
                False,
                {"missing": incomplete},
                store_uid=snapshot["store_uid"],
                change_uid=snapshot["change_uid"],
                execution_id=execution_id,
                error={
                    "code": "results-incomplete",
                    "message": f"no passed result yet for {', '.join(incomplete)}",
                    "retryable": False,
                },
            ),
        )
    local_cfg = load_local_config(root)
    tasks_path = (
        Path(local_cfg["store"]["path"])
        / "openspec"
        / "changes"
        / snapshot["change_id"]
        / "tasks.md"
    )
    if not tasks_path.is_file():
        raise SpecRunwayActionError(
            "tasks-missing",
            envelope(
                "accept-tasks",
                False,
                {},
                store_uid=snapshot["store_uid"],
                change_uid=snapshot["change_uid"],
                execution_id=execution_id,
                error={
                    "code": "tasks-missing",
                    "message": f"no tasks.md at {tasks_path}",
                    "retryable": False,
                },
            ),
        )
    task_ids = sorted(
        {
            task_id
            for repo_id in manifest["repo_order"]
            for task_id in _repo_row(manifest, repo_id)["task_ids"]
        }
    )
    before = tasks_path.read_text(encoding="utf-8")
    try:
        after, flipped = accept_tasks(before, task_ids)
    except ValidationError as exc:
        raise SpecRunwayActionError(
            str(exc),
            envelope(
                "accept-tasks",
                False,
                {"task_ids": task_ids},
                store_uid=snapshot["store_uid"],
                change_uid=snapshot["change_uid"],
                execution_id=execution_id,
                error={"code": exc.code, "message": str(exc), "retryable": False},
            ),
        ) from exc
    after_digest = hashlib.sha256(after.encode("utf-8")).hexdigest()
    operation_key = f"{execution_id}:accept-tasks:{after_digest[:16]}"
    recorded = {
        op.get("operation_key")
        for op in store.operations(execution_id)
        if op.get("status") == "recorded"
    }
    if operation_key not in recorded:
        store.write_intent(
            execution_id,
            {
                "operation_key": operation_key,
                "kind": "accept-tasks",
                "before_digest": hashlib.sha256(before.encode("utf-8")).hexdigest(),
            },
        )
        if after != before:
            tasks_path.write_text(after, encoding="utf-8")
        store.record_receipt(
            execution_id,
            operation_key,
            {"after_digest": after_digest, "flipped": flipped, "tasks_path": str(tasks_path)},
        )
    return envelope(
        "accept-tasks",
        True,
        {
            "task_ids": task_ids,
            "flipped": flipped,
            "tasks_digest": after_digest,
        },
        store_uid=snapshot["store_uid"],
        change_uid=snapshot["change_uid"],
        execution_id=execution_id,
        evidence=[str(tasks_path)],
    )


def action_gate_check(config: dict, context) -> dict:
    """Verify an approval receipt exists BEFORE the workflow gate advances."""
    root = _control_root(config)
    store, _run_dir, snapshot = _load_execution(root, config)
    kinds = config.get("kinds") or ["plan"]
    try:
        confirmed = []
        for kind in kinds:
            approval = require_gate(store, config["execution"], kind)
            confirmed.append({"kind": kind, "subject_digest": approval["subject_digest"]})
    except GateError as exc:
        raise SpecRunwayActionError(
            f"gate refuses to advance: {exc.message}",
            envelope(
                "gate-check",
                False,
                {"kinds": list(kinds)},
                store_uid=snapshot["store_uid"],
                change_uid=snapshot["change_uid"],
                execution_id=config["execution"],
                error={"code": exc.code, "message": exc.message, "retryable": False},
            ),
        ) from exc
    return envelope(
        "gate-check",
        True,
        {"confirmed": confirmed},
        store_uid=snapshot["store_uid"],
        change_uid=snapshot["change_uid"],
        execution_id=config["execution"],
    )


def action_complete(config: dict, context) -> dict:
    """Final reviewed run finishes at ready_for_review (never auto-archives)."""
    root = _control_root(config)
    store, _run_dir, snapshot = _load_execution(root, config)
    manifest = snapshot["manifest"]
    state = store.read_state(config["execution"])
    results = state.get("results") or {}
    verification = state.get("verification") or {}
    unproven = [
        repo_id
        for repo_id in manifest["repo_order"]
        if not (results.get(repo_id) or {}).get("passed")
        or (verification.get(repo_id) or {}).get("status") != "passed"
    ]
    if unproven:
        raise SpecRunwayActionError(
            "verification-failed",
            envelope(
                "complete",
                False,
                {"repos": unproven},
                store_uid=snapshot["store_uid"],
                change_uid=snapshot["change_uid"],
                execution_id=config["execution"],
                error={
                    "code": "verification-failed",
                    "message": f"failed verification cannot become ready: {', '.join(unproven)}",
                    "retryable": False,
                },
            ),
        )

    def mutate(next_state: dict) -> None:
        next_state["phase"] = "ready_for_review"

    current = store.read_state(config["execution"])
    store.update_state(config["execution"], mutate, current["revision"])
    return envelope(
        "complete",
        True,
        {"phase": "ready_for_review", "archived": False},
        store_uid=snapshot["store_uid"],
        change_uid=snapshot["change_uid"],
        execution_id=config["execution"],
    )


def action_note(config: dict, context) -> dict:
    return envelope(
        "note",
        True,
        {"label": str(config.get("label") or "note")},
        execution_id=str(config.get("execution") or ""),
    )


_DISPATCH = {
    "prepare": action_prepare,
    "run-repo": action_run_repo,
    "verify-round": action_verify_round,
    "collect-summary": action_collect_summary,
    "accept-tasks": action_accept_tasks,
    "repair-round": action_repair_round,
    "gate-check": action_gate_check,
    "complete": action_complete,
    "note": action_note,
}


def dispatch_action(action: str, config: dict, context) -> dict:
    handler = _DISPATCH.get(action)
    if handler is None:
        raise SpecRunwayActionError(
            f"Unknown specrunway action {action!r}",
            envelope(
                action,
                False,
                {},
                error={
                    "code": "unknown-action",
                    "message": f"unknown specrunway action {action!r}",
                    "retryable": False,
                },
            ),
        )
    return handler(config, context)


__all__ = [
    "SpecRunwayActionError",
    "action_collect_summary",
    "action_complete",
    "action_gate_check",
    "action_prepare",
    "action_run_repo",
    "action_verify_round",
    "dispatch_action",
    "envelope",
]
