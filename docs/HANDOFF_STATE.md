# Implementation state

Updated: 19 October 2026 (L01 session).

## Completed preparation

- Exported the full English design and task/acceptance material from revision 2.
- Recorded the confirmed local-first scope, central Store/cross-repository requirement, and exclusion of Specstride.
- Prepared five ordered OpenSpec changes with requirements, designs, and unchecked tasks.
- Provided repository development-tool setup and a next-agent implementation prompt.

## Completed work this session (L01)

- Imported the handoff package into this repository (README merged, `.gitignore` merged from fragment, AGENTS.md/openspec/scripts/tooling/docs in place), and generated the OpenSpec ↔ OpenCode integration with `openspec init --tools opencode` (`.opencode/` commands + skills).
- Installed the pinned development OpenSpec tool (`@fission-ai/openspec@1.14.3` via `tooling/openspec/package.json`; `package-lock.json` generated) and the pinned Specify runtime (`specify-cli 1.2.1` from `github/spec-kit@v1.2.1`, commit `9dca9bf42a031765ee5e5f2371137f2f26967e11`) into the repo-root `.venv`.
- Validated all five prepared changes (`openspec validate --all --strict --json`: 5/5 valid, exit 0) and confirmed the planning root resolves to this repository (`root.source: nearest`).
- Executed every L01 probe in a disposable control/Store/two-repo fixture under temp storage (unregistered the store afterwards; business fixture repos verified clean):
  - Store setup/registration + explicit root resolution (`root.source: "store"`), unknown-store error JSON (exit 1), invalid delta strict failure, planning-vs-apply progress distinction (`isPlanningComplete: true` while apply 0/2 → 1/2 after checkbox flip).
  - Custom `hub` step installed from a local package into the real Specify env; relative-import package loading verified; hub/v1 output envelope flowed through `steps.<id>.output.data.*` expressions.
  - Non-TTY gate → PAUSED → resume with verdicts completes; ordered fan-out (`repo-a`→`repo-b`, aliases `implement:repo:0/1`); fan-in aggregation; bounded do-while capped at `max_iterations: 3`; condition-driven stop before cap; loop aliases `integration:verify-round:1/2`.
  - Failed-step run + resume preserving completed work (early note executed once); graceful SIGINT → PAUSED with `workflow_interrupted` in `log.jsonl`, then resume completing from the persisted tree; SIGKILL abrupt exit → native state stays `running`, resume refused (exit 1), spawned children survived parent death (reaped manually via recorded PIDs; process group intact).
- Recorded the pass decision with real identities/digests in `toolchain.lock.json` and the full command/exit-code trail in `docs/evidence/L01/compatibility-report.md` + `docs/evidence/L01/fixtures/`.

## Not implemented

No production CLI, business schema, state store, agent launcher, Specify bridge, recovery implementation, or archive implementation has been written. L02-L15 remain open. Every product acceptance case other than the L01 compatibility gate remains Not run.

## Current change

`02-build-local-foundation` (source tasks L02-L05) — not started.

## Exact next action

Execute `openspec/changes/02-build-local-foundation/tasks.md`: create the single Python package with the `hub` CLI (doctor/plan/run/status/approve/resume/recover/archive argument skeleton), hub/v1 JSON schemas with machine-validation, the typed OpenSpec adapter (argv + explicit `--store`), and the JSON FileRunStore with atomic writes/locking; record L02 toolchain choice (ruff/pytest or similar) with reproducible dependencies. V1-A01 evidence must be consulted for adapter contracts rather than re-probed.

## Candidate versions

OpenSpec v1.14.3 and Spec Kit v1.2.1 are now measured, pinned, and locked (`toolchain.lock.json`); they are the tested runtime compatibility baseline for L01+.

## Pending checkpoints

- L01 compatibility: Passed (V1-A01 gate recorded; release replay still pending via V1-A14).
- Required v1 tasks completed: 1 / 15.
- Required v1 acceptance passed: 1 / 14 (V1-A01 compatibility scope).
- Live agent profile: Not selected or exercised.
- Start v2: Deferred.
