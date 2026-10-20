"""Dev-convention resolvers for the pinned OpenSpec and Specify CLIs."""

from __future__ import annotations

import shutil
from pathlib import Path


def _bin_name(name: str) -> str:
    return "openspec" if name == "openspec" else "specify"


def resolve_tool_bin(control_root: Path, explicit: str | None, name: str) -> str | None:
    """Explicit path first, then dev checkout hints, then PATH."""
    if explicit:
        return explicit
    specrunway_root = Path(__import__("specrunway").__file__).resolve().parent
    hints = [
        control_root / "tooling" / "openspec" / "node_modules" / ".bin" / _bin_name(name),
        specrunway_root.parent.parent
        / "tooling"
        / "openspec"
        / "node_modules"
        / ".bin"
        / _bin_name(name),
        control_root / ".venv" / "bin" / _bin_name(name),
        specrunway_root.parent.parent / ".venv" / "bin" / _bin_name(name),
    ]
    for hint in hints:
        if hint.is_file():
            return str(hint)
    found = shutil.which(_bin_name(name))
    return found


__all__ = ["resolve_tool_bin"]
