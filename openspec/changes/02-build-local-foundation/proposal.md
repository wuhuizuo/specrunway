# Proposal

## Why

Build the local foundation establishes the next verifiable slice of the standalone local coordinator. The central Store and cross-repository delivery requirements remain the project's core.

## What Changes

Implement source tasks L02, L03, L04, L05 in this change. Preserve the local-first scope and use Specify workflow at the pinned, measured contract. Specstride and v2 components are excluded.

## Capabilities

### New Capabilities

- `local-project`: Provides one locally installed command package and central configuration while preserving existing business repositories.
- `change-routing`: Maps a central change to stable repository and task identities with an explicit executable order and verifiable repository bindings.
- `local-state`: Keeps local execution state readable and external operations traceable despite concurrent commands or interrupted file writes.

### Modified Capabilities

None. The prepared sequence introduces separate capability boundaries; inspect the actual target baseline before applying if it is not empty.

## Impact

Python CLI package, central configuration, documentation and disposable integration fixtures appropriate to this slice. Prerequisite: 01-verify-upstream-contracts. Exit condition: The CLI, schemas, explicit Store adapter, and local state/locking work in disposable fixture repositories.
