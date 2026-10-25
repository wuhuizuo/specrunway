# Change 09 evidence: guided onboarding wizard

Date: 25 October 2026. Environment: macOS, Python 3.14.5, Node 24.4.1,
npm 11.4.2, pytest 9.1.1, ruff 0.17.2, pinned OpenSpec 1.14.3,
specify-cli 1.2.1.

## Implemented (L19)

- `specrunway wizard` has two deterministic phases and no model dependency.
  - Configuration: discovers sibling Git checkouts, prompts for Store,
    repository ids/order, remote identities, per-repo test commands, one
    combined integration command, and the agent profile; validates with
    `validate_local_config`, writes `local.yaml` atomically, then calls the
    existing idempotent bootstrap.
  - Request: takes a short description plus why/what/context/acceptance and
    per-repository task text; assigns `T001...` in repository order; writes
    `requests/<change>.md` and `.specrunway/requests/<change>.manifest.yaml`;
    then calls the existing `plan` function. It never runs approval or work.
- Repeat runs reuse existing `local.yaml`; `--reconfigure` explicitly reopens
  configuration. Existing request/manifest files are only replaced after
  confirmation or `--force`.
- `--json` writes prompts to stderr and the final `specrunway/v1` envelope to
  stdout. `--skip-init`/`--skip-plan` support diagnostics and tests.
- Default `plan` manifests now derive repository ids, order, base refs,
  allowed paths, and test/integration profiles from `local.yaml` instead of
  hardcoded fixture names (`repo-a`/`repo-b`).
- The control bootstrap body moved from `cli.cmd_init` to
  `specrunway/bootstrap.initialize_control`, shared by `init` and the wizard.
- README and RUNBOOK document the wizard; DECISIONS records D11 and the
  implementation plan records L19.

## Verification

Commands and results:

- `.venv/bin/python -m pytest tests/test_wizard.py -q`
  → `10 passed in 15.83s`.
  Coverage includes scripted configuration discovery, atomic
  request/manifest generation, existing-config reuse, overwrite refusal,
  integration-profile refusal, configured default routing, non-Git rejection,
  JSON stderr/stdout separation, and a real pinned-OpenSpec plan generation
  from wizard output.
- Interactive CLI smoke on a disposable control directory with two Git
  checkouts (piped answers, real pinned tools):
  `.venv/bin/specrunway wizard --root <control>` → exit 0; `local.yaml`,
  `requests/add-smoke-feature-across-both-repos.md`, the routing manifest, and
  the OpenSpec change tree were created; the output printed the explicit
  `run`/`approve` next commands.
- `.venv/bin/python -m pytest -q`
  → `218 passed in 180.08s`.
- `.venv/bin/python -m ruff check src tests`
  → `All checks passed!`
- `tooling/openspec/node_modules/.bin/openspec validate --all --strict`
  → `11 passed, 0 failed`.
- `.venv/bin/python scripts/check_handoff.py`
  → passed with L01-L19 coverage.

## Boundaries and known limitations

- Drafting is template- and answer-based, not a coding-agent quality pass.
  The operator still reviews and edits the generated request before plan.
- Test and integration command suggestions are marker-based conveniences
  (`pytest`, Go, npm, Cargo, Make); every value is shown before writing.
- An existing `local.yaml` without any integration profile cannot be used for
  a new manifest; `--reconfigure` collects one.
- The wizard writes only inside the control checkout and the configured Store
  directory. Business checkouts are inspected with read-only Git commands.

Acceptance linkage: V1-A02 (standalone local use), V1-A03 (configuration and
explicit dependency order), V1-A14 (installation and human takeover).
