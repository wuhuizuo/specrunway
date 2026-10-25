"""Idempotent control bootstrap shared by ``init`` and the onboarding wizard."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .models import ValidationError
from .openspec_adapter import OpenSpecAdapter
from .toolresolvers import resolve_tool_bin


def initialize_control(control_root: Path, config: dict) -> dict:
    """Prepare Store, Specify workspace, and the bundled step inside *control_root*."""
    root = Path(control_root).resolve()
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

    specify_initialized = False
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
            raise ValidationError(
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
            [specify_bin, "workflow", "step", "add", "specrunway", "--dev", str(step_path)],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    if step is not None and step.returncode != 0:
        raise ValidationError(
            "step-install-failed",
            f"specify step install failed (exit {step.returncode}): "
            f"{(step.stderr or step.stdout)[-400:]}",
        )

    return {
        "specify_initialized": specify_initialized,
        "step_package": str(step_path),
    }


__all__ = ["initialize_control"]
