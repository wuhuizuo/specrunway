"""Tests for hubcoord.cli command surface and stub behavior."""

from __future__ import annotations

from hubcoord.cli import main


def test_version(capsys):
    import hubcoord

    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    assert hubcoord.__version__ in capsys.readouterr().out


def test_doctor_json_ok(control_workspace):
    rc = main(["doctor", "--root", str(control_workspace["control"]), "--json"])
    assert rc == 0  # dev-tooling hints are warnings, not errors, in a fresh fixture


def test_stub_exit_code_not_implemented():
    for name in ("run", "status", "resume", "recover", "archive"):
        rc = main([name, "--json"])
        assert rc == 69


def test_approve_require_flags(capsys):
    try:
        main(["approve"])
    except SystemExit as exc:
        assert exc.code == 2
    out = capsys.readouterr().err
    assert "--execution" in out


def test_plan_requires_change_id():
    try:
        main(["plan"])
    except SystemExit as exc:
        assert exc.code == 2
