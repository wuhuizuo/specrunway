"""Hub CLI: local v1 command surface (``doctor`` diagnostic ships first)."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .doctor import run_doctor

#: Subcommands delivered by later changes, mapped to their owning OpenSpec change.
LATER_CHANGES = {
    "plan": "03-deliver-two-repo-loop",
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
        "plan": "Create/refresh planning artifacts for a change",
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
