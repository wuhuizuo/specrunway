# Toolchain compatibility and developer environment

## Installed-user tools (uv)

The supported end-user path uses three isolated tools and requires no Python
interpreter or activated virtual environment:

```bash
uv tool install "specrunway @ git+https://github.com/wuhuizuo/specrunway.git"
uv tool install "specify-cli @ git+https://github.com/github/spec-kit.git@v1.2.1"
npm install --global @fission-ai/openspec@1.15.0
uv tool update-shell          # once, if ~/.local/bin is not on PATH
```

`uv` provisions a private managed Python for the `specrunway` and `specify`
tool environments; use `uv tool install .` or a local wheel for a checkout.
OpenSpec remains a Node package and requires Node >= 20.19.0. Expected
versions: OpenSpec 1.15.0 (the current Store-capable release), specify-cli
1.2.1, specrunway 0.1.0, and Python >= 3.11 for the package itself. The L01
lock records the developer-verified set (Python 3.14.5, Node 24.4.1) rather
than the minimum supported runtime.

## Coding agent (opencode 2.1.4)

The shipped `primary-coding-agent` profile runs the real CLI as:

```text
opencode run --auto "<fixed message>" --file <prompt_file>
```

- opencode 2.x removed the `--pure` flag that 1.18.33 accepted; the profile no
  longer passes it. `--file` attaches the prompt file and must come after the
  fixed message.
- The profile intentionally does not pass `--model`. opencode uses its own
  configured default model; the re-verification probe used
  `deepseek/deepseek-flash` because the free default endpoint was unavailable
  during the run.
- The supported minimum is opencode 2.1.4. Older 1.18.33 installations still
  understand the argv shape except for the removed `--pure`, so the previous
  release evidence remains reproducible with that version.

## Runtime tool resolution order

`specrunway` does not read `toolchain.lock.json` at runtime. Each upstream CLI
is resolved by `resolve_tool_bin(control_root, explicit, name)` in this order:

1. An explicit path supplied by the caller (current CLI commands pass none).
2. `<control>/tooling/openspec/node_modules/.bin/<name>`.
3. `<specrunway-package-checkout>/tooling/openspec/node_modules/.bin/<name>`.
4. `<control>/.venv/bin/<name>`.
5. `<specrunway-package-checkout>/.venv/bin/<name>`.
6. `PATH` via `shutil.which`, where uv tool shims and global npm installs
   appear.

Here `<name>` is `openspec` or `specify`. The checkout hints make a source
checkout prefer its pinned local tools; an installed wheel normally resolves
both from PATH. A wrong version therefore usually means an earlier `.venv` or
`tooling/` hint is shadowing the intended binary. `specrunway doctor` checks
control wiring only; missing executables surface from the command that launches
them (for example `tool-missing` for OpenSpec) and name the failed executable.

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

On 25 October 2026 the pinned candidates were raised to OpenSpec v1.15.0 and
opencode 2.1.4 after re-verification (see `docs/evidence/11-toolchain-upgrade.md`).
The 1.14.3 L01 probe report remains the historical compatibility record for the
original gate; the current pin and its re-verification are recorded in
`toolchain.lock.json`.

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

During the 1.14.3 handoff validation, OpenSpec 1.14.3 returned `isPlanningComplete: true` and `isComplete: true` for change 01 while `instructions apply` reported zero of five implementation tasks complete. The status response described planning artifacts. Read apply progress and actual acceptance evidence before claiming implementation completion.

The handoff bootstrap commands were exercised in a disposable copy. `init --tools codex` generated Codex skills under `.agents/skills/` and preserved the supplied AGENTS.md and OpenSpec configuration in that copy. Recheck existing target-repository integrations before merging generated files.

## L01 report and lock

Deliver `docs/evidence/L01/compatibility-report.md`, `toolchain.lock.json`, and sanitized fixtures. The lock must contain actual installed versions, upstream tag/commit or distribution identity, Python/Node versions, workflow/step/profile digests, and supported OS. Do not prefill a successful check from this handoff. When an interpreter or upstream version changes, record the reason and re-run the compatibility gate instead of silently editing the lock.

The 25 October 2026 OpenSpec 1.15.0 / opencode 2.1.4 upgrade re-ran the gate
probes that the shipped surface depends on:

```bash
npm ci --prefix tooling/openspec
bash scripts/openspec.sh --version            # 1.15.0
.venv/bin/python -m pytest -q                 # real pinned-CLI integration tests
bash scripts/openspec.sh validate --all --strict
.venv/bin/python scripts/check_handoff.py
```

The live agent probe used the shipped profile shape with
`opencode run --auto --model deepseek/deepseek-flash "<fixed message>" --file
<prompt>` and completed with exit 0.

Test explicit OpenSpec Store creation/registration and root resolution; status/instructions/validate JSON; planning-versus-implementation completion; a harmless custom step with its real installed imports; non-TTY gates; fan-out ordering; loop aliases and outputs; paused/failed resume; and abrupt exit leaving a native running run. Record exit codes and confirm child-process termination before recovery experiments.

Keep production initialization and temporary experiment installation separate. No credential or paid model call is needed for the initial control-flow probes: a deterministic stub step can prove those contracts. Live agent acceptance is a later, explicitly recorded release case.

## References

- OpenSpec release (current pin): https://github.com/Fission-AI/OpenSpec/releases/tag/v1.15.0
- OpenSpec CLI at that tag: https://github.com/Fission-AI/OpenSpec/blob/v1.15.0/docs/cli.md
- OpenSpec schema at that tag: https://github.com/Fission-AI/OpenSpec/blob/v1.15.0/schemas/spec-driven/schema.yaml
- OpenSpec release (historical L01 pin): https://github.com/Fission-AI/OpenSpec/releases/tag/v1.14.3
- Spec Kit release: https://github.com/github/spec-kit/releases/tag/v1.2.1
- Specify workflow reference at that tag: https://github.com/github/spec-kit/blob/v1.2.1/docs/reference/workflows.md
