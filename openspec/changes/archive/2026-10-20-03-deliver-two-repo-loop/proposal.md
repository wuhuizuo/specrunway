# Proposal

## Why

Deliver the two-repository loop establishes the next verifiable slice of the standalone local coordinator. The central Store and cross-repository delivery requirements remain the project's core.

## What Changes

Implement source tasks L06, L07, L08, L09, L10, L11, L12 in this change. Preserve the local-first scope and use Specify workflow at the pinned, measured contract. Specstride and v2 components are excluded.

## Capabilities

### New Capabilities

- `local-change-execution`: Carries a prepared central change through ordered repository implementation with separate worktrees and traceable accepted results.
- `context-approval`: Binds local plan and implementation decisions to the exact frozen content and code evidence reviewed by the operator.
- `trusted-verification`: Uses independently executed tests and bounded repair to decide whether the actual repository commit matrix satisfies a central change.

### Modified Capabilities

None. The prepared sequence introduces separate capability boundaries; inspect the actual target baseline before applying if it is not empty.

## Impact

Python CLI package, central configuration, documentation and disposable integration fixtures appropriate to this slice. Prerequisite: 02-build-local-foundation. Exit condition: A central change reaches ready_for_review through two repositories, local review gates, trusted tests, and bounded repair.
