# Design

## Context

Read `docs/DESIGN.md`, the archived `trusted-verification` baseline, and this
change's requirements. Commands must come from the trusted control
repository and never from agent output; freezes must bind them to the
execution.

## Goals and boundaries

Let a control checkout declare language- or layout-specific test commands
with a relative working directory, freeze the resolved profiles, and keep the
built-in Python `unit` profile working for existing executions and narrow
steps. Do not add a plugin registry, arbitrary shell evaluation, remote test
execution, or v2 services.

## Decisions

- **Configuration**: optional `test_profiles` in the machine-only control
  `local.yaml`: `{name: {command: [argv...], cwd?: "<relative path>",
  timeout_seconds?: int}}`. Names are slugs; `cwd` must be a safe relative
  path inside the worktree (no absolute paths, no `..`); defaults are the
  worktree root and 900 seconds.
- **Precedence**: configured profiles override the built-in registry by name;
  otherwise the built-in profile (currently `unit`) is used.
- **Freeze**: `hub run` resolves every profile referenced by the manifest at
  snapshot time and stores
  `snapshot.test_profiles = {name: {command, cwd, timeout_seconds,
  config_digest}}`. Unknown profiles refuse execution before any agent work;
  editing `local.yaml` afterwards does not change an existing execution.
- **Runtime**: a single resolver reads the frozen profile for a repository;
  legacy snapshots without the field fall back to the built-in registry. The
  runner executes argv with `cwd = worktree / profile.cwd`.
- **Consumers**: run-repo receipt tests, verify-round/repair-round,
  integration repair verification, the prompt's trusted command line, and the
  archive final-matrix check all use the frozen profile.

## Implementation slices

- **L18**: schema + validation; freeze; resolver; wire consumers; tests
  (cwd execution, frozen immutability, unknown profile, built-in fallback);
  examples/runbook.

## Verification

Use a disposable repository whose tests live in a subdirectory and a profile
with `cwd` set to that directory: the trusted receipt must be produced from
the subdirectory. After freezing, change the control command to a failing one
and prove verification still uses the frozen argv. Prove unknown profiles
refuse freeze, absolute/`..` cwd is rejected, and legacy snapshots still run
the built-in `unit` profile. Run the full suite and strict validation.

## Risks and trade-offs

A misconfigured profile fails loudly before agent work rather than silently
running the wrong tests. Freezing means profile fixes require a new
execution, which is intentional for auditability.
