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

- Store id defaults to `specrunway-store`; store path defaults to
  `<control>/openspec-store` and is resolved to an absolute path.
- Existing sibling Git checkouts are listed as discovery hints. The wizard
  accepts repository paths one at a time until an empty answer, resolves
  relative paths against the control root, rejects non-Git paths, derives the
  repository id from the directory name, and reads `remote.origin.url`.
- A missing origin is prompted explicitly; an invalid or remote-less checkout
  fails before writing.
- Test commands are collected per repository with a marker-based suggestion
  (`pytest`, `go test`, `npm test`, `cargo test`). A blank answer keeps the
  built-in `unit` fallback. Non-blank answers become `<repo>-unit` profiles.
- An integration command is collected once and becomes
  `specrunway-integration`, defaulting to the first repository's test command.
- The resulting mapping is validated with the existing `local.yaml` validator,
  written atomically, and then handed to the existing init flow. The wizard
  writes only inside the control checkout and the configured Store path.

### Request phase

- The change id defaults to a slug derived from the description and must pass
  the existing slug rule.
- The description supplies `Why` and `What Changes` defaults; the wizard asks
  bounded follow-up questions for context and acceptance, then asks for
  repository task text.
- Task ids are assigned deterministically in repository order (`T001`, ...).
  The wizard asks whether each later repository depends on the previous one so
  the manifest expresses only real ordering.
- Allowed paths and base ref are suggested from the checkout layout and current
  branch, then editable per repository.
- `request.md` is written under `<control>/requests/<change>.md`; the draft
  manifest is written under `.specrunway/requests/<change>.manifest.yaml`.
  Existing files are not overwritten without confirmation.
- The wizard calls `plan` with the generated request and manifest. It reports
  the change path and the next explicit commands; it does not execute them.

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

1. A bare control checkout receives a valid `local.yaml`, request, manifest,
   and planning invocation; the generated manifest uses declared repo ids.
2. A configured checkout skips configuration, preserves the existing file, and
   creates a second change request.
3. Blank task input, unknown repository paths, duplicate ids, and cancelled
   overwrite produce stable errors without partial artifacts.
4. `--json` keeps stdout parseable while prompts use stderr.
5. The full suite, `ruff`, strict OpenSpec validation, and
   `scripts/check_handoff.py` pass; record the commands and results under
   `docs/evidence/09-guided-onboarding.md`.

## Risks and trade-offs

The wizard is intentionally not a requirement-quality agent. It removes
structural friction and produces reviewable text; the operator still owns
intent, and the existing plan/approval gates remain authoritative. Suggested
commands may not match every repository; every suggestion is visible and
editable before the configuration is written.
