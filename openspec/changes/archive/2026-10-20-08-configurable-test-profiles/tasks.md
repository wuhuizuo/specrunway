# Tasks

Prerequisite: archived baseline (L01-L17). Source task IDs: L18. All implementation starts unchecked.

## 1. L18 Configurable and frozen test profiles

- [x] 1.1 [L18] Implement control-declared test profiles with relative cwd and timeout, freeze referenced profiles into the snapshot, wire run-repo/verify/repair/integration-repair/prompt/archive to the frozen resolver, and keep the built-in fallback; verify subdirectory execution, frozen immutability, unsafe-profile refusal, unknown-profile refusal, and legacy fallback.

Acceptance linkage: V1-A03 V1-A06 V1-A07.

## Workflow follow-up

- Review the actual diff and evidence under the target repository policy.
- Archive this development change only after implementation and review conditions are met; inspect the resulting baseline.
- Update docs/HANDOFF_STATE.md with completed source IDs, actual checks, blockers, and the next task.
