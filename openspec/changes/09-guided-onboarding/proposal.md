# Proposal

## Why

The v1 dogfood run exposed two onboarding costs that the one-command bootstrap
does not remove. A new user must still hand-write `local.yaml`, including
repository paths, remote identities, test profiles, and an integration profile,
before `specrunway init` can run. After bootstrap, the user must also author a
structured `request.md` by hand before `specrunway plan` can generate planning
artifacts. Both files encode machine wiring and change intent that the product
can collect or draft through a small guided flow.

## What Changes

Add source task L19: an interactive `specrunway wizard` that performs two
phases without adding a service or model dependency.

1. When the control checkout has no `local.yaml`, the wizard inspects existing
   Git checkouts, asks only for the missing wiring, writes the machine-only
   configuration, and runs the existing idempotent `init` flow.
2. When the control checkout is already configured, the wizard accepts a short
   natural-language change summary, asks a few bounded follow-up questions,
   maps task text to the configured repositories, composes `request.md` and a
   routing manifest, then invokes the existing `specrunway plan` path.

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

## Impact

New `specrunway/wizard.py`, a small bootstrap helper extraction, one CLI
subcommand, default-manifest routing changes in `planning.py`, tests, and
README/RUNBOOK updates. No schema version change, no new runtime dependency,
and no service or v2 component.
