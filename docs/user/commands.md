# Command reference

Every command is run from the control checkout (or with an explicit `--root`).
The CLI walks upward from the current directory looking for `local.yaml`.

## Conventions

- `specrunway --version` prints `specrunway 0.1.0`.
- `--json` emits the `specrunway/v1` envelope on stdout. Without it, commands
  print one human-readable line and errors go to stderr.
- Success exits 0. A refused or failed command exits 1. Argument parsing
  errors (unknown flag, missing positional argument) exit 2 through argparse.
- A successful envelope is:

  ```json
  {
    "api_version": "specrunway/v1",
    "action": "run",
    "ok": true,
    "data": {},
    "warnings": []
  }
  ```

- A failed envelope is:

  ```json
  {
    "api_version": "specrunway/v1",
    "action": "run",
    "ok": false,
    "data": {},
    "error": {
      "code": "no-approval",
      "message": "no plan approval receipt; the gate refuses to advance"
    }
  }
  ```

  `error.errors` is present when validation produced a list of findings.
  `doctor` uses a report shape instead: `data.findings`, plus `errors` as a
  list of finding codes.

- Error codes identify the failure. Most are lowercase kebab-case; a structural
  failure can surface its exception name (for example `RuntimeError` when no
  control checkout can be found). Treat the code as stable and the message as
  explanatory.

## Command summary

| Command | Required input | Purpose |
| --- | --- | --- |
| `wizard` | interactive answers | Configure the control checkout and draft or plan a change |
| `init` | `local.yaml` | Register the Store, initialize Specify, install the step |
| `doctor` | `local.yaml` | Check control wiring and report findings |
| `plan` | `CHANGE_ID` | Generate or accept planning artifacts and routing |
| `run` | `--change` or `--execution --continue` | Freeze/start or continue an execution |
| `approve` | `--execution --kind --actor` | Record a local approval receipt |
| `status` | `--execution` | Show phase, gates, results, budgets, operations |
| `resume` | `--execution` | Resume a paused/failed execution after revalidation |
| `recover` | `--execution` | Reconcile an interrupted execution or archive |
| `archive` | `--execution` | Explicitly archive a ready change |

## Shared runtime codes

These can appear from more than one command that reads or mutates run state:

| Code | Meaning and next action |
| --- | --- |
| `snapshot-missing` | The execution has no frozen `snapshot.json`. Check the execution id; do not edit run files. |
| `lock-timeout` | Another process holds the checkout lock. Wait or stop the other SpecRunway process. |
| `execution-conflict` | A different execution is active for the checkout. Finish or release it before starting another. |
| `state-corrupt` | `state.json` is unreadable or foreign. Preserve the run directory and inspect it manually. |
| `no-execution` | The execution id has no run directory. List `.specrunway/runs/` and retry. |
| `revision-conflict` | State changed under a writer. Re-run the read/status command; do not force-write state. |
| `tool-missing` | The OpenSpec CLI could not be found. A missing Specify or agent executable surfaces as a launch or workflow failure; read the message tail. Compare versions and resolution order with `docs/TOOLCHAIN.md`. |
| `timeout` | An OpenSpec call exceeded its timeout. Check the upstream process and retry. |
| `upstream-error` | OpenSpec returned an unrecognized failure. Read its stderr tail in the message. |

Each command below lists its additional codes. A shared code may also appear
when the command reads or writes run state.

## `specrunway wizard`

```bash
specrunway wizard [--root DIR] [--reconfigure] [--change ID]
                  [--description TEXT] [--request FILE] [--manifest FILE]
                  [--skip-init] [--skip-plan] [--force] [--json]
```

Required input is interactive; there are no required flags. The wizard asks
for control wiring, writes `local.yaml`, runs the `init` bootstrap, asks for
change details and routing, writes `requests/<change>.md` and
`.specrunway/requests/<change>.manifest.yaml`, adds change-scoped test
profiles, and calls `plan`.

Stable codes: `wizard-root-missing`, `wizard-eof`, `wizard-store-inside-git`,
`wizard-repos-required`, `wizard-repo-missing`, `wizard-repo-not-git`,
`wizard-repo-selection`, `wizard-tasks-required`, `wizard-integration-repo`,
`wizard-command`, `wizard-allowed-path`, `wizard-overwrite-declined`,
`wizard-request-missing`. Bootstrap and planning failures surface their own
codes (`specify-init-failed`, `step-install-failed`, `plan-*`, `tool-missing`,
`upstream-error`).

Next action: `specrunway run --change <change_id> --json`.

## `specrunway init`

```bash
specrunway init [--root DIR] [--json]
```

Requires an existing valid `local.yaml`. It creates and registers the configured
Store, initializes `.specify` only when absent, and installs the bundled
`specrunway` step. It is idempotent; its control files stay inside the control
checkout, while the Store is created at the configured path.

Stable codes: `local-yaml-missing`, `specify-init-failed`,
`step-install-failed`, `doctor-failed`, plus `tool-missing`, `upstream-error`,
and `timeout` from upstream calls. `doctor-failed` means bootstrap completed
but a wiring finding still needs attention; the envelope includes the
findings.

Next action: `specrunway doctor --json`, then `specrunway plan`.

## `specrunway doctor`

```bash
specrunway doctor [--root DIR] [--json]
```

Required input is a control checkout with `local.yaml`. The report includes
`specrunway_version`, `control_root`, `store`, `agent_profile`, `repos`, and
`findings`. Exit code is 0 only when there are no errors.

Finding codes: `no-control-checkout`, `local-yaml`, `store-missing`,
`store-uninitialized`, `repo-missing`, `repo-not-git`, `remote-missing`,
`wrong-checkout`, plus `local.yaml` validation codes such as `store-id`,
`store-path`, `repo-path`, `remote-identity`, `test-command`, and
`unknown-key`.

`doctor` does not probe executable versions or run tests.

Next action: fix every error finding, then `specrunway plan` or
`specrunway run`.

## `specrunway plan`

```bash
specrunway plan CHANGE_ID [--store STORE_ID] [--request FILE]
                 [--manifest FILE] [--root DIR] [--json]
```

`CHANGE_ID` is required. `--store` is optional but, when supplied, must match
`local.yaml`; a mismatch is `store-unknown`. `--request` supplies the brief
used to generate artifacts for a new or incomplete change. `--manifest`
supplies explicit routing and is required for a manual plan whose tasks have no
routing labels.

Stable codes: `store-unknown`, `plan-request-required`, `plan-incomplete`,
`manifest-required`, `manifest-unreadable`, `manifest-type`, `task-routing`,
and manifest validation codes such as `unknown-key`, `repo-*`, `task-*`,
`acceptance-*`, `budget-*`, `forward-dependency`, `unknown-dep`,
`unknown-profile`, and `test-profile`. Upstream calls may return
`tool-missing`, `timeout`, `upstream-error`, `unknown_store`,
`no_registered_stores`, or `change-exists`.

Next action: `specrunway run --change <change_id> --json`. Planning success
does not mean implementation is complete.

## `specrunway run`

New execution:

```bash
specrunway run --change CHANGE_ID [--root DIR] [--json]
```

Continue a paused execution after its approval receipt exists:

```bash
specrunway run --execution EXECUTION_ID --continue [--root DIR] [--json]
```

`--change` freezes a new execution and starts the native workflow. `--execution`
without `--continue` is rejected (`execution-conflict`); `--continue` without
`--execution` is rejected (`execution-required`). `--continue` checks the
pending approval receipt against the frozen snapshot; use `resume` when you
also need live plan revalidation.

Stable codes: `manifest-missing`, `change-missing`, `repo-unconfigured`,
`execution-conflict`, `execution-required`, `specify-not-initialized`,
`workflow-output`, `workflow-failed`, `run-not-started`, plus the shared
runtime codes and gate codes (`no-approval`, `approval-rejected`,
`approval-mismatch`, `approval-corrupt`).

The envelope reports `execution_id`, `native_run_id`, `native_status`,
`paused_step_id`, and a `next` hint. A plan-gate pause has
`paused_step_id: "plan-gate"`; an implementation-gate pause has
`paused_step_id: "implementation-gate"`.

Next action: record the matching approval and run `--continue`, or use
`specrunway resume`. On `workflow-failed`, inspect the message tail; retry with
`specrunway resume` when a native run exists, otherwise start again with
`run --change`. Do not edit `.specify` state.

## `specrunway approve`

```bash
specrunway approve --execution EXECUTION_ID --kind {plan,implementation}
                   --actor NAME [--decision {approve,reject}]
                   [--root DIR] [--json]
```

All three of `--execution`, `--kind`, and `--actor` are required.
`--decision` defaults to `approve`. The subject digest is recomputed from
frozen content: `plan` binds the planning digest, `implementation` binds the
accepted-results tree. A rejected decision is recorded but the gate will refuse
to advance (`approval-rejected`).

Stable codes: `approval-kind`, `result-required` (implementation approval
before any accepted result), `no-execution`, `snapshot-missing`,
`state-corrupt`, `revision-conflict`.

Next action: `specrunway run --execution <id> --continue` or
`specrunway resume --execution <id>`.

## `specrunway status`

```bash
specrunway status --execution EXECUTION_ID [--root DIR] [--json]
```

Requires `--execution`. Data includes `phase`, `pending_gate`,
`native_run_id`, `native_runs`, `revision`, `active_owner`, `budgets`,
`results`, `verification`, `approvals`, `change_id`, `repo_order`, and
`operations`.

Stable codes: `snapshot-missing`, `no-execution`, `state-corrupt`.

Next action by phase:

| Phase | Next action |
| --- | --- |
| `planning` | Preparation did not finish. Read the last run error; retry `run --change` if the execution was never started. |
| `awaiting_plan_review` | Review the plan, then `approve --kind plan` and continue. |
| `implementing` | Wait, or `resume` if the native run is paused/failed. |
| `awaiting_implementation_review` | Review accepted results, then `approve --kind implementation` and continue. |
| `ready_for_review` | Merge if using `merged_commits`, then `archive`. |
| `blocked` | Read `blocked_reason` and `budgets`; hand over to a human. |
| `interrupted` | `recover`. |
| `archived` | No further execution work. |

## `specrunway resume`

```bash
specrunway resume --execution EXECUTION_ID [--root DIR] [--json]
```

Requires `--execution`. Before resuming, it revalidates that live planning
content still matches the frozen `planning_digest`, and it rechecks any pending
gate receipt. It uses the native resume path, so completed steps are not
re-run. Use it for a gate pause or a retryable native failure.

Stable codes: `no-approval`, `approval-rejected`, `approval-mismatch`,
`approval-corrupt`, `approval-stale`, `change-missing`, `orphan-running`,
`execution-blocked`, `run-not-started`, `specify-not-initialized`,
`workflow-output`, `workflow-failed`, plus `snapshot-missing`.

`orphan-running` means the native run still reports running. Do not force it;
use `recover` to confirm the owner process has stopped.

Next action: approve the pending gate, fix the reported drift, or use
`recover`.

## `specrunway recover`

```bash
specrunway recover --execution EXECUTION_ID [--root DIR] [--json]
```

Requires `--execution`. Recovery first reconciles a pending or uncertain
archive. For a running native run it checks the active owner process: if the
owner is alive it refuses; if the owner is dead it preserves the old run as
`abandoned-running`, marks the execution `interrupted`, and starts a new native
run under the same `execution_id`. For a paused or failed native run it
revalidates the live plan and resumes. Verified results and receipts may be
reused only after their digests, commits, worktrees, and test receipts still
match.

Stable codes: `orphan-alive`, `evidence-conflict`, `archive-mixed`,
`archive-lost`, `run-not-started`, `change-missing`, `approval-stale`,
`specify-not-initialized`, `workflow-output`, `workflow-failed`,
`snapshot-missing`.

Next action: stop the process named in `orphan-alive` and retry; for
`evidence-conflict`, preserve the scene and start a new execution; for archive
codes, see [troubleshooting.md](troubleshooting.md).

## `specrunway archive`

```bash
specrunway archive --execution EXECUTION_ID
                   [--policy {merged_commits,validated_commits}]
                   [--confirm-validated] [--root DIR] [--json]
```

Requires `--execution`. The policy defaults to the manifest's
`completion_policy` (normally `merged_commits`). `validated_commits` also
requires `--confirm-validated`. Preflight requires the `ready_for_review`
phase, accepted and verified results for every repository, checked mapped
tasks, a current implementation approval, fresh trusted final tests at the
accepted heads, and (for `merged_commits`) accepted heads contained in each
base ref.

Stable codes: `not-ready`, `unaccepted-code`, `tasks-missing`,
`verification-stale`, `repo-unknown`, `no-approval`, `approval-mismatch`,
`approval-stale`, `policy-unknown`, `confirmation-required`, `partial-merge`,
`archive-uncertain`, `archive-mixed`, `archive-lost`, plus `snapshot-missing`,
`tool-missing`, `upstream-error`, and `timeout`.

A successful re-run of an already archived execution returns
`already_archived: true` instead of applying deltas again.

Next action: none on success. On refusal, use
[troubleshooting.md](troubleshooting.md); do not delete the backup or retry a
mixed/uncertain outcome blindly.
