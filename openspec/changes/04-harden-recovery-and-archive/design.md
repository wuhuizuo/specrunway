# Design

## Context

Read `docs/DESIGN.md`, `docs/DECISIONS.md`, and the requirements in this change. This slice covers L13, L14. Its prerequisite is 03-deliver-two-repo-loop; prepared planning files do not prove that prerequisite passed.

## Goals and boundaries

Resume/recover and archive fault cases reconcile safely; partial merge and stale evidence block archive.

Implement no optional or v2 behavior. Keep product business state and runtime engine state distinct. Bootstrap probes call upstream tools directly; application code uses the narrow ports and typed adapters in the full design.

## Decisions

Use exact, measured upstream versions; one Python package; explicit repo ordering; separate worktrees; frozen inputs; trusted test execution; and coordinator-owned task acceptance. Preserve existing `specrunway` and `specrunway/v1` contracts. Use the public Specify custom-step API rather than private state or engine patches.

For the initial probes, prove custom-step import visibility inside the actual Specify Python environment. For later implementation, result evidence must bind repo/task/execution IDs, input digests and actual commits. Native running recovery creates a new native run only after reconciliation and confirmed process termination.

## Implementation slices

- **L13**: Paused/failed resume; orphan-running reconciliation. Do not edit Spec Kit private state. Recover an orphan running run through reconciliation and a new native run under the same SpecRunway execution, reusing verified receipts.
- **L14**: Archive preflight; intent; before/after backup; completion. ready_for_review does not archive. Validate the selected completion policy and accepted/merged code. Reconcile an uncertain archive before retrying.

## Verification

Each task in tasks.md has an observable check. Use real pinned OpenSpec/Specify tools for integration contracts, deterministic fake agents for repeatable failure injection, and a recorded real agent profile for final release acceptance. Keep command output and exit codes; do not mark unsupported or unavailable checks passed.

## Risks and trade-offs

Upstream behavior may differ from examples: stop dependent integration and record the measured adapter change. Local worktrees do not enforce hostile-process isolation. Side effects can complete without a receipt: reconcile actual Git/filesystem state before retrying. Parent and child work must share explicit budgets rather than multiply retries invisibly.

## Delivery and follow-up

Keep tests and operational documentation with the behavior they introduce. Update the implementation checkpoint and acceptance evidence. Development-change archive follows completion and applicable review; it is outside tracked implementation tasks. Product archive follows the separate completion policy.
