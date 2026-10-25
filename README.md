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

Quick start (uv; no Python or virtual environment required):

```bash
uv tool install "specrunway @ git+https://github.com/wuhuizuo/specrunway.git"
uv tool install "specify-cli @ git+https://github.com/github/spec-kit.git@v1.2.1"
npm install --global @fission-ai/openspec@1.14.3
uv tool update-shell               # once, if ~/.local/bin is not on PATH
specrunway --version               # specrunway 0.1.0
specrunway wizard                  # guided local.yaml + request.md + plan
specrunway doctor --json           # wiring report; exit 0 when ok
```

`uv` provisions its own managed Python for the `specrunway` and `specify`
tool environments, so users do not install Python or activate a venv. OpenSpec
remains a Node package and needs Node >= 20.19.0; install the pinned npm
release globally. In a source checkout, `uv tool install .` installs the
current tree, and `npm ci --prefix tooling/openspec` installs the pinned
OpenSpec locally instead of globally. Install a released wheel with
`uv tool install ./specrunway-0.1.0-py3-none-any.whl` when one is available.

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

The manual fallback keeps the pinned upstream versions without uv:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install specrunway-0.1.0-py3-none-any.whl   # or: pip install .
.venv/bin/python -m pip install "specify-cli @ git+https://github.com/github/spec-kit.git@v1.2.1"
npm ci --prefix tooling/openspec        # source checkout only
.venv/bin/specrunway --version
```

Then write `local.yaml` (store, repos, agent_profile, test/integration
profiles), run `specrunway init`, and `specrunway plan <change> --request
request.md`. `init` is idempotent and only writes inside the control checkout.
The pinned upstream tools are OpenSpec 1.14.3 (`tooling/openspec/`) and
specify-cli 1.2.1 (`docs/TOOLCHAIN.md`); `init` invokes them for you. A source
checkout resolves `.venv/bin` and `tooling/openspec/node_modules/.bin` before
PATH; outside a checkout both CLIs come from PATH (`docs/TOOLCHAIN.md`).

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
- The uv install path needs `uv` and Node >= 20.19.0 for OpenSpec, but no
  system Python or activated venv. The manual wheel/venv path remains a
  fallback and is the only one that needs a user-managed interpreter.
