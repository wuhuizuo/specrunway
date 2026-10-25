# Change 09 evidence: guided onboarding wizard

Date: 25 October 2026. Environment: macOS, Python 3.14.5, Node 24.4.1,
npm 11.4.2, pytest 9.1.1, ruff 0.17.2, pinned OpenSpec 1.14.3,
specify-cli 1.2.1.

## Implemented (L19)

- `specrunway wizard` has two deterministic phases and no model dependency.
  - Configuration: discovers sibling Git checkouts and collects only stable
    wiring (Store, repository ids/paths, remote identities, agent profile);
    validates with `validate_local_config`, writes `local.yaml` atomically, then
    calls the existing idempotent bootstrap.
  - Request: takes a short description, participating repositories, execution
    order, per-repository tasks/dependencies/base refs/allowed paths, and a
    change-scoped test command (monorepo path allowed). It optionally records a
    combined integration check, writes `requests/<change>.md` and
    `.specrunway/requests/<change>.manifest.yaml`, then calls `plan`. It never
    runs approval or work.
- Independent repositories are representable: a blank dependency answer writes
  no edge, and no consecutive-repository dependency is assumed.
- A manifest may omit `integration_profile` when no combined check exists. The
  runner then freezes no integration row, the generated workflow omits
  `integration-round`, and completion still requires accepted results plus
  trusted verification for every repository. No placeholder command or
  synthetic receipt is created.
- Repeat runs reuse existing `local.yaml`; `--reconfigure` explicitly reopens
  configuration. Existing request/manifest files are only replaced after
  confirmation or `--force`.
- `--json` writes prompts to stderr and the final `specrunway/v1` envelope to
  stdout. `--skip-init`/`--skip-plan` support diagnostics and tests.
- Default `plan` manifests now derive repository ids, order, base refs, allowed
  paths, and optional integration from `local.yaml` instead of hardcoded
  fixture names (`repo-a`/`repo-b`).
- The control bootstrap body moved from `cli.cmd_init` to
  `specrunway/bootstrap.initialize_control`, shared by `init` and the wizard.
- README and RUNBOOK document the wizard; DECISIONS records D11/D13 and the
  implementation plan records L19.

## Verification

Commands and results:

- `.venv/bin/python -m pytest tests/test_wizard.py -q`
  → `17 passed in 11.71s`.
  Coverage includes stable wiring-only configuration, selected repositories and
  execution order, independent dependencies, change-scoped test profiles,
  optional integration profiles, Store-path defaults outside an enclosing Git
  checkout, nested-Store refusal, atomic request/manifest generation,
  existing-config reuse, overwrite refusal, configured default routing,
  non-Git rejection, JSON stderr/stdout separation, and a real pinned-OpenSpec
  plan generation from wizard output.
- `.venv/bin/python -m pytest tests/test_integration.py -q`
  → `8 passed in 6.18s` (including completion without an integration profile
  and workflow omission of `integration-round`).
- Interactive CLI smoke on a disposable control directory with two Git
  checkouts (piped answers, real pinned tools):
  `.venv/bin/specrunway wizard --root <control>` → exit 0; `local.yaml`,
  `requests/add-smoke-feature-across-both-repos.md`, the routing manifest, and
  the OpenSpec change tree were created; the output printed the explicit
  `run`/`approve` next commands.
- `.venv/bin/python -m pytest -q`
  → `226 passed in 187.37s`.
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
- A combined integration check is optional. Omitting it is explicit and does
  not claim that repositories work together; only per-repository trusted
  verification is recorded.
- The wizard writes only inside the control checkout and the configured Store
  directory. Business checkouts are inspected with read-only Git commands.

Acceptance linkage: V1-A02 (standalone local use), V1-A03 (configuration and
explicit dependency order), V1-A14 (installation and human takeover).
