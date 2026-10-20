# Proposal

## Why

The v1 release satisfies repository-level trusted verification, but the
`trusted-verification` baseline also requires executing the configured
integration profile against the accepted commit matrix and persisting
integration repair counters. Today `integration_profile` is only a manifest
name recorded for traceability, so a change whose per-repository tests pass
but whose combined acceptance check fails can still reach `ready_for_review`.
That is a real gap against the archived baseline and V1-A07/V1-A09.

## What Changes

Implement source task L16 in this change: resolve an executable integration
profile from the trusted control checkout, freeze its argv in the execution
snapshot, run it against the accepted commit matrix during global
verification, block completion on failure, and drive bounded integration
repair rounds with persistent counters. Keep v1 scope: no parallel execution,
no CI service, no v2 component.

## Capabilities

### New Capabilities

None. This change closes gaps in the existing `trusted-verification`
capability.

### Modified Capabilities

- `trusted-verification`: Adds executable integration-profile resolution,
  combined-matrix execution, and persisted integration repair counters.

## Impact

Control configuration (`local.yaml`), execution snapshot, the `specrunway`
workflow step set, run state, and the completion guard. Disposable fixtures
gain one deterministic integration command. Prerequisite: the archived v1
baseline (L01-L15). Exit condition: a failing combined check blocks
`ready_for_review` and exhausts/repairs within persisted budgets, verified by
tests and recorded commands.
