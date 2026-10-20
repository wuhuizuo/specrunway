# Tasks

Prerequisite: archived v1 baseline (L01-L16). Source task IDs: L17. All implementation starts unchecked.

## 1. L17 One-command bootstrap and bundled step

- [x] 1.1 [L17] Implement `specrunway init` (config validation, Store setup, Specify init inside the control checkout, bundled step installation, diagnostics), ship the step shim in the wheel, and register the Store before archive; verify idempotent init, wheel step presence, missing-config refusal, and archive registration.

Acceptance linkage: V1-A14.

## Workflow follow-up

- Review the actual diff and evidence under the target repository policy.
- Archive this development change only after implementation and review conditions are met; inspect the resulting baseline.
- Update docs/HANDOFF_STATE.md with completed source IDs, actual checks, blockers, and the next task.
