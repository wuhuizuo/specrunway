# Design

## Context

Read `docs/DESIGN.md`, `docs/DECISIONS.md`, the archived
`openspec/specs/trusted-verification/spec.md`, and the requirements in this
change. The v1 baseline already accepts per-repository results, runs trusted
per-repository tests, and repairs repository failures within budgets.

## Goals and boundaries

Execute the configured integration profile against the accepted commit
matrix, block global completion when it fails, and keep bounded,
persistent integration repair accounting. Do not add a service, scheduler,
parallelism, or a provider registry. Commands stay trusted configuration;
agent prose never becomes an integration command.

## Decisions

- **Profile location**: the trusted control checkout owns executable
  arguments in `local.yaml` under optional
  `integration_profiles: {<name>: {command: [...], repo?: <repo_id>,
  timeout_seconds?: int}}`. The manifest keeps naming the profile. Absolute
  paths stay out of shared manifests and Store artifacts.
- **Freeze**: `hub run` resolves the named profile, validates it, and stores
  `snapshot.integration = {profile, command, cwd_repo, timeout_seconds,
  config_digest}` so a later edit cannot silently change verification.
  Missing or unknown profiles refuse execution before any agent runs.
- **Matrix**: the runner writes `matrix.json` (repo id, accepted head,
  result digest, verification status) and exports
  `SPECRUNWAY_MATRIX` plus `SPECRUNWAY_HEAD_<repo_id>` to the integration
  command, running it in the configured repo worktree (default: first repo
  in `repo_order`).
- **Flow**: workflow step `integration-round` runs after `repair-round` and
  before `accept-tasks`. It requires accepted + verified results, executes
  the profile, persists the receipt and state row, and returns
  `needs_repair` on an ordinary failing result.
- **Repair**: an integration failure re-attempts the last repository in
  `repo_order` with the integration log tail as explicit feedback, then
  re-runs trusted repository tests and the integration profile. The loop is
  bounded by `integration_max_repairs`; identical failure signatures at an
  unchanged matrix head stop as `no-progress`; exhausted budget and repeated
  failure enter phase `blocked` and never reach `ready_for_review`.
- **Counters**: `state.integration_repairs` counts consumed integration
  repair rounds and is only written by compare-and-swap state updates, so a
  restarted CLI or recovered native run cannot reset it.
- **Completion guard**: `complete` requires an accepted, passed integration
  receipt bound to the current matrix digest in addition to the existing
  repository evidence. When no integration profile is frozen (legacy
  executions or narrow step tests), the guard reports
  `integration-required` rather than silently passing.

## Implementation slices

- **L16**: profile schema + validation; freeze; matrix runner; workflow step;
  bounded repair; persistent counters; completion guard; tests, evidence, and
  runbook/docs updates.

## Verification

Use deterministic integration commands in tests: a passing command, one that
fails until a marker exists, one that always fails, and one that fails
identically twice. Prove: failure blocks completion, feedback reaches the
repairing agent, attempts and integration rounds are bounded, no-progress
stops early, counters survive a fresh store handle, and the completion guard
refuses missing/stale integration evidence. Run the full suite, strict
OpenSpec validation, and a real CLI workflow replay. Record commands, exit
codes, and sanitized evidence.

## Risks and trade-offs

A combined check may itself be flaky or environment-dependent; v1 records the
exact command and matrix, so failures are inspectable rather than retried
blindly. Integration repair targets the last repository by design; a change
that needs coordinated edits in several repositories still fits the operator
takeover path after the bounded rounds. Legacy snapshots without an
integration profile remain readable but cannot pass the new completion guard.
