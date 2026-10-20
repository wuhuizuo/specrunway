# Tasks

Prerequisite: 01-verify-upstream-contracts. Source task IDs: L02, L03, L04, L05. All implementation starts unchecked.

## 1. L02 Create the single-package CLI and central layout

- [x] 1.1 [L02] Build the single-package CLI and central layout; verify diagnostic entry points work from a fresh installation and business checkouts need no tool init.

Acceptance linkage: V1-A02.

## 2. L03 Validate the manifest and machine repo mappings

- [x] 2.1 [L03] Implement machine-checkable manifest/snapshot/result/approval/receipt schemas and repo mappings; verify malformed IDs, traversal, unknown profiles and incomplete task routing fail.
- [x] 2.2 [L03] Validate explicit repo order and remote identity; verify forward dependencies, cycles and wrong checkouts fail before any agent invocation.

Acceptance linkage: V1-A03.

## 3. L04 Build the typed OpenSpec adapter

- [x] 3.1 [L04] Implement typed argv OpenSpec calls with explicit Store selection; verify real JSON fixtures, error handling and planning-versus-implementation completion.

Acceptance linkage: V1-A01 V1-A04.

## 4. L05 Implement JSON state and local exclusion

- [x] 4.1 [L05] Implement atomic file state, revisions, active ownership and operation intents; verify competing writers, interrupted writes and effect-before-receipt reconciliation.

Acceptance linkage: V1-A08.

## Workflow follow-up

- Review the actual diff and evidence under the target repository policy.
- Archive this development change only after implementation and review conditions are met; inspect the resulting baseline.
- Update docs/HANDOFF_STATE.md with completed source IDs, actual checks, blockers, and the next task.
