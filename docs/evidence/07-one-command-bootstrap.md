# Change 07 evidence: one-command bootstrap

## Implemented (L17)

- Step shim moved to `src/specrunway/step_package/` and shipped as package
  data (`pyproject.toml`), so a wheel install can install the step without a
  source checkout. `tooling/specrunwaystep` no longer exists as a separate
  copy.
- `specrunway init`:
  - requires and validates `local.yaml` (`local-yaml-missing` when absent);
  - resolves the pinned `openspec`/`specify` binaries;
  - creates the declared Store directory, registers the Store idempotently;
  - runs `specify init --here --force --non-interactive --ignore-agent-tools`
    only when `.specify` is absent, with the control checkout as cwd;
  - installs the bundled step unless `.specify/workflows/steps/specrunway`
    already exists;
  - runs `doctor` and exits 1 on findings errors, naming the failing tool or
    step install in the envelope.
- `archive` now calls the idempotent Store setup before applying deltas, so a
  Store registered after the run no longer blocks archive.
- README/RUNBOOK reduced the bootstrap to `local.yaml` + `specrunway init`;
  direct upstream commands are no longer user-facing.

## Verified

`tests/test_bootstrap.py` (3 tests, real pinned CLIs, disposable control):

1. `specrunway init` on a fresh control → exit 0;
   `specify_initialized: true`; `.specify/workflows/steps/specrunway/step.yml`
   exists; Store registered; doctor findings have no errors.
2. Running `init` again → exit 0, `specify_initialized: false`, no duplicate
   step install.
3. Control without `local.yaml` → exit 1, code `local-yaml-missing`.

`tests/test_archive.py::test_archive_registers_the_store_idempotently`:
unregisters the Store after the run, merges the accepted head, then archives
→ succeeds (`archived: true`, phase `archived`).

Packaging check:

```text
$ .venv/bin/python -m pip wheel --no-deps -w <tmp> .
$ python -c "import zipfile; print([n for n in zipfile.ZipFile(w).namelist() if 'step_package' in n])"
  → specrunway/step_package/__init__.py, specrunway/step_package/step.yml
$ <fresh venv>/bin/specrunway --version       # specrunway 0.1.0
$ <fresh venv>/bin/specrunway --help | grep init
```

Full suite: `pytest -q` → 198 passed. `ruff check src tests` → clean.
`openspec validate --all --strict` → valid. `scripts/check_handoff.py` →
L01-L17 coverage, all changes present.

Acceptance linkage: V1-A14 (installed-package bootstrap with no team
component).
