# budget-accounting-v1

Date: 8 November 2026

Execution: `670e797c-c156-43ac-8cd6-56a4670cc204` (repo `specrunway`,
attempt 1, base `19a2c7c0ffe53d32551f0dd39a29cd446cc69f46`).

## Delivered behavior

- `FileRunStore.mark_activated` records `state.last_activated_at` when a run
  starts or resumes (`start_execution`, `continue_execution`, the native resume
  path, and recovery that starts a new native run). The total-time check in
  `run-repo` measures from that mark; execution `created_at` remains only as a
  fallback for state written before this change.
- A plan gate left open no longer spends the next activation's budget. A test
  seeds `created_at` in 2020, sets `last_activated_at` to now, and still runs
  the repository attempt under a one-minute limit.
- Before the first repository attempt of an execution, a snapshot older than
  the manifest `total_minutes` fails with `freeze-stale`, marks the execution
  blocked, and leaves `budgets` untouched. Its message names the age, the
  limit, and `specrunway run --change <change_id>` as the re-freeze action.
  The code is distinct from `budget-exhausted`; once any repository attempt has
  started, the same snapshot is not refused as stale.
- `record_native_failure` prefers the step's human `error.message` when the
  native row stores only the code, and copies scalar step data into
  `last_failure.details`. A total-budget refusal now keeps `elapsed_minutes`,
  `total_minutes`, and `activated_at` there, so `status` returns the numbers
  instead of the bare string `budget-exhausted`. The non-JSON status line
  prints the message and numbers as well.
- Budget refusal envelopes (`run-repo` attempts/total, `repair-round`) carry
  the numbers the failure row records. Approval semantics, attempt/repair
  budgets, and the `specrunway/v1` envelope version are unchanged.

## Verification

Trusted profile, from the execution worktree:

```bash
bash scripts/worktree_check.sh
```

Result: exit 0, `264 passed in 241.85s (0:04:01)` (up from 261; three
regression cases added in `tests/test_budget_repair.py`). The profile created
the worktree's own `.venv`, installed the package editable, used the pinned
`specify-cli==1.2.1` wheel and `tooling/openspec` dependencies, and ran the
suite.

Focused checks during development:

```bash
PYTHONPATH=src /Users/wuhuizuo/apps/github.com/wuhuizuo/specrunway/.venv/bin/python \
  -m pytest -q tests/test_budget_repair.py
# 9 passed in 7.70s

PYTHONPATH=src /Users/wuhuizuo/apps/github.com/wuhuizuo/specrunway/.venv/bin/python \
  -m pytest -q tests/test_budget_repair.py tests/test_runstore.py \
  tests/test_recovery.py tests/test_runner_flow.py tests/test_observability.py \
  tests/test_cli.py
# 56 passed, 5 skipped in 12.91s

/Users/wuhuizuo/apps/github.com/wuhuizuo/specrunway/.venv/bin/python -m ruff check src/specrunway tests
# All checks passed!
```

Documented command surface was checked against the shipped help:

```bash
.venv/bin/specrunway run --help
.venv/bin/specrunway status --help
```

The `run` and `status` flags are unchanged; this change adds no command or
flag. `docs/user/commands.md`, `docs/user/troubleshooting.md`, and
`docs/RUNBOOK.md` describe `freeze-stale`, activation-based timing, and the
`last_failure.details` fields. D16 records the decision.

## Regression coverage

`tests/test_budget_repair.py` adds:

- `test_total_budget_counts_from_last_activation`: old `created_at`, fresh
  activation, one-minute limit, repository attempt succeeds and consumes one
  attempt.
- `test_stale_freeze_is_refused_before_spending_an_attempt`: old snapshot,
  `freeze-stale` with re-freeze hint and numbers, no `attempts_used`, blocked
  phase, code differs from `budget-exhausted`.
- `test_budget_failure_keeps_message_and_numbers_in_last_failure`: a native
  total-budget failure row (native row error is the bare code) becomes a human
  `last_failure.message` plus `details.elapsed_minutes` and
  `details.total_minutes`, and `execution_status` returns the same row.

## Known limits

`freeze-stale` uses the manifest `total_minutes` as the age limit and applies
only before the first repository attempt of an execution. A run that has
already started work is not forced to re-freeze after an implementation-gate
wait; its accepted results and worktrees remain valid. Re-freezing creates a
new execution and does not migrate old attempts.
