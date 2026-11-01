# SpecRunway operator documentation

This directory is for operators who install and run SpecRunway. It does not
assume that you have read the design or contributor material.

| Page | Use it when |
| --- | --- |
| [quickstart.md](quickstart.md) | You are installing SpecRunway and want the shortest path from install to `ready_for_review`. |
| [concepts.md](concepts.md) | You need to understand changes, executions, snapshots, approvals, trusted results, and operation intents. |
| [commands.md](commands.md) | You need the arguments, stable error codes, and next action for a subcommand. |
| [troubleshooting.md](troubleshooting.md) | A run is stuck, an execution is orphaned, or archive refuses to proceed. |

Suggested first reading order: quickstart, then concepts, then commands. Keep
troubleshooting bookmarked for the first failed run.

Maintainer material stays separate: `docs/RUNBOOK.md` is the long-form
operation manual, `docs/DESIGN.md` explains the architecture, and
`docs/TOOLCHAIN.md` records the pinned toolchain. Operator pages state what the
shipped CLI does; when the two disagree, the shipped CLI and the
`specrunway/v1` envelope are authoritative.
