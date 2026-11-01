# SpecRunway

Spec-driven execution across repositories.

SpecRunway coordinates one OpenSpec change that spans one or more existing Git
repositories. It freezes the approved plan, routing, base commits, and test
profiles; drives ordered per-repository attempts through a Specify workflow;
accepts only results backed by trusted test evidence; gates plan and
implementation review on local approval receipts; and stops at
`ready_for_review`. Merging and archive remain explicit operator actions.

Status: local v1 implemented, including guided onboarding.

## Start here

| Page | Use it for |
| --- | --- |
| [Quickstart](docs/user/quickstart.md) | Install, configure, plan, run, approve, and reach `ready_for_review`. |
| [Concepts](docs/user/concepts.md) | Changes, executions, snapshots, approvals, trusted results, and operation intents. |
| [Commands](docs/user/commands.md) | Every subcommand with arguments, stable error codes, and next actions. |
| [Troubleshooting](docs/user/troubleshooting.md) | Stuck phases, orphaned runs, archive refusals, and nested Store paths. |

## Install and first run

```bash
uv tool install "specrunway @ git+https://github.com/wuhuizuo/specrunway.git"
uv tool install "specify-cli @ git+https://github.com/github/spec-kit.git@v1.2.1"
npm install --global @fission-ai/openspec@1.15.0
uv tool update-shell

mkdir ~/work/specrunway-control && cd ~/work/specrunway-control
specrunway wizard
specrunway doctor --json
```

The wizard writes `local.yaml`, initializes the Store and Specify workspace,
drafts a reviewable request and routing manifest, and plans the change. It
stops there; the run and both approvals stay explicit:

```bash
specrunway run --change <change> --json
specrunway approve --execution <id> --kind plan --actor <you>
specrunway run --execution <id> --continue
# review accepted results, then:
specrunway approve --execution <id> --kind implementation --actor <you>
specrunway run --execution <id> --continue
specrunway archive --execution <id>     # after merging, if required
```

`uv` provisions its own Python, so no system Python or activated virtual
environment is needed. OpenSpec still needs Node.js >= 20.19.0. The shipped
agent profile uses `opencode` 2.1.4 or newer and relies on opencode's
configured model. The manual wheel/venv install path and the full command
surface are documented in [docs/user/quickstart.md](docs/user/quickstart.md)
and [docs/user/commands.md](docs/user/commands.md).

## For contributors

This section is not part of the operator path.

- `docs/RUNBOOK.md` - long-form operation, failure handling, archive backup,
  and cleanup.
- `docs/DESIGN.md` - architecture, contracts, and v2 boundaries.
- `docs/DECISIONS.md` - recorded scope and design decisions.
- `docs/TOOLCHAIN.md` - pinned tools, resolution order, and the compatibility
  gate.
- `docs/ACCEPTANCE.md` and `docs/evidence/` - acceptance status and replay
  evidence.
- `AGENTS.md` - repository development instructions.

Local v1 has no server, database, broker, account system, or Web UI. Approval
is `self_asserted`; worktrees isolate ordinary edits but are not a hostile-
process sandbox. One active execution is allowed per control/Store checkout.
