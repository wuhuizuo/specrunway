# Design

## Context

Read `docs/DESIGN.md`, `docs/DECISIONS.md`, and the requirements in this change. This slice covers L02, L03, L04, L05. Its prerequisite is 01-verify-upstream-contracts; prepared planning files do not prove that prerequisite passed.

## Goals and boundaries

The CLI, schemas, explicit Store adapter, and local state/locking work in disposable fixture repositories.

Implement no optional or v2 behavior. Keep product business state and runtime engine state distinct. Bootstrap probes call upstream tools directly; application code uses the narrow ports and typed adapters in the full design.

## Decisions

Use exact, measured upstream versions; one Python package; explicit repo ordering; separate worktrees; frozen inputs; trusted test execution; and coordinator-owned task acceptance. Preserve existing `specrunway` and `specrunway/v1` contracts. Use the public Specify custom-step API rather than private state or engine patches.

For the initial probes, prove custom-step import visibility inside the actual Specify Python environment. For later implementation, result evidence must bind repo/task/execution IDs, input digests and actual commits. Native running recovery creates a new native run only after reconciliation and confirmed process termination.

## Implementation slices

- **L02**: specrunway CLI; control and Store checkouts; ignored runtime files. Commands find the SpecRunway. Business repositories need no new tool configuration. No server or database is introduced.
- **L03**: specrunway/v1 object schemas; manifest and local.yaml validation. Define manifest/snapshot/result/approval/receipt schemas. Validate IDs, repo/dependency order, remote identity, paths, profiles, and acceptance coverage.
- **L04**: argv wrappers for create, status, instructions, validate, archive. Use explicit --store and shell=False. Separate planning completion from implementation completion. Reject unsupported critical protocol data.
- **L05**: FileRunStore; atomic writes; active execution; receipts. Only one execution owns a control/Store checkout. Replace state atomically and record intent before external side effects.

## Verification

Each task in tasks.md has an observable check. Use real pinned OpenSpec/Specify tools for integration contracts, deterministic fake agents for repeatable failure injection, and a recorded real agent profile for final release acceptance. Keep command output and exit codes; do not mark unsupported or unavailable checks passed.

## Risks and trade-offs

Upstream behavior may differ from examples: stop dependent integration and record the measured adapter change. Local worktrees do not enforce hostile-process isolation. Side effects can complete without a receipt: reconcile actual Git/filesystem state before retrying. Parent and child work must share explicit budgets rather than multiply retries invisibly.

## Delivery and follow-up

Keep tests and operational documentation with the behavior they introduce. Update the implementation checkpoint and acceptance evidence. Development-change archive follows completion and applicable review; it is outside tracked implementation tasks. Product archive follows the separate completion policy.
