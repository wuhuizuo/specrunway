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
    report = run_doctor(root_dir=args.root, probe_agent=not args.no_agent_probe)
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


def _confirm_approval(execution_id: str, kind: str, actor: str) -> None:
    """Ask y/N on the operator's terminal; never consume a piped stdin."""
    from specrunway.observability import ObservabilityError

    stdin = sys.stdin
    is_tty = getattr(stdin, "isatty", lambda: False)()
    if not is_tty:
        raise ObservabilityError(
            "not-a-tty", "approve --interactive requires a terminal on stdin"
        )
    sys.stderr.write(
        f"Approve {kind} for execution {execution_id} as {actor}? [y/N] "
    )
    sys.stderr.flush()
    try:
        answer = stdin.readline()
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if str(answer).strip().lower() not in {"y", "yes"}:
        raise ObservabilityError("approval-declined", "approval declined; no receipt recorded")


def cmd_approve(args: argparse.Namespace) -> int:
    """Record the operator's own confirmation bound to the frozen subject digest."""
    from specrunway.approvals import record_approval
    from specrunway.models.common import ValidationError
    from specrunway.observability import ObservabilityError, resolve_pending_execution
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
        execution_id = args.execution
        kind = args.kind
        if args.pending:
            if execution_id:
                raise ValidationError(
                    "approval-selector", "pass either --execution or --pending, not both"
                )
            resolved = resolve_pending_execution(control_root)
            execution_id = resolved["execution_id"]
            pending_kind = resolved.get("pending_gate")
            if kind and pending_kind and kind != pending_kind:
                raise ValidationError(
                    "approval-kind-conflict",
                    f"execution {execution_id} waits at {pending_kind!r}, not {kind!r}",
                )
            kind = kind or pending_kind
        elif not execution_id:
            raise ValidationError(
                "execution-required", "pass --execution or --pending"
            )
        if not kind:
            raise ValidationError(
                "approval-kind-required", "pass --kind {plan,implementation}"
            )
        if kind not in ("plan", "implementation"):
            raise ValidationError("approval-kind", f"unsupported approval kind {kind!r}")
        if args.interactive:
            _confirm_approval(execution_id, kind, args.actor)
        snapshot = store.run_dir(execution_id).joinpath("snapshot.json")
        if not snapshot.is_file():
            raise ValidationError(
                "snapshot-missing", f"no frozen snapshot.json for execution {execution_id}"
            )
        from specrunway.runstore import _read_json_or_none

        frozen = _read_json_or_none(snapshot)
        if frozen is None:
            raise ValidationError(
                "snapshot-missing", f"snapshot.json unreadable for {execution_id}"
            )
        # record_approval recomputes the binding subject digest from frozen
        # content (plan: planning digest; implementation: accepted results
        # tree), so no caller-supplied digest is consumed here.
        record = record_approval(
            store=store,
            execution_id=execution_id,
            kind=kind,
            snapshot=frozen,
            actor=args.actor,
            decision=args.decision,
        )
    except RunStoreError as exc:
        return _fail_cli(_error_envelope("approve", exc), args.json, "specrunway approve")
    except (ValidationError, ObservabilityError) as exc:
        return _fail_cli(_error_envelope("approve", exc), args.json, "specrunway approve")
    except Exception as exc:  # noqa: BLE001
        return _fail_cli(_error_envelope("approve", exc), args.json, "specrunway approve")
    payload = _specrunway_envelope(
        action="approve",
        ok=True,
        data={
            "execution_id": execution_id,
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
            payload = continue_execution(
                control_root, execution_id, progress_stream=sys.stderr
            )
        else:
            if execution_id:
                raise RunError(
                    "execution-conflict",
                    "pass --change to start a new execution or --continue to resume",
                )
            prepared = prepare_execution(control_root, args.change)
            execution_id = prepared["execution_id"]
            payload = start_execution(
                control_root, execution_id, progress_stream=sys.stderr
            )
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
    from specrunway.bootstrap import initialize_control
    from specrunway.models import load_local_config

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
    try:
        initialized = initialize_control(root, config)
    except Exception as exc:  # noqa: BLE001
        return _fail_cli(_error_envelope("init", exc), args.json, "specrunway init")

    # Bootstrap checks wiring only; `specrunway doctor` runs the agent preflight.
    report = run_doctor(root_dir=str(root), probe_agent=False)
    payload = _specrunway_envelope(
        action="init",
        ok=bool(report["ok"]),
        data={
            "control_root": str(root),
            "store_id": config["store"]["id"],
            "store_path": config["store"]["path"],
            "specify_initialized": initialized["specify_initialized"],
            "step_package": initialized["step_package"],
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
        f"{'initialized' if initialized['specify_initialized'] else 'already present'})\n",
    )
    return 0 if report["ok"] else 1


def cmd_wizard(args: argparse.Namespace) -> int:
    """Guided first use: configure the control checkout and draft a request."""
    from specrunway.wizard import WizardIO, run_wizard

    root = _control_root_for(args)
    if root is None:
        root = Path.cwd().resolve()
    io = WizardIO(
        input_fn=input,
        output=sys.stderr if args.json else sys.stdout,
    )
    try:
        result = run_wizard(
            root,
            io=io,
            reconfigure=args.reconfigure,
            change_id=args.change,
            description=args.description,
            request_path=args.request,
            manifest_path=args.manifest,
            skip_init=args.skip_init,
            skip_plan=args.skip_plan,
            force=args.force,
        )
    except Exception as exc:  # noqa: BLE001 (CLI boundary; stable envelope required)
        return _fail_cli(_error_envelope("wizard", exc), args.json, "specrunway wizard")
    payload = _specrunway_envelope(
        action="wizard", ok=True, data=result, warnings=[]
    )
    if args.json:
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    elif result["planned"]:
        sys.stdout.write(
            f"wizard ok: {result['change_id']} planned at {result['change_path']}\n"
        )
        for hint in result["next"]:
            sys.stdout.write(f"  next: {hint}\n")
    else:
        sys.stdout.write(
            f"wizard ok: control checkout ready at {result['control_root']}\n"
        )
        if result.get("request_path"):
            sys.stdout.write(f"  request: {result['request_path']}\n")
    return 0


def _validation_error(code: str, message: str) -> Exception:
    from specrunway.models.common import ValidationError

    return ValidationError(code, message)


def cmd_status(args: argparse.Namespace) -> int:
    from specrunway.observability import (
        format_status_transition,
        iter_status_transitions,
    )
    from specrunway.recovery import execution_status

    root = _control_root_for(args)
    if root is None:
        return _fail_cli(
            _error_envelope("status", RuntimeError("no control checkout found")),
            args.json,
            "specrunway status",
        )
    if args.follow:
        try:
            for event in iter_status_transitions(root, args.execution):
                if args.json:
                    json.dump(
                        _specrunway_envelope(
                            action="status", ok=True, data=event, warnings=[]
                        ),
                        sys.stdout,
                        indent=2,
                        sort_keys=True,
                    )
                    sys.stdout.write("\n")
                else:
                    sys.stdout.write(format_status_transition(event) + "\n")
                sys.stdout.flush()
        except KeyboardInterrupt:
            return 0
        except Exception as exc:  # noqa: BLE001
            return _fail_cli(
                _error_envelope("status", exc), args.json, "specrunway status"
            )
        return 0
    try:
        data = execution_status(root, args.execution)
    except Exception as exc:  # noqa: BLE001
        return _fail_cli(_error_envelope("status", exc), args.json, "specrunway status")
    payload = _specrunway_envelope(action="status", ok=True, data=data, warnings=[])
    step = data.get("current_step") or {}
    step_detail = ""
    if step.get("step_id"):
        elapsed = step.get("elapsed_seconds")
        duration = f" for {elapsed:.1f}s" if isinstance(elapsed, (int, float)) else ""
        step_detail = f" step {step['step_id']} {step.get('status') or 'unknown'}{duration}"
        if step.get("log_path"):
            step_detail += f" log {step['log_path']}"
    detail = ""
    failure = data.get("last_failure")
    if failure:
        message = str(failure.get("message") or "").strip()
        message_detail = (
            f" {message}" if message and message != failure.get("code") else ""
        )
        details = failure.get("details") or {}
        numbers = ", ".join(
            f"{key}={value}"
            for key, value in sorted(details.items())
            if isinstance(value, (int, float, str, bool))
        )
        numbers_detail = f" ({numbers})" if numbers else ""
        detail = (
            f"; last failed step {failure.get('step_id') or 'unknown'} "
            f"[{failure.get('code')}]{message_detail}{numbers_detail} "
            f"log {failure.get('log_path') or 'unavailable'}"
        )
    _emit(
        payload,
        args.json,
        f"status {data['phase']}: execution {args.execution}"
        f"{step_detail} (native run {data['native_run_id']}){detail}\n",
    )
    return 0


def cmd_executions(args: argparse.Namespace) -> int:
    """List executions and the gate each one waits at."""
    from specrunway.observability import list_executions, pending_executions

    root = _control_root_for(args)
    if root is None:
        return _fail_cli(
            _error_envelope("executions", RuntimeError("no control checkout found")),
            args.json,
            "specrunway executions",
        )
    try:
        rows = list_executions(root)
        pending = [row["execution_id"] for row in pending_executions(root)]
    except Exception as exc:  # noqa: BLE001
        return _fail_cli(
            _error_envelope("executions", exc), args.json, "specrunway executions"
        )
    payload = _specrunway_envelope(
        action="executions",
        ok=True,
        data={"executions": rows, "pending": pending},
        warnings=[],
    )
    if args.json:
        _emit(payload, True, "")
    elif not rows:
        sys.stdout.write("executions: none\n")
    else:
        for row in rows:
            gate = row.get("pending_gate") or "none"
            owner = " active" if row.get("active_owner") else ""
            sys.stdout.write(
                f"{row['execution_id']} {row.get('phase')} "
                f"pending={gate} change={row.get('change_id') or 'unknown'}{owner}\n"
            )
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    """Locate and optionally tail agent, test, and native logs."""
    from specrunway.observability import (
        ObservabilityError,
        enumerate_logs,
        iter_log_chunks,
    )

    root = _control_root_for(args)
    if root is None:
        return _fail_cli(
            _error_envelope("logs", RuntimeError("no control checkout found")),
            args.json,
            "specrunway logs",
        )
    kind = None if args.kind == "all" else args.kind
    if args.follow:
        try:
            for chunk in iter_log_chunks(
                root,
                args.execution,
                kind=kind,
                repo_id=args.repo,
                attempt=args.attempt,
            ):
                if args.json:
                    json.dump(
                        {
                            "api_version": "specrunway/v1",
                            "action": "logs",
                            "ok": True,
                            "data": {"execution_id": args.execution, "chunk": chunk},
                        },
                        sys.stdout,
                        sort_keys=True,
                    )
                    sys.stdout.write("\n")
                else:
                    sys.stdout.write(chunk)
                sys.stdout.flush()
        except KeyboardInterrupt:
            return 0
        except Exception as exc:  # noqa: BLE001
            return _fail_cli(_error_envelope("logs", exc), args.json, "specrunway logs")
        return 0
    try:
        rows = enumerate_logs(
            root,
            args.execution,
            kind=kind,
            repo_id=args.repo,
            attempt=args.attempt,
        )
    except Exception as exc:  # noqa: BLE001
        return _fail_cli(_error_envelope("logs", exc), args.json, "specrunway logs")
    if not rows:
        return _fail_cli(
            _error_envelope(
                "logs",
                ObservabilityError(
                    "log-missing",
                    f"no matching logs for execution {args.execution}",
                ),
            ),
            args.json,
            "specrunway logs",
        )
    payload = _specrunway_envelope(
        action="logs",
        ok=True,
        data={"execution_id": args.execution, "logs": rows},
        warnings=[],
    )
    if args.json:
        _emit(payload, True, "")
    else:
        for row in rows:
            scope = row.get("repo_id") or row.get("run_id") or "native"
            sys.stdout.write(
                f"{row['kind']} {scope}/{row.get('attempt')} {row['path']} "
                f"({row.get('size', 0)} bytes)\n"
            )
    return 0


def cmd_abandon(args: argparse.Namespace) -> int:
    """Release the active-owner record of a paused or failed execution."""
    from specrunway.recovery import abandon_execution

    root = _control_root_for(args)
    if root is None:
        return _fail_cli(
            _error_envelope("abandon", RuntimeError("no control checkout found")),
            args.json,
            "specrunway abandon",
        )
    try:
        outcome = abandon_execution(root, args.execution)
    except Exception as exc:  # noqa: BLE001
        return _fail_cli(_error_envelope("abandon", exc), args.json, "specrunway abandon")
    payload = _specrunway_envelope(action="abandon", ok=True, data=outcome, warnings=[])
    _emit(
        payload,
        args.json,
        f"abandon ok: execution {args.execution} "
        f"{'released' if outcome['released'] else 'had no active owner'}\n",
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
        outcome = resume_execution(root, args.execution, progress_stream=sys.stderr)
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
        outcome = recover_execution(root, args.execution, progress_stream=sys.stderr)
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
    doc.add_argument(
        "--no-agent-probe",
        action="store_true",
        help="Skip the bounded coding-agent preflight and report wiring findings only",
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

    wizard_parser = sub.add_parser(
        "wizard", help="Guide control configuration and request drafting"
    )
    wizard_parser.add_argument(
        "--root", help="Explicit control root (default: walk up from cwd)"
    )
    wizard_parser.add_argument(
        "--reconfigure", action="store_true", help="Re-open the local.yaml questions"
    )
    wizard_parser.add_argument("--change", help="Change id (default: slug from description)")
    wizard_parser.add_argument("--description", help="Short change summary")
    wizard_parser.add_argument("--request", help="Use an existing request markdown file")
    wizard_parser.add_argument("--manifest", help="Routing manifest for --request")
    wizard_parser.add_argument(
        "--skip-init", action="store_true", help="Write configuration without bootstrapping"
    )
    wizard_parser.add_argument(
        "--skip-plan", action="store_true", help="Stop after configuration or request writing"
    )
    wizard_parser.add_argument(
        "--force", action="store_true", help="Replace existing local.yaml/request/manifest"
    )
    wizard_parser.add_argument(
        "--json", action="store_true", help="Emit the specrunway/v1 envelope as JSON"
    )
    wizard_parser.set_defaults(func=cmd_wizard)

    status_parser = sub.add_parser("status", help="Show execution status")
    status_parser.add_argument("--execution", required=True, help="Execution UUID")
    status_parser.add_argument(
        "--follow",
        action="store_true",
        help="Stream step transitions and their durations until the run settles",
    )
    status_parser.add_argument(
        "--root", help="Explicit control root (default: walk up from cwd)"
    )
    status_parser.add_argument(
        "--json", action="store_true", help="Emit specrunway/v1 JSON envelope"
    )
    status_parser.set_defaults(func=cmd_status)

    executions_parser = sub.add_parser(
        "executions", help="List executions and their pending gates"
    )
    executions_parser.add_argument(
        "--root", help="Explicit control root (default: walk up from cwd)"
    )
    executions_parser.add_argument(
        "--json", action="store_true", help="Emit specrunway/v1 JSON envelope"
    )
    executions_parser.set_defaults(func=cmd_executions)

    logs_parser = sub.add_parser(
        "logs", help="Locate or follow the agent, test, and native logs"
    )
    logs_parser.add_argument("--execution", required=True, help="Execution UUID")
    logs_parser.add_argument(
        "--kind",
        choices=["all", "agent", "test", "native"],
        default="all",
        help="Log kind to locate (default: all)",
    )
    logs_parser.add_argument("--repo", help="Only logs for this repository id")
    logs_parser.add_argument("--attempt", type=int, help="Only this attempt number")
    logs_parser.add_argument(
        "--follow", action="store_true", help="Tail matching logs until the run settles"
    )
    logs_parser.add_argument(
        "--root", help="Explicit control root (default: walk up from cwd)"
    )
    logs_parser.add_argument(
        "--json", action="store_true", help="Emit specrunway/v1 JSON envelope"
    )
    logs_parser.set_defaults(func=cmd_logs)

    for name, help_text, handler in (
        ("abandon", "Release a paused/failed execution's checkout ownership", cmd_abandon),
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
    approve_parser.add_argument("--execution", help="Execution UUID")
    approve_parser.add_argument(
        "--pending",
        action="store_true",
        help="Resolve the single execution waiting at an approval gate",
    )
    approve_parser.add_argument(
        "--kind",
        choices=["plan", "implementation"],
        help="Approval kind (default: the pending gate with --pending)",
    )
    approve_parser.add_argument(
        "--interactive",
        action="store_true",
        help="Ask y/N on the terminal before recording the receipt",
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
