# run-observability-v1

Date: 8 November 2026

Execution: `61d595ad-547e-420a-8afb-52ff77cf777e` (repo `specrunway`,
attempt 1, base `e6ce953499c35a5a1c4116e8c6c5f4bc67fec017`).

## Delivered behavior

- `specrunway status` adds `current_step` (also `running_step`) with the step
  id, status, start/finish timestamps, elapsed seconds, and the native log that
  belongs to it, plus `native_log_path`. The envelope stays
  `specrunway/v1`; no gate semantics changed.
- `specrunway status --follow` streams one row per step transition, including
  its duration, and stops when the workflow settles (completed, paused, failed,
  or blocked) or on Ctrl-C.
- `run`, `resume`, and `recover` forward `[native]` step progress to stderr.
  Under `--json`, stdout remains a single clean envelope.
- `specrunway logs --execution <id> [--kind {all,agent,test,native}]
  [--repo] [--attempt] [--follow]` locates the agent/test logs by
  `<repo>/<attempt>` and the native `log.jsonl`, then optionally tails them.
- `specrunway executions` lists runs newest first with phase and pending gate.
  `approve --pending` resolves the single pending execution; zero is
  `no-pending-execution`, several are `pending-execution-conflict`.
- `approve --interactive` asks `y/N` on a TTY, refuses with `not-a-tty` when
  stdin is not a terminal, and records the same `self_asserted` receipt on
  confirmation. A declined answer records nothing (`approval-declined`).

Read-only helpers live in `src/specrunway/observability.py`. The native log
watcher never edits `.specify` state; it reads the log the native workflow
already writes.

## Verification

Command (trusted profile, from the execution worktree):

```bash
bash scripts/worktree_check.sh
```

Result: exit 0, `261 passed in 207.52s (0:03:27)`, no skips. The profile
provisioned the worktree venv, installed the package editable, and used the
pinned `specify-cli==1.2.1`, `openspec` 1.15.0, and each worktree's own
`node_modules`.

Additional static check:

```bash
.venv/bin/python -m ruff check src/specrunway tests
```

Result: `All checks passed!`

## Test coverage added

`tests/test_observability.py` covers:

- Status detail for a paused, a failed, and a completed execution, including
  start time, elapsed seconds, and native log path.
- `status --follow` transitions and step durations against a log written while
  the follower polls.
- stderr-only progress during `run --json`, and the `[native]` watcher against
  a real spawned process that writes a new native log.
- Log discovery for agent, test, and native kinds, `log-missing` for a filter
  with no file, and `--follow` printing existing content and the path.
- `executions` pending-gate listing and `approve --pending` for the single
  case, the zero case, and the conflicting case.
- `approve --interactive` acceptance on a real pty and refusal without a
  terminal, including that no receipt is written on refusal.

## Known limits

`status --follow` stops when the native workflow settles; it is not a daemon.
`logs --follow` tails from the beginning of each matching file and stops when
the execution settles so a paused run does not block the terminal. Following a
running execution still requires the operator to keep the process alive or
interrupt it with Ctrl-C.

## Review performed after `ready_for_review`

Merged as `cb3db47` and archived as `2026-11-08-run-observability-v1`.
Independent checks, run against the execution worktree's own package so the
new code answered for real data:

```text
$ specrunway executions
61d595ad-... awaiting_implementation_review pending=implementation change=run-observability-v1 active
8d09d111-... blocked                        pending=plan           change=run-observability-v1
0c300426-... archived                       pending=none           change=archive-ownership-v1

$ specrunway status --execution 61d595ad-... --json
current_step: implementation-gate | status: paused | elapsed: 0.001
native_log_path: .../.specify/workflows/runs/677544c1/log.jsonl

$ specrunway logs --execution 61d595ad-...
agent  specrunway/1  .../logs/specrunway/1/agent.log    (218001 bytes)
test   specrunway/1  .../logs/specrunway/1/tests.log    (3043 bytes)
native 677544c1/1    .../.specify/workflows/runs/677544c1/log.jsonl (2663 bytes)

$ specrunway status --execution 61d595ad-... --follow
status awaiting_implementation_review: implementation-gate paused in 0.0s pending_gate=implementation log .../log.jsonl
```

Trusted verification: 261 passed, exit 0, 210.8s (14 new cases). The progress
path uses temporary files rather than pipes, so a slow reader cannot block the
native workflow.

## Findings recorded during this round

Two gaps showed up while driving the run and are candidates for a later change:

1. **Total-time budget counts wall-clock from execution creation.** A plan gate
   left open for six days made the next attempt fail at the first repository
   step with `budget-exhausted` and zero agent work. Either the budget should
   count active execution time only, or `resume`/`run` should refuse a stale
   freeze with its own code before spending an attempt.
2. **`last_failure.message` loses the budget detail.** It recorded the bare
   string `budget-exhausted` while the step envelope carried "exceeded the 180
   minute total budget". The failure row should keep the human message and the
   relevant numbers.

Cleanup after this round removed the archived executions' worktrees through
`git worktree remove --force` plus `git worktree prune`, and deleted three
abandoned/unreferenced executions; run evidence (snapshots, state, results,
receipts, archive backups) stays. `.srrunway` went from about 380 MB to 1.8 MB.
