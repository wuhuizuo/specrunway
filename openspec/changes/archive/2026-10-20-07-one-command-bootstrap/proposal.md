# Proposal

## Why

Daily operation already uses only `specrunway`, but first use still requires
three upstream commands (`openspec store setup`, `specify init`, `specify
workflow step add`), and the published wheel does not contain the step shim,
so an installed user has no path to `--dev`. That friction is unacceptable
for a local release and makes the documented dogfood flow error-prone.

## What Changes

Implement source task L17: add an idempotent `specrunway init` that
validates the control checkout, registers the Store, initializes the Specify
workspace only inside the control checkout, installs the bundled
`specrunway` step from package data, and reports diagnostics. Ship the step
shim inside the wheel. Make archive registration idempotent. Update the
runbook so the only hand-written artifact is `local.yaml`.

## Capabilities

### New Capabilities

None. This change improves the existing `local-project` capability.

### Modified Capabilities

- `local-project`: Adds one-command control-checkout bootstrap and bundled
  step installation without requiring direct upstream CLI calls.

## Impact

Package data (step shim in the wheel), a new CLI subcommand, archive Store
registration, tests, and runbook/README. No service or v2 component.
Prerequisite: the archived v1 baseline (L01-L16).
