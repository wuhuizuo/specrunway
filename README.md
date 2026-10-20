# SpecRunway

Spec-driven execution across repositories.

SpecRunway coordinates one OpenSpec change that spans two or more existing Git
repositories. It freezes the approved plan and base commits, drives an ordered
per-repository implementation loop through a Specify workflow (`type:
specrunway`), validates agent results against trusted test evidence, enforces
repair budgets, gates plan and implementation review on local approval
receipts, and finishes at `ready_for_review`. Archiving is always explicit.

Status: local v1 implemented (source tasks L01-L15). Required acceptance
cases and evidence: `docs/ACCEPTANCE.md` and
`docs/evidence/05-release-local-v1.md`. No server, database, broker, account
system, or v2 component is required.

## Operate it

- `docs/RUNBOOK.md` — install, control checkout, plan, run, approve,
  resume/recover, repair, archive, backup, cleanup.
- Command surface: `specrunway doctor|plan|run|approve|resume|recover|status|archive`.
- `docs/examples/` — envelope, approval, manifest, local config, workflow.
- `docs/DESIGN.md` — architecture and contracts; `docs/DECISIONS.md` —
  recorded decisions (including D10: the SpecRunway rename).

Quick start:

```bash
python3 -m venv .venv && .venv/bin/python -m pip install .
.venv/bin/specrunway --version
# write local.yaml (store, repos, agent_profile, integration_profiles)
.venv/bin/specrunway init        # Store + Specify workspace + bundled step
.venv/bin/specrunway doctor --json
```

`init` is idempotent and only writes inside the control checkout. The pinned
upstream tools are OpenSpec 1.14.3 (`tooling/openspec/`) and specify-cli 1.2.1
(`docs/TOOLCHAIN.md`); `init` invokes them for you.

## Repository layout

| Path | Purpose |
| --- | --- |
| `src/specrunway/` | Coordinator package (CLI, planning, freezer, approvals, launcher, worktrees, results, runner, recovery, archive, Specify step bridge) |
| `src/specrunway/step_package/` | Bundled `type: specrunway` step shim installed by `specrunway init` |
| `tooling/openspec/` | Pinned OpenSpec CLI and lockfile |
| `tests/` | Deterministic fixtures (fake agent CLI) plus real pinned OpenSpec/Specify integration tests |
| `openspec/` | This repository's own development specs and archived changes 01-05 |
| `docs/` | Design, decisions, runbook, acceptance, evidence |

## Development checks

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
tooling/openspec/node_modules/.bin/openspec validate --all --strict --json
.venv/bin/python scripts/check_handoff.py
```

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
