# Design

## Context

The archived v1 baseline already owns configuration validation, OpenSpec
planning, and control bootstrap. `specrunway init` requires a valid
`local.yaml`, and `specrunway plan` accepts either a complete manual plan or a
`request.md` plus optional routing manifest. The dogfood run showed that these
inputs, not the execution engine, are the first-use barrier.

This change is developer tooling for the control layer. It must not write to a
business checkout, infer an approval, or make planning success look like
implementation completion.

## Goals and boundaries

- Reduce first use to `pip install`, `specrunway wizard`, and a few answers.
- Keep every artifact deterministic, inspectable, and editable.
- Reuse `local.yaml` validation, `init`, and `plan`; do not duplicate their
  business rules.
- Support repeat use: a configured control checkout enters the request phase
  directly; `--reconfigure` explicitly re-opens the configuration phase.
- Do not call a coding agent while drafting a request. The configured agent is
  reserved for implementation after approval.
- Never invoke `run`, `approve`, `resume`, `recover`, or `archive` from the
  wizard.

## Decisions

### Command surface

Add one command, `specrunway wizard`. Options:

- `--root` (explicit control checkout), `--reconfigure`, `--json`;
- `--change`, `--description`, `--request`, `--manifest` for scripted or
  repeat runs;
- `--skip-init`, `--skip-plan` for diagnostics and tests.

Interactive prompts go to the selected output stream. In `--json` mode prompts
go to stderr and the final `specrunway/v1` envelope goes to stdout, so callers
can parse the result without losing the interview.

### Configuration phase

Triggered only when `local.yaml` is absent or `--reconfigure` is present.

- Store id defaults to `specrunway-store`. For a control checkout outside Git,
  the Store default is `<control>/openspec-store`. OpenSpec refuses to create a
  Store inside another Git checkout, so when the control directory is a
  checkout (or sits inside one) the default becomes a sibling of the enclosing
  checkout (`<enclosing>-specrunway-store`). An explicit nested path is rejected
  before writing configuration or invoking Store setup, with the suggested
  external path in the error.
- Existing sibling Git checkouts are listed as discovery hints. The wizard
  accepts repository paths one at a time until an empty answer, resolves
  relative paths against the control root, rejects non-Git paths, derives the
  repository id from the directory name, and reads `remote.origin.url`.
- A missing origin is prompted explicitly; an invalid or remote-less checkout
  fails before writing.
- Control configuration stays limited to stable wiring. Test commands,
  dependency relations, and integration checks are deliberately not collected
  here: monorepos may need module-specific commands, and unrelated repositories
  may participate in one central change without forming an integration graph.
- The resulting mapping is validated with the existing `local.yaml` validator,
  written atomically, and then handed to the existing init flow. The wizard
  writes only inside the control checkout and the configured Store path.

### Request phase

- The change id defaults to a slug derived from the description and must pass
  the existing slug rule.
- The description supplies `Why` and `What Changes` defaults; the wizard asks
  bounded follow-up questions for context and acceptance.
- The wizard asks which configured repositories participate in this change and
  in what execution order. Task ids are assigned deterministically in that
  order (`T001`, ...), so unrelated repositories need not be included.
- Dependencies are explicit and may name any earlier participating repository;
  a blank answer means the repository is independent. The wizard never assumes
  that consecutive repositories depend on each other.
- Allowed paths and base ref are suggested from the checkout layout and current
  branch, then editable per repository.
- Test commands are asked per participating repository for this change only and
  written as `<change>-<repo>` profiles in `local.yaml`. The suggestion is
  marker-based (`pytest`, `go test`, `npm test`, `cargo test`), but a monorepo
  path can be typed. The profile bytes are frozen at run start as usual.
- The wizard asks whether the change has a combined integration check. If yes,
  it collects argv and a working repository and writes
  `<change>-integration`. If no, the manifest omits `integration_profile`.
- `request.md` is written under `<control>/requests/<change>.md`; the draft
  manifest is written under `.specrunway/requests/<change>.manifest.yaml`.
  Existing files are not overwritten without confirmation.
- The wizard calls `plan` with the generated request and manifest. It reports
  the change path and the next explicit commands; it does not execute them.

### Optional integration

A change whose repositories are independent has no honest combined command.
The manifest therefore treats `integration_profile` as optional. When present,
the existing resolve/freeze/integration-round/gate behavior is unchanged. When
absent, the run freezes no integration row, the generated workflow omits the
integration round, and completion checks only per-repository accepted results
and trusted verification. No placeholder command or synthetic receipt is
created.

### Default manifest routing

`plan` without `--manifest` currently synthesizes `repo-a`/`repo-b`, which are
fixture names. Change it to use the repository ids, order, base refs, and
declared test/integration profiles from `local.yaml`, while retaining the
fixture-compatible split when the fixture declares those same ids. This makes
`specrunway plan --request request.md` usable in a real control checkout.

## Implementation slices

- **L19**: bootstrap helper extraction, `wizard.py`, CLI command, default
  manifest routing fix, tests, and operator documentation.

## Verification

Use disposable Git checkouts and a scripted prompt stream. Verify:

1. A bare control checkout receives a valid `local.yaml` containing only stable
   wiring, plus a request, manifest, and planning invocation.
2. A configured checkout skips configuration, preserves the existing file, and
   creates a second change request.
3. Repository selection, order, and dependencies are change-scoped; a selected
   subset and an independent repository are both representable.
4. Per-change test profiles are written only for participating repositories;
   an omitted integration check produces a manifest without
   `integration_profile`, a workflow without `integration-round`, and a
   completion that still requires per-repository verification.
5. Blank task input, unknown repository paths, duplicate ids, invalid
   selections, a Store nested inside a Git checkout, and cancelled overwrite
   produce stable errors without partial artifacts.
6. `--json` keeps stdout parseable while prompts use stderr.
7. The full suite, `ruff`, strict OpenSpec validation, and
   `scripts/check_handoff.py` pass; record the commands and results under
   `docs/evidence/09-guided-onboarding.md`.

## Risks and trade-offs

The wizard is intentionally not a requirement-quality agent. It removes
structural friction and produces reviewable text; the operator still owns
intent, and the existing plan/approval gates remain authoritative. Suggested
test commands may not match every repository or monorepo path; every value is
visible and editable before the manifest is frozen. Omitting integration is an
explicit choice, not a claim that a combined check ran.
