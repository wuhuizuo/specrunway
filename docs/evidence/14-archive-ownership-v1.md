# Central Store change `archive-ownership-v1`: close the archive ownership leak

Date: 1 November 2026. Change: `archive-ownership-v1` in the
`specrunway-docs` Store. Execution: `0c300426-2956-4766-b6c9-fe10a91d17de`.
Base commit: `8ac503a3f4cbd82e600c827b53c429523e22bfcb`. This evidence is part
of the commit that delivers the change; the coordinator's result record
carries its exact head and attempt. Attempt 1 committed the same work but its
agent process died on a transport error before returning. Attempt 2 added two
end-to-end archive-ownership checks and the stricter capability-name cases,
then timed out before returning. Attempt 3 re-verified the complete tree: the
focused tests, the trusted worktree profile, lint, the handoff guard, and
strict OpenSpec validation all passed before this result was recorded.

The change closes the residual defect recorded in
`docs/evidence/13-p0-fixes-v1.md`: a successful archive left the control
checkout claimed, while `abandon` refused archived executions. It also adds the
wiring-only doctor switch and request-driven capability naming from the same
operator review.

## Tool identities

| Tool | Version | Note |
| --- | --- | --- |
| specrunway | 0.1.0 (editable `.venv` in the execution worktree) | current change |
| Python | 3.14.5 | `mise.toml` pin |
| OpenSpec | 1.15.0 | `tooling/openspec` npm pin |
| specify-cli | 1.2.1 | installed in the execution `.venv` |

## Fixes and tests

### T001: archive releases checkout ownership

`archive_execution` now checks ownership before applying deltas and holds the
checkout lock through backup, intent, the OpenSpec call, receipt, and state
update. After the receipt and `archived` phase are written, it releases the
active-owner record of the execution it archived, so a later
`specrunway run --change` can claim the checkout with no manual state edit. A
foreign owner is refused with `execution-conflict`; a matching live owner
process is refused with `owner-alive` and ownership stays unchanged. Replaying
an already recorded archive and reconciling an interrupted archive from
`recover` also release a matching dead record left by an older coordinator,
without releasing a live process. `abandon` still refuses
archived executions with `execution-archived`; that path is unchanged.

Tests (`tests/test_archive.py`):

- `test_archive_releases_owner_and_unblocks_next_execution` claims the
  checkout for the archived execution with a dead pid, archives, asserts the
  phase is `archived` and no owner remains, then claims the checkout for
  `next-execution` (the exact defect).
- `test_archive_then_next_run_prepares_a_new_execution` goes through the real
  `run --change` entry point: after archiving, `runner.prepare_execution` for a
  second planned change in the same control checkout freezes a new execution,
  owns the checkout, and reaches `awaiting_plan_review`. Removing the release
  lines from `archive.py` reproduces the old
  `ExecutionConflictError: [execution-conflict]` in this test, so it fails
  before the fix and passes after it.
- `test_abandon_still_refuses_an_archived_execution` archives, then asserts
  `abandon` still refuses with `execution-archived` and leaves no owner.
- `test_reconcile_completed_archive_without_replay` now claims the checkout
  with a dead pid before reconciling an already archived change, and asserts
  reconciliation records the receipt and leaves no owner.
- `test_archive_refuses_a_live_owner_before_applying_deltas` records the test
  process as owner, asserts `owner-alive`, the change directory still exists,
  the phase is still `ready_for_review`, and the owner record is unchanged.

### T002: doctor switch skips the agent preflight

`specrunway doctor --no-agent-probe` passes `probe_agent=False` to
`run_doctor`, so the bounded coding-agent launch is skipped. The report omits
`data.agent`, adds no `agent-preflight` finding, and keeps the same wiring
findings. `init` already used the wiring-only path; the default `doctor` path
still probes.

Tests (`tests/test_doctor.py`):

- `test_doctor_no_agent_probe_skips_the_launch` replaces `run_agent` with a
  failing stub, runs the CLI with the switch, and asserts exit 0, no `agent`
  data, no `agent-preflight` finding, and unchanged repo findings.
- `test_doctor_default_cli_still_probes` runs the CLI without the switch and
  asserts the preflight result is present.

### T003: capabilities are named from `Spec-Head`

`specrunway plan` reads `Spec-Head` lines from the request. A declared name
must be a lowercase slug of letters, digits, and single hyphens (an empty
value, underscore, or leading/trailing/doubled hyphen is unusable); otherwise
planning fails with `capability-name` before creating the change. A valid declared name writes
`specs/<name>/spec.md` instead of `<repo_id>-delivery`; the full
`Spec-Head`/`Spec-Title`/`Spec-Body`/`Spec-When`/`Spec-Then` block still
supplies the requirement text. When no name is declared, the per-repo
`<repo_id>-delivery` fallback stays and `plan-summary.json` records
`capability_name_source: "fallback"` (declared names record `"spec-head"`).

Tests (`tests/test_planning.py`):

- `test_declared_spec_head_names_the_capability_and_archives` plans with
  `Spec-Head: quota-limits`, asserts the delta path and summary source, then
  archives with the pinned OpenSpec CLI and validates the new capability
  strictly.
- `test_unusable_spec_head_is_rejected` is parametrized over `Quota_Limits`,
  `quota_limits`, an empty value, `quota--limits`, and `quota-`; each plans,
  asserts the stable `capability-name` code and the rejected value in the
  message, and asserts no change directory was created.
- `test_plan_generation_path` now also asserts the fallback summary records
  `capability_names` and `capability_name_source`.

### T004: operator documentation and handoff

`docs/user/commands.md` documents the `--no-agent-probe` switch, the
`Spec-Head` naming and fallback, the `capability-name` code, and archive
ownership release with `owner-alive`/`execution-conflict`. `docs/RUNBOOK.md`
adds the wiring-only doctor command, the naming rule, and the archive
ownership behavior. `docs/HANDOFF_STATE.md` records this change as completed
and updates the next action.

## Commands and results

Run in the execution worktree:

| Command | Exit | Result |
| --- | --- | --- |
| `.venv/bin/python -m pytest -q tests/test_archive.py tests/test_doctor.py tests/test_planning.py` | 0 | 51 passed |
| `bash scripts/worktree_check.sh` (trusted profile) | 0 | 247 passed |
| `.venv/bin/ruff check src tests` | 0 | All checks passed |
| `.venv/bin/python scripts/check_handoff.py` | 0 | 9 changes, 19 source tasks, 47 requirements, passed |
| `bash scripts/openspec.sh validate --all --strict` | 0 | 11 passed, 0 failed |

The trusted profile count rose from 235 (after `p0-fixes-v1`) to 247 with the
twelve added regression cases.

## Boundaries

- The ownership rule is unchanged: one active execution per control checkout,
  and a live owner process is never released behind its back.
- Archive still owns the explicit completion policy, backup, intent, and
  receipt behavior; only the end-of-life ownership release is new.
- `abandon` keeps refusing archived executions and never deletes evidence.
- Approval stays local `self_asserted`; no authenticated authority was added.
- The doctor switch controls only the preflight; it does not claim that a
  skipped probe passed.

## Review performed after `ready_for_review`

Merged as `4ada28c` (a merge commit, because prerequisite commit `e8f8113`
landed on `main` while the agent worked) and archived as
`2026-11-02-archive-ownership-v1`. Independent checks on the merged tree:

| Check | Result |
| --- | --- |
| Trusted profile at the accepted head | 247 passed, exit 0, 286.4s |
| Store strict validation after archive | 5/5 (`execution-lifecycle`, `change-planning`, `execution-recovery`, `specrunway-delivery`, active change) |
| Capability Purpose | both new capabilities carry the request purpose; no `TBD` |
| `active.json` after archive | absent, immediately after the archive command |
| Change scope | 10 files under `src/`, `tests/`, `docs/` |

The `active.json` result is the acceptance for T001: the four earlier changes
each needed a direct `FileRunStore.release_activity` call before the next
execution could start, and this one needed none.

## Run conditions that differ from the frozen snapshot

Attempts 1 and 2 stalled inside `opencode run` after a tool result. Attempt 3
continued the stalled conversation by passing `SPECRUNWAY_AGENT_SESSION` on top
of prerequisite commit `e8f8113`, which adds `--session` support to the launcher
and a per-change session id in the execution state. That commit is not part of
the accepted head, so the verified artifact is unchanged; the agent was only
invoked differently. The prerequisite itself was verified separately: 235 tests
passed before it was used, and it changes no coordinator logic under test here.
