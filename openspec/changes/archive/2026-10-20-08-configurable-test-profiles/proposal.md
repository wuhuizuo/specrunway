# Proposal

## Why

The trusted test runner only knows a built-in Python `unit` profile. Real
repositories in other languages or monorepo layouts (for example a Go service
in a subdirectory, or Helm/kustomize manifests validated by a shell script)
cannot be dogfooded: there is no trusted way to declare the test argv or the
subdirectory it must run in, and the manifest's `test_profile` name has no
control-side definition.

## What Changes

Implement source task L18: allow trusted control configuration to declare
named test profiles (argv, optional relative cwd, timeout), validate them,
freeze every referenced profile into the execution snapshot with a digest,
and make the bridge, verification, prompt, and archive use the frozen
profile instead of the built-in registry alone. The built-in `unit` profile
remains the default fallback.

## Capabilities

### New Capabilities

None. This closes an expressiveness gap in `trusted-verification`.

### Modified Capabilities

- `trusted-verification`: Adds control-declared, snapshot-frozen test
  profiles with a relative working directory.

## Impact

`local.yaml` schema, snapshot schema, test runner, bridge actions, prompt,
archive preflight, tests, examples, and runbook. No service or v2 component.
Prerequisite: the archived baseline (L01-L17).
