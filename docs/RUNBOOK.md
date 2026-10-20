# SpecRunway v1 runbook (local coordinator)

Reproducible local operation of the Central Store Coordinator at pinned
tool versions (OpenSpec 1.14.3, specify-cli 1.2.1, Python 3.14, one real
coding-agent CLI). No server, database, broker, or team component is used.

## 1. Install

```bash
python3 -m venv .venv
.venv/bin/python -m pip install specrunway-0.1.0-py3-none-any.whl   # or: pip install .
.venv/bin/specrunway --version
.venv/bin/python -m pip install "specify-cli @ git+https://github.com/github/spec-kit.git@v1.2.1"
```

The OpenSpec CLI is pinned by `tooling/openspec/package.json`; install it
with `npm ci --prefix tooling/openspec`.

## 2. Control checkout

`local.yaml` lives only in the control checkout (never in business repos):

```yaml
store:
  id: my-store
  path: /abs/path/to/store          # OpenSpec Store repository
repos:
  repo-a:
    path: /abs/path/to/repo-a       # existing Git checkout
    remote_identity: https://example.org/repo-a.git
agent_profile: primary-coding-agent
max_workers: 1
integration_profiles:              # executable combined check, trusted config
  quota-e2e:
    command: ["go", "test", "./test/e2e/..."]
    repo: operator                 # worktree to run from (default: first repo)
    timeout_seconds: 900
```

```bash
specrunway init --json     # Store setup + Specify workspace + bundled step
specrunway doctor --json   # wiring findings, exit 1 on errors
```

`init` is idempotent, creates the Store directory, registers the Store,
initializes `.specify` only when absent, installs the `specrunway` step from
the installed package, and never writes outside the control checkout. You do
not need to type the upstream `openspec`/`specify` commands yourself.

## 3. Plan

```bash
specrunway plan my-change --store my-store --request request.md --json
```

- Generates proposal/design/tasks/spec deltas in the Store when the change
  is new; accepts an existing complete manual plan otherwise.
- Task routing comes from the manifest (`task_ids`, `depends_on`,
  `allowed_paths`, `test_profile`). Forward dependencies, unknown repos,
  duplicate/missing tasks, and unknown profiles fail before execution.
- Planning success is NOT implementation completion; checkboxes stay
  unchecked.

## 4. Run and approve

```bash
specrunway run --change my-change --json          # freezes snapshot + starts native run
specrunway approve --execution <id> --kind plan --actor <you> --json
specrunway resume --execution <id> --json         # or: specrunway run --execution <id> --continue
specrunway status --execution <id> --json
```

Execution order:

1. `prepare` → ordered repos from `repo_order`.
2. Native plan gate pauses until a matching `self_asserted` receipt exists;
   `resume` re-checks the receipt and the live planning digest before
   supplying the native verdict.
3. `run-repo` fan-out with `max_concurrency: 1`: per-repo worktree at the
   frozen base OID, bounded prompt, agent CLI (argv only), trusted tests,
   result identity/ancestry/path validation, result + receipt persistence.
4. `verify-round` re-runs trusted tests; `repair-round` retries only failing
   repos with prior test feedback, bounded by `repo_max_attempts`.
5. `integration-round` writes `matrix.json` (accepted head/result per repo),
   exports `SPECRUNWAY_MATRIX` + `SPECRUNWAY_HEAD_<REPO>`, and runs the frozen
   integration command. Failure is fed back to the last repository and
   retried within `integration_max_repairs`; a repeated failure at the same
   matrix head stops as `no-progress`. `ready_for_review` requires a passed
   receipt bound to the current matrix.
6. `accept-tasks` flips only the mapped tasks.md checkboxes (single writer).
7. Native implementation gate pauses for the implementation approval bound
   to the accepted-results digest; after approval `resume` completes at
   `ready_for_review`.

## 5. Failure handling

| Situation | Command | Behavior |
|---|---|---|
| Gate pause | `specrunway resume` | Checks receipt + digests, resumes native run |
| Retryable native failure | `specrunway resume` | Native resume; completed steps are not re-run |
| Blocked budget/no-progress | — | `specrunway status` shows `blocked`; preserve worktrees for takeover |
| Orphan `running`, owner dead | `specrunway recover` | Old run preserved `abandoned-running`, new native run same execution, verified receipts reused |
| Orphan `running`, owner alive | — | `specrunway recover` refuses `orphan-alive`; stop the process first |
| Archive outcome unknown | `specrunway recover` | Path-based reconciliation records the proven result; mixed state stays blocked |

Counters (`budgets`), accepted results, verification rows, and operation
intents/receipts live in `<control>/.specrunway/runs/<execution>/` and survive
process restarts. Never edit Specify's private run state.

## 6. Archive

```bash
specrunway archive --execution <id> --json                             # merged_commits (default)
specrunway archive --execution <id> --policy validated_commits \
            --confirm-validated --json                          # reviewed commits only
```

Preflight blocks when: phase is not `ready_for_review`, results are not
accepted/verified, mapped tasks remain unchecked, the implementation
approval no longer binds the results, final trusted tests fail or run at a
different head, or `merged_commits` finds an accepted head not merged into
the base ref (`partial-merge`). `validated_commits` requires explicit
selection plus `--confirm-validated` and never claims a main-branch merge.

Archive writes intent + backup before applying OpenSpec deltas, verifies the
resulting path/specs, and records a receipt. A successful archive is never
replayed. Backup: `<control>/.specrunway/runs/<execution>/archive-backup/<stamp>/`
(`change/` tree, `before.json`, `after.json`).

Restore drill: copy `archive-backup/<stamp>/change` back to the Store change
path to inspect or re-validate the pre-archive bytes; do not re-run archive
for the recorded execution (it returns `already_archived`).

## 7. Cleanup

```bash
openspec store unregister my-store --json   # disposable fixtures only
rm -rf <control>/.specrunway/runs/<execution>      # after evidence is captured
```

Preserve a usable failure scene (worktrees, logs, receipts) before cleanup
when investigating a failure.
