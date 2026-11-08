# Troubleshooting

This page is organized by symptom. Start with `specrunway status --execution
<id> --json`; it shows the phase, pending gate, native run, active owner,
budgets, accepted results, verification rows, approvals, the last failed step
(`last_failure`), and operation statuses. Preserve the run directory before
changing anything.

## The phase does not move

| Observed phase | Likely cause | Next action |
| --- | --- | --- |
| `planning` | Preparation stopped before the snapshot and workflow were ready. | Read the last run error; retry `run --change` if no native run was created. |
| `awaiting_plan_review` | The plan gate has no matching approval receipt, or the receipt binds different content. | Review the plan, record `approve --kind plan`, then `run --continue` or `resume`. |
| `implementing` | Work, trusted tests, repair, or integration is still running; or the native run is paused/failed. | Read `last_failure` for the failing step, code, and log; then `resume` (or `abandon` to release the checkout). If `resume` reports `orphan-running`, use `recover`. |
| `awaiting_implementation_review` | The implementation gate has no matching receipt, or a result/verification is missing. | Check `results` and `verification`; approve only after every required repository is accepted. |
| `ready_for_review` | Normal completion; nothing is pending. | Merge if required, then archive explicitly. |
| `blocked` | Budget exhausted, repeated failure without progress, or an uncertain archive. | Hand over to a human; read `blocked_reason` and `budgets`. |
| `interrupted` | `recover` preserved an orphaned running native run. | Finish recovery, then continue the new native run. |
| `archived` | The change was archived. | No execution action remains. |

A phase name is not proof of completion. Check `results` and `verification`
before approving or archiving.

### Stuck at awaiting_plan_review

```bash
specrunway status --execution "$EXEC" --json
specrunway approve --execution "$EXEC" --kind plan --actor "$USER"
specrunway resume --execution "$EXEC" --json
```

`resume` revalidates the live plan against the frozen planning digest. If it
fails with `approval-stale` or `change-missing`, the approved planning content
changed after freeze or disappeared. Do not try to re-approve the old
execution; create a new execution from the current plan.

### Stuck at awaiting_implementation_review

Check that every repository in `repo_order` has `results.<repo>.passed: true`
and `verification.<repo>.status: "passed"`. If a repository is missing or
failed, the native run has not finished successfully. Try:

```bash
specrunway resume --execution "$EXEC" --json
```

If the native run is paused or failed, `resume` retries it without re-running
completed steps. If the execution is `blocked`, resume refuses with
`execution-blocked`; the failure needs a human decision. If the results are
present but the implementation approval refuses with `result-required`, no
accepted result was persisted; inspect `results/` under the run directory.

### Running but nothing happens

1. Run `specrunway status --execution "$EXEC" --json` and inspect
   `native_run_id`, `native_runs`, and `active_owner`.
2. Check the newest agent log under
   `.specrunway/runs/<execution>/logs/<repo_id>/`.
3. If the native run is paused or failed, run `specrunway resume`.
4. If `resume` reports `orphan-running`, the native state still says running.
   Use `specrunway recover`; do not edit `.specify` private state.

## A paused or failed run blocks the next run

`specrunway run --change` refuses with `execution-conflict` while the previous
execution still owns the checkout. A failed step also leaves the phase at
`implementing`; the real cause is in `status`:

```bash
specrunway status --execution "$EXEC" --json
```

```json
"last_failure": {
  "step_id": "implement:repo:0",
  "code": "agent-failed",
  "message": "agent did not complete: exit 1",
  "log_path": "…/logs/repo-a/1/agent.log",
  "details": {"attempt": 1, "repo_id": "repo-a"}
}
```

Read the named log first. If the failure is retryable, `specrunway resume`
re-runs only the failed native step. If resume is not appropriate, or the
execution is a dead end, release the checkout explicitly:

```bash
specrunway abandon --execution "$EXEC" --json
specrunway run --change <next-change> --json
```

`abandon` refuses with `owner-alive` while the recorded owner process is still
running. Check `ps -p <pid>`; stop that process before retrying. It leaves the
execution's state, results, receipts, and worktrees in place so the failure can
still be reviewed. Never delete `active.json` or rewrite `state.json` by hand.

## orphan-alive (recover refuses)

```text
[orphan-alive] process 12345 still owns the checkout; confirm it stopped
before recover
```

The active-owner record still points at a live process. Do not start another
run and do not edit the native run state.

1. Identify the process: `ps -p <pid> -o pid,ppid,command`.
2. Stop it from its original terminal, or terminate that process (and its
   group only if you are sure no unrelated process shares it).
3. Confirm it is gone: `ps -p <pid>` should report no process.
4. Run `specrunway recover --execution "$EXEC" --json`.

`recover` preserves the old native run with status `abandoned-running`, marks
the execution `interrupted`, and starts a new native run under the same
`execution_id`. Verified results, receipts, and worktrees may be reused only
after the digest, commit, and trusted-test checks still pass.

If `ps` shows a different command for the recorded pid, the pid was reused by
an unrelated process. Confirm the SpecRunway owner is gone; never terminate an
unrelated process just to clear the check. Never delete or rewrite `state.json`
to bypass the owner check.

## blocked: budget or no progress

`budgets` records attempts and repairs used. Defaults are three repository
attempts, two integration repair rounds, and 120 minutes total.

- `budget-exhausted`: stop. A human must inspect the worktree, logs, and test
  evidence, then decide whether to repair manually or start a new execution
  with a corrected request or budget. `last_failure.details` keeps the
  `elapsed_minutes` and `total_minutes` that triggered the refusal.
- `freeze-stale`: the frozen snapshot is older than the total-time limit and
  no repository attempt was spent. Re-freeze with
  `specrunway run --change <change_id>` so base commits and approved inputs are
  current; do not resume the old freeze.
- `no-progress`: the same failure repeated at the same head. Do not loop; fix
  the underlying cause and start a new execution.
- `execution-blocked` from `resume`: the execution is already blocked.
  `resume` will not clear it.

Blocked executions never become `ready_for_review` automatically. Preserve the
worktrees and logs until the investigation is complete.

## Archive refuses

Run archive only at `ready_for_review`. Each refusal is a specific missing
condition:

| Code | Meaning | Fix |
| --- | --- | --- |
| `not-ready` | Phase is not `ready_for_review`. | Finish approvals and the implementation gate. |
| `unaccepted-code` | A repository result or verification is missing, or mapped tasks are unchecked. | Inspect `results`, `verification`, and `tasks.md`; complete or repair the run. |
| `tasks-missing` | The Store change has no `tasks.md`. | Restore the change content; do not fabricate checkboxes. |
| `verification-stale` | Final trusted tests failed, the worktree is gone, or the tested head differs from the accepted head. | Fix the test environment or restore the worktree and retry; if the accepted head changed or the worktree is gone, start a new execution. Do not edit the worktree to fake a match. |
| `no-approval` | No implementation receipt exists. | Approve the implementation after results are accepted. |
| `approval-mismatch`, `approval-stale` | The receipt no longer binds the accepted results or current content. | Re-review and re-approve the implementation; if planning changed, create a new execution. |
| `partial-merge` | Accepted heads are not contained in the base ref. | Merge every accepted head, refresh the local base ref, and retry. |
| `confirmation-required` | `validated_commits` was selected without confirmation. | Re-run with `--confirm-validated`, or use the manifest policy. |
| `policy-unknown` | The selected policy is not `merged_commits` or `validated_commits`. | Correct `--policy` or the manifest. |
| `repo-unknown` | A repository in the snapshot is missing from the manifest. | Preserve the run; the snapshot and manifest disagree. |
| `archive-uncertain` | OpenSpec archive failed or its result could not be verified. | Run `specrunway recover` and inspect the backup; never replay blindly. |
| `archive-mixed` | Both active and archived change paths exist. | Preserve both, inspect the backup and Store, and repair manually. |
| `archive-lost` | Neither active nor archived change path remains. | Preserve the run; manual Store repair is required. |

Archive backup for an attempt:
`.specrunway/runs/<execution>/archive-backup/<stamp>/` contains the pre-archive
change tree, `before.json`, and (on success) `after.json`.

If the process died after OpenSpec archive but before the receipt:

```bash
specrunway recover --execution "$EXEC" --json
```

Recovery proves the actual active/archived path. If it records a receipt, the
execution becomes `archived`; if the active change still exists and no archive
copy does, recovery marks the intent not applied and reopens
`ready_for_review` when the phase was blocked. Mixed state remains blocked.

## Nested Store path

OpenSpec refuses a Store nested inside another Git checkout. The wizard checks
this before registration and reports:

```text
[wizard-store-inside-git] Store path ... is inside the Git repository ...;
choose a directory outside it
```

The default depends on the control directory:

- outside any checkout: `<control>/openspec-store`;
- inside a checkout: a sibling of the enclosing checkout, named
  `<enclosing-checkout>-specrunway-store`.

Fix an existing `local.yaml` by moving `store.path` outside every checkout, or
by re-running `specrunway wizard --reconfigure` and accepting the suggested
sibling. Then run `specrunway init` again to register the new path. Do not put
a Store under a business repository, and do not point `store.path` at a
subdirectory of an existing checkout.

A local control checkout such as `.sr-control/` inside a repository is runtime
wiring, not a Store. It is ignored by Git, and `check_handoff.py` skips
dot-directories; never commit its run state.

## Approval drift

`approval-mismatch` or `approval-stale` means the approved subject changed.
The plan digest excludes only checkbox markers; task text, dependencies,
routing, design, specification, and acceptance content all count. Repository
rule files (`AGENTS.md`, `CLAUDE.md`) feed the frozen context digest; changing
them after freeze does not rewrite the snapshot.

`run --continue` checks the receipt only against the frozen snapshot. Use
`specrunway resume` when you need the live planning bytes revalidated; that
check is where a post-freeze plan edit surfaces as `approval-stale`.

A changed approved input cannot be repaired by re-approving the old execution:
the frozen subject is immutable. Start a new execution from the current plan
and approve it again. Checkbox-only edits preserve the planning digest.

## Result rejected

Accepted results are independently validated. Common rejections:

| Code | Meaning |
| --- | --- |
| `result-missing`, `result-invalid` | The agent did not write a parseable, correctly shaped `result.json`. |
| `result-committed` | `result.json` was committed; evidence must stay untracked. |
| `execution-mismatch`, `repo-mismatch` | The result names a different execution or repository. |
| `base-mismatch` | `base_commit` is not the frozen base OID. |
| `head-not-descendant` | The head is missing or does not descend from the frozen base. |
| `path-not-allowed`, `path-unsafe` | A changed path is outside `allowed_paths` or is not a safe relative path. |
| `task-unmapped` | The result reports a task outside this repository's routing. |
| `receipt-missing` | No trusted test receipt exists for this repository and attempt. |
| `receipt-mismatch`, `receipt-command-mismatch` | The agent's claimed test status or command disagrees with the trusted receipt. |
| `digest-mismatch` | `result_digest` does not bind the result payload. |
| `stale-result` | The result does not match the frozen execution inputs. |

Do not fix these by editing `result.json` after the fact or by changing
`tests_claimed` to match. The trusted runner's receipt is the evidence. Fix
the code or routing and let the bounded repair retry, or hand over.

## Tool and version errors

`tool-missing` reports an OpenSpec executable that could not be resolved.
Specify and agent launch failures surface as their own error or as a workflow
failure; read the message tail and the agent log. The resolution order prefers
a control-local `tooling/openspec/node_modules/.bin`, then the package
checkout's pinned tools, then `.venv/bin`, then `PATH`. A stale local tool can
shadow the intended binary.

```bash
specrunway --version
opencode --version
specify version
openspec --version
```

Expected: specrunway 0.1.0, opencode 2.1.4 or newer, specify-cli 1.2.1,
OpenSpec 1.15.0. `specrunway doctor` checks wiring and runs a bounded
coding-agent preflight; it does not verify other executable versions or run
tests. See `docs/TOOLCHAIN.md` for the full resolution order.

## doctor reports agent-preflight

`agent-preflight` means the configured coding agent cannot answer. The finding
names the profile and binary, and `data.agent` carries the status, exit code,
and a bounded log tail:

| `data.agent.status` | Meaning | Fix |
| --- | --- | --- |
| `missing-binary` | The profile's executable is not on `PATH`. | Install the agent or fix `PATH`; `--version` should work. |
| `unknown-profile` | `local.yaml agent_profile` names no shipped profile. | Use `primary-coding-agent` or correct the wiring. |
| `failed` | The probe exited non-zero, commonly because no model is usable. | Configure a provider/model in the agent's own config and rerun `doctor`. |
| `timeout` | The agent did not answer within 60 seconds. | Check network and provider latency; the real run would also stall. |

The probe runs in a temporary directory with a one-line prompt, so it never
spends repository work. Fix the agent before `specrunway run`.

## Lock timeout or concurrent execution

`lock-timeout` means another process holds the checkout lock.
`execution-conflict` means a different execution is active. There is one
active execution per control/Store checkout.

Find the process from `status.active_owner` or from the error context, stop it,
and retry. If the owner is dead and the execution is paused or failed, release
it with `specrunway abandon --execution <id>` instead of deleting state. Do not
delete the lock file while a process may still be writing. Do not run two
executions against the same Store or control checkout.

## Where the evidence is

```text
<control>/.specrunway/runs/<execution_id>/
  state.json          # phase, gates, budgets, results, verification, approvals
  snapshot.json       # frozen manifest, digests, base OIDs, profiles
  approvals/          # plan.json, implementation.json
  results/            # accepted result.json copies per repo and attempt
  tests_receipts/     # trusted runner receipts per repo and attempt
  operations/         # intents, receipts, uncertainty records
  worktrees/          # detached worktrees per repository
  logs/               # agent and test logs
  prompts/            # generated per-repository prompts
  archive-backup/     # pre/post archive evidence, when archive ran
```

Use the logs and receipts to diagnose; do not share sensitive raw logs. Keep
only sanitized evidence when recording a failure.

## Do not

- Do not edit `.specify` private run state to make a running run resumable.
- Do not rewrite `state.json`, approval files, result files, or receipts.
- Do not delete worktrees, logs, or backups before the failure is understood.
- Do not re-run archive after `archive-uncertain` or `archive-mixed`.
- Do not hand-edit `tasks.md` checkboxes to satisfy archive.
- Do not treat an agent's success message as test evidence.
