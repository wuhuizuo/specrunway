# Central Store change `p0-fixes-v1`: four live-path defects

Date: 1 November 2026. Change: `p0-fixes-v1` in the `specrunway-docs` Store.
Execution: `05884c10-f8f9-4bb1-8089-74eff6b06769`. Base commit:
`a91b1d11acdb6b3cd77c0d7c7cb943394e71fd72`.

The four defects come from the first live central-Store run
(`docs/evidence/12-user-docs-v1.md`): checkout ownership was never released,
`doctor` never probed the coding agent, `status` hid the failing step, and
planned capability deltas lacked `## Purpose`. Each fix carries a test that
fails against the previous behavior.

## Tool identities

| Tool | Version | Note |
| --- | --- | --- |
| specrunway | 0.1.0 (editable `.venv` in the execution worktree) | current change |
| Python | 3.14.5 | `mise.toml` pin |
| OpenSpec | 1.15.0 | `tooling/openspec` npm pin |
| specify-cli | 1.2.1 | pinned wheel from the local cache |
| opencode | 2.2.5 | only observed; the suite uses deterministic fake agents |

## Fixes and tests

### T001: explicit abandon of a paused or failed execution

`specrunway abandon --execution <id>` releases the active-owner record via
`FileRunStore.release_activity`, so the next `specrunway run --change` can
claim the checkout. It refuses with `owner-alive` while the recorded owner pid
is alive, refuses `execution-archived`, and leaves `state.json`, results,
receipts, logs, and worktrees untouched for review.

Tests (`tests/test_recovery.py`):

- `test_abandon_releases_dead_owner_and_unblocks_next_run` first reproduces the
  old refusal (`ExecutionConflictError` when another execution claims the
  checkout), abandons, and then claims successfully.
- `test_abandon_refuses_live_owner` keeps the record unchanged for a live pid.
- `test_cli_abandon_releases_owner` exercises the CLI envelope.

### T002: bounded coding-agent preflight in doctor

`run_doctor` now resolves `agent_profile` and runs it once with a one-line
prompt, a 60-second timeout, and a disposable temporary working directory. It
reports `data.agent` (`profile`, `binary`, `ok`, `status`, `reason`,
`exit_code`, `duration_seconds`, bounded `log_tail`) and an
`agent-preflight` finding. Missing binary, unknown profile, non-zero exit, and
timeout are errors, so the report is not silently green. `specrunway init`
calls `run_doctor(probe_agent=False)` and keeps checking wiring only.

Tests (`tests/test_doctor.py`): success with the resolved binary, failure on
exit 3 with the log tail, missing binary, and a capture proving the probe runs
outside every business checkout with the configured timeout.

### T003: status names the failed step

The run controller records `last_failure` in `state.json` whenever a native
`workflow run/resume` fails, reading the native step results without editing
them. It stores `step_id`, `code`, `message`, `log_path`, `native_run_id`, and
`recorded_at`; `status` returns the same object and prints it in text mode.
`code` comes from the bridge envelope (`agent-failed`, `result-rejected`, ...)
and `log_path` from the step evidence or the repo attempt log. A successful
pause or completion clears it.

Tests (`tests/test_runner_flow.py`): `test_failed_step_is_visible_in_status`
runs the real pinned Specify workflow with a fake agent that exits 3, then
asserts `phase` is still `implementing`, `last_failure.step_id` is
`implement:repo:0`, the code is `agent-failed`, and the printed log path exists
and contains the agent's error.

### T004: generated spec deltas carry a real Purpose

`specrunway plan` now writes `## Purpose` into every generated capability
delta. The text comes from the request's `Why` (falling back to `What`), joined
to reach the 50-character strict-validation floor. Archiving reads that delta
Purpose while creating the capability, so no
`TBD - created by archiving change ...` placeholder remains.

Test (`tests/test_planning.py`):
`test_planned_capability_archives_with_a_real_purpose` plans a change, archives
it with the real OpenSpec CLI, asserts the baseline spec contains the request
purpose and no `TBD`, and validates the new capability with `--strict`.

## Commands and results

Run in the execution worktree:

| Command | Exit | Result |
| --- | --- | --- |
| `bash scripts/worktree_check.sh` (baseline before edits) | 0 | 226 passed |
| `.venv/bin/python -m pytest -q tests/test_planning.py tests/test_doctor.py tests/test_recovery.py tests/test_cli.py` | 0 | 44 passed |
| `.venv/bin/python -m pytest -q tests/test_runner_flow.py` | 0 | 5 passed |
| `.venv/bin/ruff check src tests` | 0 | All checks passed |
| `.venv/bin/python scripts/check_handoff.py` | 0 | 9 changes, 19 source tasks, 47 requirements, passed |
| `bash scripts/openspec.sh validate --all --strict` | 0 | 11 passed, 0 failed |
| `.venv/bin/python -m pytest -q` (full suite after all edits) | 0 | 235 passed |

The baseline count and the final count differ by the nine added tests.

## Boundaries

- Approval stayed local `self_asserted`; no authentication was added.
- The agent preflight is an availability check, not a model-quality claim, and
  `init` deliberately skips it.
- `abandon` does not delete evidence and does not change the execution's phase.
- The planner naming defect (`<repo>-delivery`) stays on the P0 follow-up list;
  this change only adds the Purpose section.
