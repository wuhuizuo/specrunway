# Design

## Context

Read `docs/DESIGN.md`, `docs/RUNBOOK.md`, the archived `local-project`
baseline, and this change's requirements. `specrunway plan` already performs
an idempotent OpenSpec store setup; archive does not. The Specify control
workspace and step registration are currently manual, and the wheel omits
the step package.

## Goals and boundaries

Reduce bootstrap to `pip install` + `local.yaml` + `specrunway init`, keeping
all writes inside the control checkout. Upstream binaries remain
prerequisites; the user does not type their commands. Vendor no upstream
Python packages beyond the pinned CLI tools. `init` must never touch a
business repository or run inside one.

## Decisions

- **Packaging**: move the step shim to `src/specrunway/step_package/`
  (`step.yml` + `__init__.py`) and include it as package data, so an
  installed wheel can pass its path to `specify workflow step add --dev`.
  The dev repository uses the same path (no duplicate copy).
- **`specrunway init`**:
  1. require and validate `local.yaml` at the control root
     (`local-yaml-missing` otherwise);
  2. resolve pinned `openspec` and `specify` via the existing tool resolver;
  3. call the adapter's idempotent store setup;
  4. if `.specify` is absent, run `specify init --here --force
     --non-interactive --ignore-agent-tools` with an explicit control cwd;
  5. run `specify workflow step add specrunway --dev <bundled step path>`;
  6. run `doctor` and surface findings; exit 1 on errors.
  Existing `.specify` is never regenerated, and a second `init` is a no-op.
- **Archive**: call the idempotent store setup before `openspec archive`, so
  users never register the Store manually.
- **Errors**: stable envelope codes for missing/invalid local config,
  missing upstream binaries, failed init, and failed step install; the
  message names the exact tool and installation hint.

## Implementation slices

- **L17**: packaging move; `init` command; archive setup; tests (idempotent
  init, fresh control, bundled step presence, archive auto-registration);
  runbook/README updates.

## Verification

Use a disposable control checkout with `local.yaml` and the pinned CLIs:
run `init` twice, assert exit 0, `.specify` presence, the installed step
directory containing `step.yml`, and Store registration. Build a wheel and
assert `step_package/step.yml` is present and `init` appears in `--help`.
Re-run archive against a temporarily unregistered Store. Record commands and
exit codes; run the full suite and strict validation.

## Risks and trade-offs

`specify init` writes an agent-integration scaffold; it is restricted to the
control checkout and skipped when already present. Upstream CLI flags are
pinned by the measured L01 contract; an unsupported version fails `init`
with the tool name rather than silently diverging.
