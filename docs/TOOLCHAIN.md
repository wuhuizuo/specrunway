# Toolchain setup and compatibility gate

## Observed release candidates

On 19 October 2026, the official repositories advertised OpenSpec v1.14.3 and Spec Kit v1.2.1 as published, non-prerelease releases. OpenSpec v1.14.3 requires Node >=20.19.0. Specify is the CLI supplied by the `specify-cli` Python distribution.

These candidates must pass L01. Do not replace them with a moving `main` or `latest` reference silently. Record an explained version change if the candidate fails a required contract.

## Repository development OpenSpec

`tooling/openspec/package.json` pins OpenSpec exactly and keeps Node development tooling separate from the Python application package.

```bash
npm --prefix tooling/openspec install
bash scripts/openspec.sh --version
bash scripts/openspec.sh init --tools codex
bash scripts/openspec.sh validate --all --strict --json
```

Commit the generated `tooling/openspec/package-lock.json` after reviewing it. Merge ignore rules and generated agent integration files with existing project policy. Preserve the supplied `openspec/config.yaml`. Never use `--force` as an automatic conflict-resolution step.

Before running change commands, confirm the resolved planning root is the intended repository. Runtime Store probes use a different disposable directory and explicit Store selection.

## Specify runtime probe

Use one isolated Python environment for the pinned Specify distribution and local probe code, so a copied custom step can import its core package. Installing the coordinator into an unrelated environment is not sufficient. Record interpreter and package paths without secrets.

For a fresh project environment on macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install "specify-cli @ git+https://github.com/github/spec-kit.git@v1.2.1"
.venv/bin/specify version
.venv/bin/specify workflow --help
```

Run initialization and custom-step probes in a disposable control workspace, not in a business repository. Verify `specify workflow step add specrunway --dev <package-directory>` against that release's help. Its package root must contain `step.yml` and `__init__.py`; the implementation must import the supported StepBase/StepResult types and delegate through public contracts.

Use `specify version` rather than assuming the CLI supports `--version`. Check JSON flags in help before using them.

## Planning status is not implementation status

During handoff validation, OpenSpec 1.14.3 returned `isPlanningComplete: true` and `isComplete: true` for change 01 while `instructions apply` reported zero of five implementation tasks complete. The status response described planning artifacts. Read apply progress and actual acceptance evidence before claiming implementation completion.

The handoff bootstrap commands were exercised in a disposable copy. `init --tools codex` generated Codex skills under `.agents/skills/` and preserved the supplied AGENTS.md and OpenSpec configuration in that copy. Recheck existing target-repository integrations before merging generated files.

## L01 report and lock

Deliver `docs/evidence/L01/compatibility-report.md`, `toolchain.lock.json`, and sanitized fixtures. The lock must contain actual installed versions, upstream tag/commit or distribution identity, Python/Node versions, workflow/step/profile digests, and supported OS. Do not prefill a successful lock from this handoff.

Test explicit OpenSpec Store creation/registration and root resolution; status/instructions/validate JSON; planning-versus-implementation completion; a harmless custom step with its real installed imports; non-TTY gates; fan-out ordering; loop aliases and outputs; paused/failed resume; and abrupt exit leaving a native running run. Record exit codes and confirm child-process termination before recovery experiments.

Keep production initialization and temporary experiment installation separate. No credential or paid model call is needed for the initial control-flow probes: a deterministic stub step can prove those contracts. Live agent acceptance is a later, explicitly recorded release case.

## References

- OpenSpec release: https://github.com/Fission-AI/OpenSpec/releases/tag/v1.14.3
- OpenSpec CLI at that tag: https://github.com/Fission-AI/OpenSpec/blob/v1.14.3/docs/cli.md
- OpenSpec schema at that tag: https://github.com/Fission-AI/OpenSpec/blob/v1.14.3/schemas/spec-driven/schema.yaml
- Spec Kit release: https://github.com/github/spec-kit/releases/tag/v1.2.1
- Specify workflow reference at that tag: https://github.com/github/spec-kit/blob/v1.2.1/docs/reference/workflows.md
