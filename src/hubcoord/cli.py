"""Hub CLI: local v1 command surface (``doctor`` diagnostic ships first)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .doctor import find_control_root, run_doctor

#: Subcommands delivered by later changes, mapped to their owning OpenSpec change.
LATER_CHANGES = {
    "run": "03-deliver-two-repo-loop",
    "approve": "03-deliver-two-repo-loop",
    "status": "03-deliver-two-repo-loop",
    "resume": "04-harden-recovery-and-archive",
    "recover": "04-harden-recovery-and-archive",
    "archive": "04-harden-recovery-and-archive",
}


def _envelope(ok: bool, **body) -> dict:
    return {"api_version": "hub/v1", "ok": bool(ok), **body}


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


def _hub_envelope(**body) -> dict:
    return {"api_version": "hub/v1", **body}


def _error_envelope(action: str, exc: Exception) -> dict:
    code = getattr(exc, "code", None)
    errors = getattr(exc, "errors", None)
    body = {"code": code or type(exc).__name__, "message": str(exc)}
    if errors:
        body["errors"] = errors
    return _hub_envelope(action=action, ok=False, data={}, error=body)


def cmd_plan(args: argparse.Namespace) -> int:
    """Create/accept planning artifacts + machine-validated routing."""
    from .planning import plan

    control_root = Path(args.root).resolve() if args.root else find_control_root(Path.cwd())
    if control_root is None:
        payload = _error_envelope(
            "plan",
            RuntimeError("no control checkout found; run hub from the control workspace"),
        )
        code = payload["error"]["code"]
        message = payload["error"]["message"]
        if args.json:
            json.dump(payload, sys.stdout, indent=2, sort_keys=True)
            sys.stdout.write("\n")
        else:
            sys.stderr.write(f"hub plan: [{code}] {message}\n")
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
            sys.stderr.write(f"hub plan: [{error['code']}] {error['message']}\n")
        return 1
    payload = _hub_envelope(
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


def _make_stub(name: str):
    change_dir = LATER_CHANGES[name]

    def handler(args: argparse.Namespace) -> int:
        payload = _envelope(
            False,
            action=name,
            data={},
            error={
                "code": "not-implemented",
                "message": (
                    f"`hub {name}` is not implemented yet; see openspec/changes/{change_dir}."
                ),
                "retryable": False,
            },
        )
        if getattr(args, "json", False):
            json.dump(payload, sys.stdout, indent=2, sort_keys=True)
            sys.stdout.write("\n")
        else:
            sys.stderr.write(f"hub: {payload['error']['message']}\n")
        return 69  # EX_UNAVAILABLE

    handler.__name__ = f"cmd_{name}"
    return handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hub",
        description="Central Store Coordinator (local v1).",
    )
    parser.add_argument("--version", action="version", version=f"hub {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    doc = sub.add_parser("doctor", help="Check control checkout, Store, and repo wiring")
    doc.add_argument("--json", action="store_true", help="Emit the hub/v1 envelope as JSON")
    doc.add_argument(
        "--root", help="Explicit control checkout root (default: walk up from cwd)"
    )
    doc.set_defaults(func=cmd_doctor)

    helps = {
        "run": "Run an approved change across ordered repositories",
        "approve": "Record a local approval for an execution",
        "status": "Show execution status",
        "resume": "Resume a paused/failed execution",
        "recover": "Reconcile an interrupted execution",
        "archive": "Archive a completed change explicitly",
    }
    for name, help_text in helps.items():
        sub_parser = sub.add_parser(name, help=help_text)
        sub_parser.add_argument("--json", action="store_true", help="Emit hub/v1 JSON envelope")
        sub_parser.set_defaults(func=_make_stub(name))

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
    plan_parser.add_argument("--json", action="store_true", help="Emit hub/v1 JSON envelope")
    plan_parser.set_defaults(func=cmd_plan)

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
