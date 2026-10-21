"""SpecRunway CLI: local v1 command surface (``doctor`` diagnostic ships first)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .doctor import find_control_root, run_doctor


def _error_payload(action: str, exc: Exception) -> dict:
    code = getattr(exc, "code", None)
    errors = getattr(exc, "errors", None)
    body = {"code": code or type(exc).__name__, "message": str(exc)}
    if errors:
        body["errors"] = errors
    return _specrunway_envelope(action=action, ok=False, data={}, error=body)


def _emit(payload: dict, as_json: bool, line: str, err: bool = False) -> None:
    stream = sys.stderr if err else sys.stdout
    if as_json:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
    else:
        stream.write(line)


def _fail_cli(payload: dict, as_json: bool, prefix: str) -> int:
    error = payload["error"]
    _emit(
        payload,
        as_json,
        f"{prefix}: [{error['code']}] {error['message']}\n",
        err=not as_json,
    )
    return 1


def _envelope(ok: bool, **body) -> dict:
    return {"api_version": "specrunway/v1", "ok": bool(ok), **body}


def cmd_doctor(args: argparse.Namespace) -> int:
    report = run_doctor(root_dir=args.root)
    if args.json:
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        for finding in report["data"]["findings"]:
            sys.stdout.write(
                f"[{finding['severity']}] {finding['check']}: {finding['message']}\n"
            )
        sys.stdout.write(f"doctor ok: {str(report['ok']).lower()}\n")
    return 0 if report["ok"] else 1


def _specrunway_envelope(**body) -> dict:
    return {"api_version": "specrunway/v1", **body}


def _error_envelope(action: str, exc: Exception) -> dict:
    code = getattr(exc, "code", None)
    errors = getattr(exc, "errors", None)
    body = {"code": code or type(exc).__name__, "message": str(exc)}
    if errors:
        body["errors"] = errors
    return _specrunway_envelope(action=action, ok=False, data={}, error=body)


def cmd_plan(args: argparse.Namespace) -> int:
    """Create/accept planning artifacts + machine-validated routing."""
    from .planning import plan

    control_root = Path(args.root).resolve() if args.root else find_control_root(Path.cwd())
    if control_root is None:
        payload = _error_envelope(
            "plan",
            RuntimeError(
                "no control checkout found; run specrunway from the control workspace"
            ),
        )
        code = payload["error"]["code"]
        message = payload["error"]["message"]
        if args.json:
            json.dump(payload, sys.stdout, indent=2, sort_keys=True)
            sys.stdout.write("\n")
        else:
            sys.stderr.write(f"specrunway plan: [{code}] {message}\n")
        return 1
    try:
        outcome = plan(
            control_root=control_root,
            store_id=args.store or "",
            change_id=args.change_id,
            request_path=Path(args.request).resolve() if args.request else None,
            manifest_path=Path(args.manifest).resolve() if args.manifest else None,
        )
    except Exception as exc:  # noqa: BLE001 (CLI boundary; stable envelope required)
        payload = _error_envelope("plan", exc)
        if args.json:
            json.dump(payload, sys.stdout, indent=2, sort_keys=True)
            sys.stdout.write("\n")
        else:
            error = payload["error"]
            sys.stderr.write(f"specrunway plan: [{error['code']}] {error['message']}\n")
        return 1
    payload = _specrunway_envelope(
        action="plan",
        ok=True,
        data={
            "change_id": outcome.change_id,
            "change_path": outcome.change_path,
            "store_id": outcome.store_id,
            "planning_complete": outcome.planning_complete,
            "task_ids": outcome.task_ids,
            "manifest_path": outcome.manifest_path,
            "generated": outcome.generated,
        },
        warnings=[],
    )
    if args.json:
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(
            f"plan ok: {outcome.change_id} "
            f"(tasks {', '.join(outcome.task_ids) or 'none'} at {outcome.change_path})\n"
        )
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    """Record the operator's own confirmation bound to the frozen subject digest."""
    from specrunway.approvals import record_approval
    from specrunway.models.common import ValidationError
    from specrunway.runstore import FileRunStore, RunStoreError

    control_root = Path(args.root).resolve() if args.root else find_control_root(Path.cwd())
    if control_root is None:
        return _fail_cli(
            _error_envelope("approve", RuntimeError("no control checkout found")),
            args.json,
            "specrunway approve",
        )
    specrunway_root = control_root / ".specrunway"
    store = FileRunStore(specrunway_root)
    try:
        snapshot = store.run_dir(args.execution).joinpath("snapshot.json")
        if not snapshot.is_file():
            raise ValidationError(
                "snapshot-missing", f"no frozen snapshot.json for execution {args.execution}"
            )
        from specrunway.runstore import _read_json_or_none

        frozen = _read_json_or_none(snapshot)
        if frozen is None:
            raise ValidationError(
                "snapshot-missing", f"snapshot.json unreadable for {args.execution}"
            )
        # record_approval recomputes the binding subject digest from frozen
        # content (plan: planning digest; implementation: accepted results
        # tree), so no caller-supplied digest is consumed here.
        record = record_approval(
            store=store,
            execution_id=args.execution,
            kind=args.kind,
            snapshot=frozen,
            actor=args.actor,
            decision=args.decision,
        )
    except RunStoreError as exc:
        return _fail_cli(_error_envelope("approve", exc), args.json, "specrunway approve")
    except ValidationError as exc:
        return _fail_cli(_error_envelope("approve", exc), args.json, "specrunway approve")
    except Exception as exc:  # noqa: BLE001
        return _fail_cli(_error_envelope("approve", exc), args.json, "specrunway approve")
    payload = _specrunway_envelope(
        action="approve",
        ok=True,
        data={
            "execution_id": args.execution,
            "kind": record["kind"],
            "decision": record["decision"],
            "subject_digest": record["subject_digest"],
            "scope": record["scope"],
            "actor": record["actor"],
            "auth_level": record["auth_level"],
            "timestamp": record["timestamp"],
        },
        warnings=[],
    )
    _emit(
        payload,
        args.json,
        f"approve ok: {record['kind']} {record['decision']} "
        f"{record['subject_digest'][:12]}… by {record['actor']}\n",
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Freeze/claim an execution and drive it through ordered repositories."""
    from specrunway.runner import (
        RunError,
        continue_execution,
        prepare_execution,
        start_execution,
    )

    control_root = Path(args.root).resolve() if args.root else find_control_root(Path.cwd())
    if control_root is None:
        return _fail_cli(
            _error_envelope("run", RuntimeError("no control checkout found")),
            args.json,
            "specrunway run",
        )
    try:
        execution_id = args.execution
        if args.continue_run:
            if not execution_id:
                raise RunError("execution-required", "--continue requires --execution")
            payload = continue_execution(control_root, execution_id)
        else:
            if execution_id:
                raise RunError(
                    "execution-conflict",
                    "pass --change to start a new execution or --continue to resume",
                )
            prepared = prepare_execution(control_root, args.change)
            execution_id = prepared["execution_id"]
            payload = start_execution(control_root, execution_id)
    except Exception as exc:  # noqa: BLE001 (CLI boundary; stable envelope required)
        return _fail_cli(_error_envelope("run", exc), args.json, "specrunway run")
    status = payload.get("status")
    paused_step = payload.get("current_step_id") if status == "paused" else None
    next_hint = "review the accepted results; archive stays an explicit command"
    if paused_step == "plan-gate":
        next_hint = (
            "record the plan approval (`specrunway approve --kind plan`) then run "
            "`specrunway run --execution <id> --continue`"
        )
    elif status == "paused":
        next_hint = (
            "record the implementation approval (`specrunway approve --kind implementation`) "
            "then run `specrunway run --execution <id> --continue`"
        )
    envelope = _specrunway_envelope(
        action="run",
        ok=True,
        data={
            "execution_id": execution_id,
            "workflow_id": payload.get("workflow_id"),
            "native_run_id": payload.get("run_id"),
            "native_status": status,
            "paused_step_id": paused_step,
            "next": next_hint,
        },
        warnings=[],
    )
    hint = f" (paused at {paused_step})" if paused_step else ""
    _emit(
        envelope,
        args.json,
        f"run {status}: execution {execution_id}{hint}\n",
    )
    return 0


def _control_root_for(args: argparse.Namespace) -> Path | None:
    return Path(args.root).resolve() if args.root else find_control_root(Path.cwd())


def cmd_init(args: argparse.Namespace) -> int:
    """Idempotent control bootstrap: Store, Specify workspace, bundled step."""
    import subprocess

    from specrunway.models import load_local_config
    from specrunway.openspec_adapter import OpenSpecAdapter
    from specrunway.toolresolvers import resolve_tool_bin

    root = _control_root_for(args)
    if root is None:
        return _fail_cli(
            _error_envelope(
                "init",
                RuntimeError("no control checkout found; pass --root or run inside it"),
            ),
            args.json,
            "specrunway init",
        )
    try:
        config = load_local_config(root)
    except FileNotFoundError:
        return _fail_cli(
            _error_envelope(
                "init",
                _validation_error(
                    "local-yaml-missing",
                    f"write {root / 'local.yaml'} (store, repos, agent_profile, "
                    "integration_profiles) before running init",
                ),
            ),
            args.json,
            "specrunway init",
        )
    except Exception as exc:  # noqa: BLE001
        return _fail_cli(_error_envelope("init", exc), args.json, "specrunway init")
    specify_initialized = False
    try:
        openspec_bin = resolve_tool_bin(root, None, "openspec")
        specify_bin = resolve_tool_bin(root, None, "specify")
        store_path = Path(config["store"]["path"])
        store_path.mkdir(parents=True, exist_ok=True)
        adapter = OpenSpecAdapter(
            store_path=store_path,
            store_id=config["store"]["id"],
            openspec_bin=openspec_bin,
        )
        adapter.store_setup()
        if not (root / ".specify").is_dir():
            done = subprocess.run(
                [
                    specify_bin,
                    "init",
                    "--here",
                    "--force",
                    "--non-interactive",
                    "--ignore-agent-tools",
                ],
                cwd=str(root),
                capture_output=True,
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
            )
            if done.returncode != 0:
                raise _validation_error(
                    "specify-init-failed",
                    f"specify init failed (exit {done.returncode}): "
                    f"{(done.stderr or done.stdout)[-400:]}",
                )
            specify_initialized = True
        step_path = Path(__file__).resolve().parent / "step_package"
        installed_step = root / ".specify" / "workflows" / "steps" / "specrunway" / "step.yml"
        step = None
        if not installed_step.is_file():
            step = subprocess.run(
                [
                    specify_bin,
                    "workflow",
                    "step",
                    "add",
                    "specrunway",
                    "--dev",
                    str(step_path),
                ],
                cwd=str(root),
                capture_output=True,
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
            )
        if step is not None and step.returncode != 0:
            raise _validation_error(
                "step-install-failed",
                f"specify step install failed (exit {step.returncode}): "
                f"{(step.stderr or step.stdout)[-400:]}",
            )
    except Exception as exc:  # noqa: BLE001
        return _fail_cli(_error_envelope("init", exc), args.json, "specrunway init")

    report = run_doctor(root_dir=str(root))
    payload = _specrunway_envelope(
        action="init",
        ok=bool(report["ok"]),
        data={
            "control_root": str(root),
            "store_id": config["store"]["id"],
            "store_path": config["store"]["path"],
            "specify_initialized": specify_initialized,
            "step_package": str(step_path),
            "doctor_ok": bool(report["ok"]),
            "findings": report["data"]["findings"],
        },
        warnings=[],
    )
    if not report["ok"]:
        payload["error"] = {
            "code": "doctor-failed",
            "message": "init completed but doctor reported errors; fix them before plan/run",
            "retryable": False,
        }
    _emit(
        payload,
        args.json,
        f"init {'ok' if report['ok'] else 'incomplete'}: {root} "
        f"(store {config['store']['id']}, specify "
        f"{'initialized' if specify_initialized else 'already present'})\n",
    )
    return 0 if report["ok"] else 1


def _validation_error(code: str, message: str) -> Exception:
    from specrunway.models.common import ValidationError

    return ValidationError(code, message)


def cmd_status(args: argparse.Namespace) -> int:
    from specrunway.recovery import execution_status

    root = _control_root_for(args)
    if root is None:
        return _fail_cli(
            _error_envelope("status", RuntimeError("no control checkout found")),
            args.json,
            "specrunway status",
        )
    try:
        data = execution_status(root, args.execution)
    except Exception as exc:  # noqa: BLE001
        return _fail_cli(_error_envelope("status", exc), args.json, "specrunway status")
    payload = _specrunway_envelope(action="status", ok=True, data=data, warnings=[])
    _emit(
        payload,
        args.json,
        f"status {data['phase']}: execution {args.execution} "
        f"(native run {data['native_run_id']})\n",
    )
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    from specrunway.recovery import resume_execution

    root = _control_root_for(args)
    if root is None:
        return _fail_cli(
            _error_envelope("resume", RuntimeError("no control checkout found")),
            args.json,
            "specrunway resume",
        )
    try:
        outcome = resume_execution(root, args.execution)
    except Exception as exc:  # noqa: BLE001
        return _fail_cli(_error_envelope("resume", exc), args.json, "specrunway resume")
    payload = _specrunway_envelope(
        action="resume",
        ok=True,
        data={
            "execution_id": args.execution,
            "native_run_id": outcome.get("run_id"),
            "native_status": outcome.get("status"),
            "paused_step_id": outcome.get("current_step_id"),
        },
        warnings=[],
    )
    _emit(
        payload,
        args.json,
        f"resume {outcome.get('status')}: execution {args.execution}\n",
    )
    return 0


def cmd_recover(args: argparse.Namespace) -> int:
    from specrunway.recovery import recover_execution

    root = _control_root_for(args)
    if root is None:
        return _fail_cli(
            _error_envelope("recover", RuntimeError("no control checkout found")),
            args.json,
            "specrunway recover",
        )
    try:
        outcome = recover_execution(root, args.execution)
    except Exception as exc:  # noqa: BLE001
        return _fail_cli(_error_envelope("recover", exc), args.json, "specrunway recover")
    payload = _specrunway_envelope(
        action="recover",
        ok=True,
        data={
            "execution_id": args.execution,
            "native_run_id": outcome.get("run_id"),
            "native_status": outcome.get("status"),
            "paused_step_id": outcome.get("current_step_id"),
            "reconciled_archive": bool(outcome.get("reconciled_archive")),
        },
        warnings=[],
    )
    _emit(
        payload,
        args.json,
        f"recover {outcome.get('status')}: execution {args.execution}\n",
    )
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    from specrunway.archive import archive_execution

    root = _control_root_for(args)
    if root is None:
        return _fail_cli(
            _error_envelope("archive", RuntimeError("no control checkout found")),
            args.json,
            "specrunway archive",
        )
    try:
        outcome = archive_execution(
            root,
            args.execution,
            policy=args.policy,
            confirm_validated=args.confirm_validated,
        )
    except Exception as exc:  # noqa: BLE001
        return _fail_cli(_error_envelope("archive", exc), args.json, "specrunway archive")
    payload = _specrunway_envelope(
        action="archive",
        ok=True,
        data={**outcome, "execution_id": args.execution},
        warnings=[],
    )
    _emit(
        payload,
        args.json,
        f"archive ok: {outcome.get('archived_as')} (policy {outcome.get('policy')})\n",
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="specrunway",
        description="Central Store Coordinator (local v1).",
    )
    parser.add_argument("--version", action="version", version=f"specrunway {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    doc = sub.add_parser("doctor", help="Check control checkout, Store, and repo wiring")
    doc.add_argument(
        "--json", action="store_true", help="Emit the specrunway/v1 envelope as JSON"
    )
    doc.add_argument(
        "--root", help="Explicit control checkout root (default: walk up from cwd)"
    )
    doc.set_defaults(func=cmd_doctor)

    init_parser = sub.add_parser(
        "init", help="Prepare the control checkout (Store, Specify, step) idempotently"
    )
    init_parser.add_argument("--root", help="Explicit control root (default: walk up from cwd)")
    init_parser.add_argument(
        "--json", action="store_true", help="Emit specrunway/v1 JSON envelope"
    )
    init_parser.set_defaults(func=cmd_init)

    for name, help_text, handler in (
        ("status", "Show execution status", cmd_status),
        ("resume", "Resume a paused/failed execution", cmd_resume),
        ("recover", "Reconcile an interrupted execution", cmd_recover),
    ):
        sub_parser = sub.add_parser(name, help=help_text)
        sub_parser.add_argument("--execution", required=True, help="Execution UUID")
        sub_parser.add_argument(
            "--root", help="Explicit control root (default: walk up from cwd)"
        )
        sub_parser.add_argument(
            "--json", action="store_true", help="Emit specrunway/v1 JSON envelope"
        )
        sub_parser.set_defaults(func=handler)

    archive_parser = sub.add_parser("archive", help="Archive a completed change explicitly")
    archive_parser.add_argument("--execution", required=True, help="Execution UUID")
    archive_parser.add_argument(
        "--policy",
        choices=["merged_commits", "validated_commits"],
        help="Explicit completion policy (default: manifest policy / merged_commits)",
    )
    archive_parser.add_argument(
        "--confirm-validated",
        action="store_true",
        help="Confirm validated_commits (no main-branch merge claim)",
    )
    archive_parser.add_argument(
        "--root", help="Explicit control root (default: walk up from cwd)"
    )
    archive_parser.add_argument(
        "--json", action="store_true", help="Emit specrunway/v1 JSON envelope"
    )
    archive_parser.set_defaults(func=cmd_archive)

    run_parser = sub.add_parser(
        "run", help="Run an approved change across ordered repositories"
    )
    run_parser.add_argument("--change", help="Change id to freeze into a new execution")
    run_parser.add_argument("--execution", help="Existing execution UUID")
    run_parser.add_argument(
        "--continue",
        dest="continue_run",
        action="store_true",
        help="Resume the paused run after the implementation approval receipt exists",
    )
    run_parser.add_argument("--root", help="Explicit control root (default: walk up from cwd)")
    run_parser.add_argument(
        "--json", action="store_true", help="Emit specrunway/v1 JSON envelope"
    )
    run_parser.set_defaults(func=cmd_run)

    plan_parser = sub.add_parser(
        "plan", help="Create/refresh planning artifacts for a central change"
    )
    plan_parser.add_argument("change_id", help="Change id (OpenSpec change name)")
    plan_parser.add_argument("--store", help="Store id from local.yaml (required mapping)")
    plan_parser.add_argument("--request", help="Request markdown file for artifact generation")
    plan_parser.add_argument(
        "--manifest", help="Routing manifest YAML (validated at plan time)"
    )
    plan_parser.add_argument("--root", help="Explicit control root (default: walk up from cwd)")
    plan_parser.add_argument(
        "--json", action="store_true", help="Emit specrunway/v1 JSON envelope"
    )
    plan_parser.set_defaults(func=cmd_plan)

    approve_parser = sub.add_parser(
        "approve", help="Record a self_asserted approval bound to a frozen subject digest"
    )
    approve_parser.add_argument("--execution", required=True, help="Execution UUID")
    approve_parser.add_argument(
        "--kind", required=True, choices=["plan", "implementation"], help="Approval kind"
    )
    approve_parser.add_argument(
        "--actor", required=True, help="Operator recording the approval"
    )
    approve_parser.add_argument(
        "--decision", choices=["approve", "reject"], default="approve", help="Decision"
    )
    approve_parser.add_argument(
        "--root", help="Explicit control root (default: walk up from cwd)"
    )
    approve_parser.add_argument(
        "--json", action="store_true", help="Emit specrunway/v1 JSON envelope"
    )
    approve_parser.set_defaults(func=cmd_approve)

    return parser


def main(argv: list | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BrokenPipeError:  # pragma: no cover - CLI plumbing
        return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
