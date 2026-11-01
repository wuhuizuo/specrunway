# Core concepts

SpecRunway coordinates one OpenSpec change across one or more Git
repositories. This page defines the objects an operator sees and the lifecycle
that connects them. Commands are in [commands.md](commands.md); recovery steps
are in [troubleshooting.md](troubleshooting.md).

## The control checkout

The control checkout is a local directory that holds machine-specific wiring
and runtime state:

```text
<control>/
  local.yaml                         # Store, repositories, agent, test profiles
  requests/<change>.md               # reviewable request (wizard output)
  .specrunway/
    plans/<change>/manifest.yaml      # routing manifest used by run
    plans/<change>/plan-summary.json  # human-readable planning summary
    requests/<change>.manifest.yaml   # wizard routing before plan
    runs/<execution_id>/              # one execution's frozen inputs and state
  .specify/                           # native Specify workspace and run state
```

`local.yaml` lives only in the control checkout. Business repositories are
normal Git checkouts; SpecRunway does not initialize OpenSpec, Specify, or any
coordinator files inside them.

## Change

A **change** is an OpenSpec change stored in the central Store:

```text
<store>/openspec/changes/<change_id>/
  proposal.md
  design.md
  tasks.md
  specs/<capability>/spec.md
```

The `change_id` is a stable business identity. Within a repository's
`tasks.md` section, each task has the form:

```text
- [ ] 1.1 [T001] Add quota enforcement.
```

`T001` is the routing identity. The SpecRunway manifest maps every declared
task id to exactly one repository, one test profile, and one set of allowed
paths. The routing manifest also carries `store_uid` and `change_uid`; these
survive moves such as archive, while repository ids and task ids identify
routing.

Planning artifacts and task checkboxes are separate. Completing planning does
not check boxes, accept results, or archive the change.

## Execution

An **execution** is one frozen attempt to implement one change:

- `execution_id` is a UUID and the stable business identity. Use it for every
  `status`, `approve`, `resume`, `recover`, and `archive` call.
- A **native run id** identifies one Specify workflow run. It is a runtime
  identity. An explicit `recover` may preserve the old native run and create a
  new one under the same `execution_id`.
- Only one execution may be active per control/Store checkout. The run
  controller (prepare, start, continue, resume, and recover) takes a file lock
  and an active-owner record; a second writer fails with `lock-timeout` or
  `execution-conflict`.
- Execution state, budgets, accepted results, and operation receipts live under
  `.specrunway/runs/<execution_id>/` and survive process restarts.

`specrunway run --change <id>` prepares and starts an execution. `specrunway
run` does not reuse an existing execution unless you pass `--execution <id>
--continue`.

## Frozen snapshot

`run` writes `snapshot.json` before any agent work. The snapshot freezes:

- the routing manifest bytes and the manifest digest;
- the planning digest over proposal, design, specification deltas, task text,
  and the full routing manifest (routing, allowed paths, test profiles,
  acceptance criteria, budgets, and completion policy);
- the context digest, including repository rules and referenced constraints;
- each repository's resolved base commit OID and declared remote identity;
- the test profiles (`command`, `cwd`, `timeout_seconds`, digest) and the
  optional integration profile;
- the tool and agent-profile versions.

The snapshot is immutable for the execution. Editing `local.yaml`, the Store
plan, or a test profile after freezing does not change a running execution.
Changed approved inputs require a new execution, not a resumed one.

The planning digest excludes only checkbox markers. Changing task text,
dependencies, routing, acceptance criteria, or design content changes the
digest and invalidates an earlier plan approval.

## Approval receipt

An **approval receipt** is the operator's local confirmation that a specific
frozen subject was reviewed:

```json
{
  "api_version": "specrunway/v1",
  "execution_id": "...",
  "kind": "plan",
  "decision": "approve",
  "subject_digest": "<sha256>",
  "scope": "planning_snapshot:<change_id>",
  "actor": "alice",
  "auth_level": "self_asserted",
  "timestamp": "2026-11-01T10:00:00Z"
}
```

Receipts are stored in `.specrunway/runs/<execution_id>/approvals/<kind>.json`.

- A **plan** receipt binds `snapshot.planning_digest`.
- An **implementation** receipt binds the accepted-results tree: each accepted
  repository's `repo_id`, `attempt`, `head_commit`, and `result_digest`.
- `approve` recomputes the subject digest from frozen content; the caller
  cannot supply an arbitrary digest.
- The gate refuses to advance without a receipt (`no-approval`), with a
  rejected decision (`approval-rejected`), or when the receipt no longer binds
  the subject (`approval-mismatch` or `approval-stale`).

`auth_level` is always `self_asserted` in local v1. It records local
confirmation and drift detection; it is not authenticated team authority and
cannot be promoted to one by copying a file.

The CLI exposes `--kind plan` and `--kind implementation`. Archive is guarded
by explicit preflight and the completion policy rather than by a separate
approval command in v1.

## Trusted result

The coding agent writes `result.json` in its worktree. That file is untrusted
input. A **trusted result** exists only after the coordinator has independently
checked:

- execution, repository, and task identities match the frozen routing;
- `base_commit` equals the frozen base OID;
- `head_commit` exists and descends from that base;
- every `changed_paths` entry is a safe relative path inside the manifest's
  `allowed_paths`;
- `result.json` is not committed to Git;
- a trusted test receipt exists for the same repository and attempt, and the
  agent's `tests_claimed` status and optional command agree with that receipt;
- `result_digest` binds the result payload.

The trusted test receipt comes from the frozen test profile executed by
SpecRunway, not from the agent's prose. An accepted copy is stored under
`.specrunway/runs/<execution_id>/results/<repo_id>/<attempt>/result.json` and
mirrored in state. Only then can the coordinator flip the mapped `tasks.md`
checkboxes, and only accepted results can support the implementation approval.

## Operation intent

Some actions have external effects: starting a repository attempt, accepting
tasks in the Store, and archiving. Before each effect, SpecRunway writes an
**operation intent** with a stable operation key. The record moves through:

| Status | Meaning |
| --- | --- |
| `pending` | Intent written; the effect may not have happened yet. |
| `recorded` | The effect succeeded and a receipt binds its evidence. |
| `uncertain` | The process cannot prove whether the effect happened. |
| `reconciled` | A later check proved the actual outcome against Git, result files, or archive paths. |

An uncertain outcome is never replayed blindly. `specrunway recover`
reconciles it from observable state; archive is especially strict, because
re-applying OpenSpec deltas would corrupt the Store. A pending intent with no
receipt is not evidence that the work succeeded.

## Worktrees and budgets

Each repository in an execution has a separate Git worktree under
`.specrunway/runs/<execution_id>/worktrees/<repo_id>`, detached at the frozen
base OID. Repairs reuse that worktree. The original checkout is preserved. A
worktree separates ordinary edits; it is not a security sandbox against a
hostile process running as the same OS user.

Budgets are frozen from the manifest and persisted across resume and recover:

- `repo_max_attempts` (default 3) bounds initial implementation plus repairs
  per repository;
- `integration_max_repairs` (default 2) bounds integration repair rounds;
- `total_minutes` (default 120) bounds the execution wall clock.

Exhaustion or a repeated failure at the same evidence stops the execution in
`blocked`. A blocked execution is a handover point, not a retry loop.

## Lifecycle

```text
specrunway plan
      |
      v
planned: proposal/design/tasks/specs exist, tasks unchecked
      |
      | specrunway run --change <id>
      v
awaiting_plan_review  -- approve plan + run --continue -->  implementing
                                                              |
                                                              | run-repo, trusted tests,
                                                              | verify, bounded repair,
                                                              | optional integration
                                                              v
                                              awaiting_implementation_review
                                                              |
                                                              | approve implementation
                                                              | + run --continue
                                                              v
                                                       ready_for_review
                                                              |
                                                              | explicit merge
                                                              | + specrunway archive
                                                              v
                                                          archived

Any active phase may become:
  blocked       budget exhausted, no progress, or uncertain archive
  interrupted   orphaned running native run preserved by recover
```

The shipped CLI reports `implementing` while repository work, verification,
repair, and integration execute. Per-repository verification rows are visible
in `status --json` under `verification`.

`ready_for_review` means the implementation evidence was reviewed and
accepted. Merging, pushing, deploying, and archiving remain explicit operator
actions.

## What local v1 does not claim

- Approval is `self_asserted`, not authenticated team identity.
- A worktree is not a hostile-process sandbox.
- One control checkout has one active execution; there is no shared queue or
  cross-machine lock.
- Tests are trusted because the configured runner executed them, not because
  an agent said so.
- Archive applies the OpenSpec change locally; it does not publish or push the
  Store.
