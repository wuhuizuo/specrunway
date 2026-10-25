# SpecRunway

Spec-driven execution across repositories.

SpecRunway coordinates one OpenSpec change that spans two or more existing Git
repositories. It freezes the approved plan and base commits, drives an ordered
per-repository implementation loop through a Specify workflow (`type:
specrunway`), validates agent results against trusted test evidence, enforces
repair budgets, gates plan and implementation review on local approval
receipts, and finishes at `ready_for_review`. Archiving is always explicit.

Status: local v1 implemented (source tasks L01-L18), with post-v1 guided onboarding (L19). Required acceptance
cases and evidence: `docs/ACCEPTANCE.md` and
`docs/evidence/05-release-local-v1.md`. No server, database, broker, account
system, or v2 component is required.

## Operate it

- `docs/RUNBOOK.md` — install, control checkout, plan, run, approve,
  resume/recover, repair, archive, backup, cleanup.
- Command surface: `specrunway wizard|doctor|init|plan|run|approve|resume|recover|status|archive`.
- `docs/examples/` — envelope, approval, manifest, local config, workflow.
- `docs/DESIGN.md` — architecture and contracts; `docs/DECISIONS.md` —
  recorded decisions (including D10: the SpecRunway rename).

Quick start:

```bash
python3 -m venv .venv && .venv/bin/python -m pip install .
.venv/bin/specrunway --version
.venv/bin/specrunway wizard      # guided local.yaml + request.md + plan
.venv/bin/specrunway doctor --json
```

`wizard` inspects sibling Git checkouts, asks only for stable control wiring
(Store, repositories, remotes, agent profile), writes `local.yaml`, and
initializes the Store/Specify workspace. It then asks which repositories
participate in the change, their order and dependencies, change-scoped test
commands (including monorepo paths), and whether a combined integration check
exists. It drafts `request.md` plus a routing manifest before calling `plan`.
An independent change can omit integration; no placeholder check is invented.
If the control directory is itself a Git checkout, the Store default is placed
in a sibling directory because OpenSpec refuses a Store nested inside another
checkout. Repeat runs reuse `local.yaml`. Every generated file is editable, and
`run`/`approve`/`archive` remain explicit commands.

The manual path still works: write `local.yaml` (store, repos, agent_profile,
test/integration profiles), run `specrunway init`, then
`specrunway plan <change> --request request.md`. `init` is idempotent and only
writes inside the control checkout. The pinned upstream tools are OpenSpec
1.14.3 (`tooling/openspec/`) and specify-cli 1.2.1 (`docs/TOOLCHAIN.md`);
`init` invokes them for you.

## Repository layout

| Path | Purpose |
| --- | --- |
| `src/specrunway/` | Coordinator package (CLI, planning, freezer, approvals, launcher, worktrees, results, runner, recovery, archive, Specify step bridge) |
| `src/specrunway/step_package/` | Bundled `type: specrunway` step shim installed by `specrunway init` |
| `tooling/openspec/` | Pinned OpenSpec CLI and lockfile |
| `mise.toml` | Developer Python/Node versions and bootstrap/check tasks |
| `tests/` | Deterministic fixtures (fake agent CLI) plus real pinned OpenSpec/Specify integration tests |
| `openspec/` | This repository's own development specs, archived changes 01-08, and active change 09 |
| `docs/` | Design, decisions, runbook, acceptance, evidence |

## Development environment

Developer interpreter versions are pinned with `mise` (Python 3.14.5,
Node 24.4.1). `mise` manages the interpreters and the project venv lifecycle;
`pip` and `npm` still own Python and Node package dependencies.

```bash
mise trust
mise install
eval "$(mise activate zsh)"   # once per shell; add to ~/.zshrc
mise run bootstrap            # create .venv, editable install, Specify, OpenSpec deps
mise run versions             # python, node, npm, git
```

Without shell activation, prefix ad-hoc commands with `mise exec --`
(for example `mise exec -- npm --version`) so the pinned Node is used.

Daily checks:

```bash
mise run check       # pytest, ruff, OpenSpec strict validation, handoff check
```

Individual commands remain available as
`.venv/bin/python -m pytest -q`, `.venv/bin/ruff check src tests`,
`scripts/openspec.sh validate --all --strict`, and
`.venv/bin/python scripts/check_handoff.py`.

`toolchain.lock.json` is the machine-readable L01 compatibility evidence, not
a package lock. `docs/TOOLCHAIN.md` explains the compatibility gate and probe
history; `mise.toml` is the current developer entry point.

Record real commands, versions, exit codes, and sanitized artifacts under
`docs/evidence/`. Fake agents prove coordination behavior, not a live model
integration; the live `opencode` replay is recorded in the release evidence.

## Boundaries

- Approval is local `self_asserted` confirmation with drift detection, not
  enterprise identity or tamper-resistant audit.
- Worktrees isolate ordinary edits; they are not a sandbox for hostile
  same-user processes.
- v1 does not push, merge, deploy, or archive the product Store
  automatically; those remain explicit operator actions.
- One active execution per control/Store checkout; v2 services are deferred.
