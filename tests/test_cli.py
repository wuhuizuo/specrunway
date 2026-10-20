"""Tests for specrunway.cli command surface and stub behavior."""

from __future__ import annotations

import pytest

from specrunway.cli import main


def test_version(capsys):
    import specrunway

    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    assert specrunway.__version__ in capsys.readouterr().out


def test_doctor_json_ok(control_workspace):
    rc = main(["doctor", "--root", str(control_workspace["control"]), "--json"])
    assert rc == 0  # dev-tooling hints are warnings, not errors, in a fresh fixture


def test_commands_require_execution_flag():
    for name in ("status", "resume", "recover", "archive"):
        with pytest.raises(SystemExit) as exited:
            main([name, "--json"])
        assert exited.value.code == 2


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
