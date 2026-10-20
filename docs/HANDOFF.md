# Next code agent launch prompt

Paste the following prompt into the code agent opened at the target repository root. The files in this package must be available in that repository first.

```text
Implement the standalone local v1 of the Central Store Coordinator in this repository.

Read all applicable AGENTS.md files, then docs/DECISIONS.md, docs/DESIGN.md,
docs/IMPLEMENTATION_PLAN.md, docs/ACCEPTANCE.md, and docs/HANDOFF_STATE.md.
Inspect the existing repository and preserve unrelated work and established tooling.

Confirmed requirements:
- Central OpenSpec Store and changes spanning multiple existing Git repositories are core.
- OpenSpec manages this repository's own implementation changes.
- The product uses Specify workflow with a thin custom step bridge and one real agent CLI.
- Specstride is excluded from the current implementation.
- Build required local v1 tasks L01-L15 only. v2 and optional enhancements stay deferred.
- Keep one authoritative specification set and preserve specrunway/v1 business contracts.
- Keep all repository documents and reports in English.

Start with openspec/changes/01-verify-upstream-contracts (L01). Follow docs/TOOLCHAIN.md.
Confirm the planning root, validate all prepared changes, and prove the real pinned
OpenSpec/Specify contracts in disposable fixtures. Record actual evidence before
building production code. Do not mark a generated plan, mock-only upstream response,
or unexecuted test as a pass. Bootstrap with upstream tools; do not require the
unimplemented coordinator to run itself.

After L01 passes, continue through changes 02, 03, 04, and 05 in order. The active
change's tasks.md is the live implementation checklist. Each task includes verification:
land the code, meaningful tests, and necessary documentation together, then check it off.
Use the OpenSpec apply instructions or equivalent CLI-driven workflow; do not regenerate
the supplied plans with a second Specify planning process.

Verify two-repo execution, approval drift, commit/test result validation, bounded repair,
normal resume, orphan-running recovery, partial merge, and uncertain archive behavior.
Preserve original checkouts, keep runtime data out of Git, and never force-edit private
Specify state. Test and record the installed distribution before claiming v1 release.

Make routine implementation decisions autonomously. Stop dependent work on material
contract/identity conflicts, but continue independent work and report precise blockers.
Do not implement team services, add empty v2 scaffolding, or publish/push/merge as a
side effect of green tests. Follow existing repository policy for local commits.

At each milestone and before the session ends, update tasks.md, acceptance evidence,
and docs/HANDOFF_STATE.md. Report changed files, actual commands/results, completed
task IDs, remaining blockers, and the exact next task. A v1 release requires all 14
required v1 acceptance cases, including the configured real-agent case; missing live
credentials must remain visible as a blocked case rather than a false pass.
```

## Agent handback format

```text
Active change:
Completed source task IDs and OpenSpec checkbox IDs:
Files changed and resulting behavior:
Commands run, exit codes, and evidence refs:
Acceptance passed / failed / blocked / not run:
Compatibility or design decisions recorded:
Remaining blockers:
Exact next task:
```

For a short first session, scope the same prompt to completing change 01 and its compatibility report. That is a milestone checkpoint, not completion of local v1.
