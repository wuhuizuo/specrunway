# Toolchain compatibility and developer environment

## Developer environment (mise)

`mise.toml` is the current developer entry point. It pins the interpreter
versions recorded by the L01 gate (Python 3.14.5 and Node 24.4.1, whose npm is
11.4.2) and creates/activates the project `.venv`. It does not resolve Python
or Node packages; `pip` and `npm` do that inside the project.

```bash
mise trust
mise install
eval "$(mise activate zsh)"   # once per shell; add to ~/.zshrc
mise run bootstrap            # .venv + editable package + Specify + OpenSpec npm deps
mise run versions
mise run check
```

Without activation, use `mise exec -- <command>` so `node`, `npm`, and
`python` resolve to the pinned versions instead of the system PATH.

The venv remains deliberate. mise installs interpreters under its shared
version store (`~/.local/share/mise/installs/python/3.14.5`); installing the
editable package or `specify-cli` into that interpreter would share
site-packages across every project using the same version. The project venv
keeps those packages local and reproducible without changing the selected
interpreter.

`mise.toml` is developer tooling, not a runtime dependency of the product.
Package users still install the wheel and the pinned upstream CLIs as described
in `docs/RUNBOOK.md`.

## Toolchain lock and this document

`toolchain.lock.json` is the machine-readable result of the L01 compatibility
gate. It records the observed OS/architecture, interpreter versions, the exact
OpenSpec npm package and integrity, the Specify git tag and commit, step
package digests, probe workflow digests, and the gate decision. It is not a
package lock, and no code reads it at runtime.

This document remains the human-readable compatibility record: why those
versions were selected, which upstream contracts were probed, what the probes
proved, and what to re-check before changing a pinned version. Keep it when
updating setup instructions; do not turn it into a second package lock or a
duplicate runbook.

## Observed release candidates

On 19 October 2026, the official repositories advertised OpenSpec v1.14.3 and Spec Kit v1.2.1 as published, non-prerelease releases. OpenSpec v1.14.3 requires Node >=20.19.0. Specify is the CLI supplied by the `specify-cli` Python distribution.

These candidates must pass L01. Do not replace them with a moving `main` or `latest` reference silently. Record an explained version change if the candidate fails a required contract.

## Repository development OpenSpec

`tooling/openspec/package.json` pins OpenSpec exactly and keeps Node development tooling separate from the Python application package.

```bash
npm ci --prefix tooling/openspec
bash scripts/openspec.sh --version
bash scripts/openspec.sh init --tools codex
bash scripts/openspec.sh validate --all --strict --json
```

Commit the generated `tooling/openspec/package-lock.json` after reviewing it. Merge ignore rules and generated agent integration files with existing project policy. Preserve the supplied `openspec/config.yaml`. Never use `--force` as an automatic conflict-resolution step.

Before running change commands, confirm the resolved planning root is the intended repository. Runtime Store probes use a different disposable directory and explicit Store selection.

## Specify runtime probe

Use one isolated Python environment for the pinned Specify distribution and local probe code, so a copied custom step can import its core package. Installing the coordinator into an unrelated environment is not sufficient. Record interpreter and package paths without secrets.

For the repository environment:

```bash
mise install
mise run bootstrap
.venv/bin/specify version
.venv/bin/specify workflow --help
```

Run initialization and custom-step probes in a disposable control workspace, not in a business repository. Verify `specify workflow step add specrunway --dev <package-directory>` against that release's help. Its package root must contain `step.yml` and `__init__.py`; the implementation must import the supported StepBase/StepResult types and delegate through public contracts.

Use `specify version` rather than assuming the CLI supports `--version`. Check JSON flags in help before using them.

## Planning status is not implementation status

During handoff validation, OpenSpec 1.14.3 returned `isPlanningComplete: true` and `isComplete: true` for change 01 while `instructions apply` reported zero of five implementation tasks complete. The status response described planning artifacts. Read apply progress and actual acceptance evidence before claiming implementation completion.

The handoff bootstrap commands were exercised in a disposable copy. `init --tools codex` generated Codex skills under `.agents/skills/` and preserved the supplied AGENTS.md and OpenSpec configuration in that copy. Recheck existing target-repository integrations before merging generated files.

## L01 report and lock

Deliver `docs/evidence/L01/compatibility-report.md`, `toolchain.lock.json`, and sanitized fixtures. The lock must contain actual installed versions, upstream tag/commit or distribution identity, Python/Node versions, workflow/step/profile digests, and supported OS. Do not prefill a successful check from this handoff. When an interpreter or upstream version changes, record the reason and re-run the compatibility gate instead of silently editing the lock.

Test explicit OpenSpec Store creation/registration and root resolution; status/instructions/validate JSON; planning-versus-implementation completion; a harmless custom step with its real installed imports; non-TTY gates; fan-out ordering; loop aliases and outputs; paused/failed resume; and abrupt exit leaving a native running run. Record exit codes and confirm child-process termination before recovery experiments.

Keep production initialization and temporary experiment installation separate. No credential or paid model call is needed for the initial control-flow probes: a deterministic stub step can prove those contracts. Live agent acceptance is a later, explicitly recorded release case.

## References

- OpenSpec release: https://github.com/Fission-AI/OpenSpec/releases/tag/v1.14.3
- OpenSpec CLI at that tag: https://github.com/Fission-AI/OpenSpec/blob/v1.14.3/docs/cli.md
- OpenSpec schema at that tag: https://github.com/Fission-AI/OpenSpec/blob/v1.14.3/schemas/spec-driven/schema.yaml
- Spec Kit release: https://github.com/github/spec-kit/releases/tag/v1.2.1
- Specify workflow reference at that tag: https://github.com/github/spec-kit/blob/v1.2.1/docs/reference/workflows.md
