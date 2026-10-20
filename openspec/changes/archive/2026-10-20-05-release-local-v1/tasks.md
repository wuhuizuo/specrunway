# Tasks

Prerequisite: 04-harden-recovery-and-archive. Source task IDs: L15. All implementation starts unchecked.

## 1. L15 Replay, package, and hand over v1

- [x] 1.1 [L15] Package and install the distribution in a fresh directory; verify every required V1-A01 through V1-A14 case and retain real upstream/agent identities.
- [x] 1.2 [L15] Replay normal, repair and abnormal recovery paths plus backup/restore and cleanup; verify the runbook works without any v2 component.
- [x] 1.3 [L15] Review the release evidence matrix and known limitations; verify missing or failed cases remain visible and no optional/v2 feature becomes a release dependency.

Acceptance linkage: V1-A01 through V1-A14.

## Workflow follow-up

- Review the actual diff and evidence under the target repository policy.
- Archive this development change only after implementation and review conditions are met; inspect the resulting baseline.
- Update docs/HANDOFF_STATE.md with completed source IDs, actual checks, blockers, and the next task.
