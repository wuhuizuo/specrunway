# Hub v1 runbook (local coordinator)

Reproducible local operation of the Central Store Coordinator at pinned
tool versions (OpenSpec 1.14.3, specify-cli 1.2.1, Python 3.14, one real
coding-agent CLI). No server, database, broker, or team component is used.

## 1. Install

```bash
python3 -m venv .venv
.venv/bin/python -m pip install hub_cli-0.1.0-py3-none-any.whl   # or: pip install .
.venv/bin/hub --version
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
```

```bash
hub doctor --json                   # wiring findings, exit 1 on errors
openspec store setup my-store --path /abs/path/to/store --json
specify init --here --force --non-interactive --ignore-agent-tools
specify workflow step add hub --dev <path-to>/tooling/hubstep
```

## 3. Plan

```bash
hub plan my-change --store my-store --request request.md --json
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
hub run --change my-change --json          # freezes snapshot + starts native run
hub approve --execution <id> --kind plan --actor <you> --json
hub resume --execution <id> --json         # or: hub run --execution <id> --continue
hub status --execution <id> --json
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
   repos with prior test feedback, bounded by `repo_max_attempts` /
   `integration_max_repairs`, stopping on no-progress or exhaustion.
5. `accept-tasks` flips only the mapped tasks.md checkboxes (single writer).
6. Native implementation gate pauses for the implementation approval bound
   to the accepted-results digest; after approval `resume` completes at
   `ready_for_review`.

## 5. Failure handling

| Situation | Command | Behavior |
|---|---|---|
| Gate pause | `hub resume` | Checks receipt + digests, resumes native run |
| Retryable native failure | `hub resume` | Native resume; completed steps are not re-run |
| Blocked budget/no-progress | — | `hub status` shows `blocked`; preserve worktrees for takeover |
| Orphan `running`, owner dead | `hub recover` | Old run preserved `abandoned-running`, new native run same execution, verified receipts reused |
| Orphan `running`, owner alive | — | `hub recover` refuses `orphan-alive`; stop the process first |
| Archive outcome unknown | `hub recover` | Path-based reconciliation records the proven result; mixed state stays blocked |

Counters (`budgets`), accepted results, verification rows, and operation
intents/receipts live in `<control>/.hub/runs/<execution>/` and survive
process restarts. Never edit Specify's private run state.

## 6. Archive

```bash
hub archive --execution <id> --json                             # merged_commits (default)
hub archive --execution <id> --policy validated_commits \
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
replayed. Backup: `<control>/.hub/runs/<execution>/archive-backup/<stamp>/`
(`change/` tree, `before.json`, `after.json`).

Restore drill: copy `archive-backup/<stamp>/change` back to the Store change
path to inspect or re-validate the pre-archive bytes; do not re-run archive
for the recorded execution (it returns `already_archived`).

## 7. Cleanup

```bash
openspec store unregister my-store --json   # disposable fixtures only
rm -rf <control>/.hub/runs/<execution>      # after evidence is captured
```

Preserve a usable failure scene (worktrees, logs, receipts) before cleanup
when investigating a failure.
