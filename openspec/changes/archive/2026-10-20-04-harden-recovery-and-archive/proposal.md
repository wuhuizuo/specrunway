# Proposal

## Why

Harden recovery and archive establishes the next verifiable slice of the standalone local coordinator. The central Store and cross-repository delivery requirements remain the project's core.

## What Changes

Implement source tasks L13, L14 in this change. Preserve the local-first scope and use Specify workflow at the pinned, measured contract. Specstride and v2 components are excluded.

## Capabilities

### New Capabilities

- `execution-recovery`: Resumes local execution through verified receipts and native runtime contracts while avoiding duplicate work after abnormal process exit.
- `change-completion`: Archives specifications only after the approved final cross-repository code state satisfies the selected explicit completion policy.

### Modified Capabilities

None. The prepared sequence introduces separate capability boundaries; inspect the actual target baseline before applying if it is not empty.

## Impact

Python CLI package, central configuration, documentation and disposable integration fixtures appropriate to this slice. Prerequisite: 03-deliver-two-repo-loop. Exit condition: Resume/recover and archive fault cases reconcile safely; partial merge and stale evidence block archive.
