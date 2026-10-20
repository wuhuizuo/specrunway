# Design

## Context

Read `docs/DESIGN.md`, `docs/DECISIONS.md`, and the requirements in this change. This slice covers L06, L07, L08, L09, L10, L11, L12. Its prerequisite is 02-build-local-foundation; prepared planning files do not prove that prerequisite passed.

## Goals and boundaries

A central change reaches ready_for_review through two repositories, local review gates, trusted tests, and bounded repair.

Implement no optional or v2 behavior. Keep product business state and runtime engine state distinct. Bootstrap probes call upstream tools directly; application code uses the narrow ports and typed adapters in the full design.

## Decisions

Use exact, measured upstream versions; one Python package; explicit repo ordering; separate worktrees; frozen inputs; trusted test execution; and coordinator-owned task acceptance. Preserve existing `hub` and `hub/v1` contracts. Use the public Specify custom-step API rather than private state or engine patches.

For the initial probes, prove custom-step import visibility inside the actual Specify Python environment. For later implementation, result evidence must bind repo/task/execution IDs, input digests and actual commits. Native running recovery creates a new native run only after reconciliation and confirmed process termination.

## Implementation slices

- **L06**: hub plan; artifact generation and validation. A request produces complete OpenSpec planning artifacts and explicit repo/task routing. Manually prepared plans are also accepted.
- **L07**: Snapshots; planning/result digests; self_asserted approvals. Bind approval to content. Text or rule changes invalidate it; checkbox-only changes preserve the planning digest. Do not claim team authentication.
- **L08**: argv/cwd/prompt-file launcher; process groups; structured result. Support the first CLI actually used. Apply existing repository instructions. Never interpolate agent output into a shell command.
- **L09**: Separate worktrees; test profiles; result validation. Preserve original checkouts. Runner tests bind evidence to commits. Reject invalid results, unexpected paths, and unverified success claims.
- **L10**: type: hub bridge; standardized output.data. One step package delegates to functions in the same package. Do not mutate private SDK context or build another workflow engine.
- **L11**: Prepare; gates; fan-out with max=1; fan-in; review. Run repositories in explicit order. Reject invalid dependency order before execution. The workflow runs without any v2 component.
- **L12**: Per-repo attempts; integration rounds; persisted budgets. Allow initial work plus at most two repairs. Test failures enter repair; exhausted budgets stop. Resume preserves counters and no-progress detection.

## Verification

Each task in tasks.md has an observable check. Use real pinned OpenSpec/Specify tools for integration contracts, deterministic fake agents for repeatable failure injection, and a recorded real agent profile for final release acceptance. Keep command output and exit codes; do not mark unsupported or unavailable checks passed.

## Risks and trade-offs

Upstream behavior may differ from examples: stop dependent integration and record the measured adapter change. Local worktrees do not enforce hostile-process isolation. Side effects can complete without a receipt: reconcile actual Git/filesystem state before retrying. Parent and child work must share explicit budgets rather than multiply retries invisibly.

## Delivery and follow-up

Keep tests and operational documentation with the behavior they introduce. Update the implementation checkpoint and acceptance evidence. Development-change archive follows completion and applicable review; it is outside tracked implementation tasks. Product archive follows the separate completion policy.
