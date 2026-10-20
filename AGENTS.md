# Agent instructions

## Goal and scope

Implement local v1 of the Central Store Coordinator. The defining use case is one central OpenSpec change spanning two or more existing Git repositories. Deliver a usable Python CLI before any team platform.

The confirmed stack is OpenSpec Store for authoritative specifications, our coordinator for cross-repository business rules, Specify workflow for runtime control flow, and one real coding-agent CLI for code execution. Specstride is excluded: add no dependency, adapter, prototype, or benchmark for it.

The product is **SpecRunway**: `specrunway` CLI, `specrunway` Python package, `specrunway/v1` data schema, `.specrunway/` control directory, and workflow step type `specrunway`. Decision D10 supersedes the earlier provisional-name rule; keep code, docs, and fixtures on the new names.

## Read before editing

Read `docs/DECISIONS.md`, `docs/DESIGN.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/ACCEPTANCE.md`, `docs/HANDOFF_STATE.md`, and the active OpenSpec change. Existing target-repository instructions and latest user instructions still apply. Resolve material contradictions in a recorded decision before dependent code; make routine implementation choices autonomously.

## Two different uses of tools

This repository's `openspec/` manages development of the coordinator. Runtime integration tests use separate disposable Store/control/code repositories. Keep their identities and paths distinct. Use Specify's custom workflow and one custom step bridge for the product; do not run the default Spec Kit planning flow to create competing normative documents.

Do not require the unimplemented coordinator to bootstrap its own development. L01 calls upstream tools directly. Initialize Specify only in the intended control/probe workspace, never automatically in business repositories.

## Implementation order

Follow the five OpenSpec changes in `docs/IMPLEMENTATION_PLAN.md`. Complete L01 compatibility evidence before building against upstream assumptions. Passing the compatibility gate permits the next change; it does not mark later acceptance cases passed. Implement required L01-L15 only. Keep optional local parallelism, Jenkins integration, and all v2 code deferred.

Every tracked task states its verification. Mark it complete only after execution or direct artifact inspection proves it. A plan, stub, mocked upstream response, or test command that has not run is not completion evidence. Keep code, tests, and operational documentation together in the change that introduces the behavior.

## Architectural invariants

- One Python package; one real agent profile; explicit sequential `repo_order`; one active execution per control/Store checkout. No HTTP service, database, broker, account system, Web UI, or generic scheduler in v1.
- OpenSpec is the sole specification source. Repo-specific execution views retain original task IDs and input digests. A single coordinator writer accepts results and updates task checkboxes.
- Stable Store/change/repo/task/execution IDs are business identities. A native Specify run ID is a runtime identity and may change during explicit recovery.
- Freeze plan/rules/profile bytes and base commit OIDs. Planning digests exclude only checkbox state, not task text or dependencies. Changed approved inputs invalidate approval.
- Preserve original checkouts through separate worktrees. Independently validate result identity, commit ancestry, allowed paths, and test evidence. A worktree is not a hostile-process security sandbox.
- Execute subprocesses with argv and explicit cwd; never evaluate agent output as shell. Tests are executed by the trusted runner rather than accepted from agent prose.
- Persist budgets, operation intents, and verified receipts across resume/recover. Do not edit private Specify state to force a running run into a resumable status.
- Keep local approval `self_asserted`. It does not become authenticated team authority.
- Finish normal execution at `ready_for_review`. Archive is explicit and subject to completion policy, final accepted code matrix, fresh evidence, and approval. Partial merge or an uncertain archive blocks publication.
- Preserve only RunStore, Executor, and ArtifactStore as narrow ports. Add no empty v2 implementations or provider registry scaffolding.

## Quality and evidence

Use deterministic fixtures and fake agents for failure injection, plus real OpenSpec/Specify integration tests at pinned versions. Before a v1 release, also demonstrate the supported real agent profile on two fixture repositories. Missing credentials may block that live case, but must not be reported as a pass.

Meaningful checks include invalid routing, approval drift, foreign/wrong-head results, original-checkout preservation, concurrent writers, interrupted state writes, bounded repair, normal native resume, orphan-running recovery, partial merge, and uncertain archive reconciliation. Do not create tests that merely repeat implementation details.

Record actual commands, versions, exit codes, findings, artifact refs, and test outcomes. Keep sensitive raw logs in ignored runtime locations and commit only sanitized evidence. Do not claim OpenSpec planning status proves implementation or acceptance.

Use English for repository documentation, specifications, commit/PR descriptions, and reports. Honor an established formatter, type checker, or test runner if the target repository has one. If none exists, choose a small Python toolchain and record it in L02 with reproducible dependencies.

## Checkpoints and boundaries

Continue required v1 work as prerequisites pass, without asking permission for ordinary edits and tests. Report blockers precisely and continue independent work. Stop dependent work when upstream contracts fail or an identity/scope conflict is unresolved. Keep v2 deferred.

Before ending a session, update the active tasks, acceptance evidence references, and `docs/HANDOFF_STATE.md`: completed work, commands/results, unresolved blockers, and the exact next task. Keep external publication and merges outside ordinary implementation completion.
