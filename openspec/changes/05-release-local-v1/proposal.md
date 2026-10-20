# Proposal

## Why

Release local v1 establishes the next verifiable slice of the standalone local coordinator. The central Store and cross-repository delivery requirements remain the project's core.

## What Changes

Implement source tasks L15 in this change. Preserve the local-first scope and use Specify workflow at the pinned, measured contract. Specstride and v2 components are excluded.

## Capabilities

### New Capabilities

- `local-release`: Demonstrates that an independently installed local distribution satisfies every required v1 acceptance case and supports human operation.

### Modified Capabilities

None. The prepared sequence introduces separate capability boundaries; inspect the actual target baseline before applying if it is not empty.

## Impact

Python CLI package, central configuration, documentation and disposable integration fixtures appropriate to this slice. Prerequisite: 04-harden-recovery-and-archive. Exit condition: The installed distribution passes all 14 required v1 cases, with live-agent and failure-replay evidence.
