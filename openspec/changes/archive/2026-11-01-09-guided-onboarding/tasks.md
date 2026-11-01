# Tasks

Prerequisite: archived v1 baseline (L01-L18). Source task IDs: L19. All implementation starts unchecked.

## 1. L19 Guided onboarding wizard

- [x] 1.1 [L19] Implement `specrunway wizard` for configuration and request drafting, including Git checkout discovery, atomic `local.yaml`/`request.md`/manifest writes, deterministic task mapping, and handoff to `init`/`plan`; verify fresh-control bootstrap, repeat request-only runs, overwrite refusal, and scripted prompts.

- [x] 1.2 [L19] Route default `plan` manifests to the repository ids and profiles declared in `local.yaml` instead of hardcoded fixture names; verify a two-repository plan without `--manifest` and a mismatch refusal.

- [x] 1.3 [L19] Document the wizard in README/RUNBOOK, verify CLI and JSON-envelope behavior in tests, and record commands and results in `docs/evidence/09-guided-onboarding.md`.
- [x] 1.4 [L19] Keep control configuration limited to stable wiring, select participating repositories and dependency edges at request time, and write change-scoped test profiles for monorepo paths; verify selected-subset, independent-repository, and monorepo-command behavior in wizard tests.
- [x] 1.5 [L19] Allow manifests without `integration_profile`, omit the integration round, and complete from per-repository verified evidence; verify manifest validation, workflow generation, and completion in integration tests.
- [x] 1.6 [L19] Default the Store outside an enclosing Git checkout and reject nested Store paths with a corrective hint; verify Git-control defaults, non-Git defaults, nested collection refusal, and existing-config refusal.

Acceptance linkage: V1-A02, V1-A03, V1-A14.

## Workflow follow-up

- Review the actual diff and evidence under the target repository policy.
- Archive this development change only after implementation and review conditions are met; inspect the resulting baseline.
- Update docs/HANDOFF_STATE.md with completed source IDs, actual checks, blockers, and the next task.
