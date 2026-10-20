"""Single-writer acceptance of mapped tasks.md checkboxes."""

from __future__ import annotations

import re
from pathlib import Path

from hubcoord.models.common import ValidationError

TASK_LINE_RE = re.compile(
    r"^(?P<indent>[ \t]*)- \[(?P<mark>[ xX])\] "
    r"(?P<number>\d+(?:\.\d+)*) "
    r"\[(?P<label>T[A-Z0-9-]+)\](?P<rest>.*)$",
    re.MULTILINE,
)


def accept_tasks(tasks_md: str, task_ids: list[str]) -> tuple[str, list[str]]:
    """Mark the given task checkboxes complete; never touch unaccepted lines.

    Returns ``(new_text, flipped_labels)``. A requested label that no line
    carries is a mapping error, because the coordinator may not invent tasks.
    """
    wanted = set(task_ids)
    found: set[str] = set()
    flipped: list[str] = []

    def replace(match: re.Match[str]) -> str:
        label = match.group("label")
        if label not in wanted:
            return match.group(0)
        found.add(label)
        if match.group("mark").lower() == "x":
            return match.group(0)
        flipped.append(label)
        return (
            f"{match.group('indent')}- [x] {match.group('number')} [{label}]"
            f"{match.group('rest')}"
        )

    new_text = TASK_LINE_RE.sub(replace, tasks_md)
    missing = sorted(wanted - found)
    if missing:
        raise ValidationError(
            "task-unmapped",
            f"tasks.md has no checkbox line for {', '.join(missing)}",
        )
    return new_text, flipped


def update_tasks_file(tasks_path: Path, task_ids: list[str]) -> list[str]:
    """Apply acceptance to the change tasks.md in place; return flipped labels."""
    tasks_path = Path(tasks_path)
    if not tasks_path.is_file():
        raise ValidationError("tasks-missing", f"no tasks.md at {tasks_path}")
    before = tasks_path.read_text(encoding="utf-8")
    after, flipped = accept_tasks(before, task_ids)
    if after != before:
        tasks_path.write_text(after, encoding="utf-8")
    return flipped


__all__ = ["TASK_LINE_RE", "accept_tasks", "update_tasks_file"]
