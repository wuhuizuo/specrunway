# Proposal

## Why

The v1 dogfood run exposed onboarding costs that the one-command bootstrap
does not remove. A new user must still hand-write `local.yaml`, including
repository paths and remote identities, before `specrunway init` can run. After
bootstrap, the user must author a structured `request.md` by hand. The dogfood
run also showed that test commands, repository dependencies, and integration
checks are change-specific: a target may be a monorepo, and repositories in one
central change are not necessarily integrated with each other. Collecting them
during control setup either guesses wrong or blocks the user before the change
scope is known.

## What Changes

Add source task L19: an interactive `specrunway wizard` that performs two
phases without adding a service or model dependency.

1. When the control checkout has no `local.yaml`, the wizard inspects existing
   Git checkouts, asks only for stable wiring (Store, repository paths/ids,
   remote identities, agent profile), writes the machine-only configuration,
   and runs the existing idempotent `init` flow.
2. When the control checkout is already configured, the wizard accepts a short
   natural-language change summary, asks which repositories participate and in
   what order, collects per-repository tasks and dependencies, adds
   change-scoped test profiles, optionally adds one integration profile,
   composes `request.md` and a routing manifest, then invokes the existing
   `specrunway plan` path.

A manifest may omit `integration_profile` when the change has no combined
check. The workflow then omits the integration round and completion depends on
per-repository trusted verification instead of inventing a combined receipt.

The wizard is deterministic and testable: it uses templates and Git inspection,
not a coding agent, for requirement drafting. It never runs implementation,
approval, or archive; those remain explicit commands.

Also fix the default manifest generation in `specrunway plan`: when no
`--manifest` is supplied it must route tasks to the repositories configured in
`local.yaml`, not to hardcoded `repo-a`/`repo-b` names.

## Capabilities

- `guided-onboarding`: Adds a resumable interactive wizard for control
  configuration and change-request drafting, with deterministic artifacts and
  explicit handoff to the existing plan command.
- `trusted-verification`: Makes the integration profile optional when a change
  has no combined acceptance check while preserving the existing gated
  behavior whenever one is configured.

## Impact

New `specrunway/wizard.py`, a small bootstrap helper extraction, one CLI
subcommand, default-manifest routing changes in `planning.py`, optional
integration handling in manifest validation, runner, workflow generation, and
completion, tests, and README/RUNBOOK updates. No schema version change, no new
runtime dependency, and no service or v2 component.
