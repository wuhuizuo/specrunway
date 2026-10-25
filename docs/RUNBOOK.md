# SpecRunway v1 runbook (local coordinator)

Reproducible local operation of the Central Store Coordinator at pinned
tool versions (OpenSpec 1.14.3, specify-cli 1.2.1, Python 3.14, one real
coding-agent CLI). No server, database, broker, or team component is used.

## 1. Install

### Primary: uv tool installs (no Python or venv)

`uv` is a standalone binary; it provisions a private managed Python the first
time `uv tool install` needs one. Install uv from
<https://docs.astral.sh/uv/getting-started/installation/> (for example
`curl -LsSf https://astral.sh/uv/install.sh | sh`).

```bash
uv tool install "specrunway @ git+https://github.com/wuhuizuo/specrunway.git"
uv tool install "specify-cli @ git+https://github.com/github/spec-kit.git@v1.2.1"
npm install --global @fission-ai/openspec@1.14.3
uv tool update-shell          # once, if ~/.local/bin is not on PATH; open a new shell
```

From a source checkout use `uv tool install .`; from a local wheel use
`uv tool install ./specrunway-0.1.0-py3-none-any.whl`. The two Python tools get
separate isolated environments, so no venv is activated and no interpreter is
installed by the user. OpenSpec remains a Node package and needs Node >=
20.19.0; the global npm install puts `openspec` on PATH.

Verify the installed tools before initializing a control checkout:

```bash
specrunway --version          # specrunway 0.1.0
specify version               # 1.2.1 (prints a banner, then the version)
openspec --version            # 1.14.3
uv tool list                  # specrunway and specify-cli as separate tools
```

`specrunway doctor` needs a control checkout with `local.yaml`; run it after
section 2. It validates control wiring (`local.yaml`, Store, repos) and does
not probe the executables. If `init`, `plan`, `run`, or `archive` reports
`tool-missing`, compare your versions with the list above and check the
resolution order in `docs/TOOLCHAIN.md`.

### Fallback: manual wheel and venv

Use this when uv is unavailable or when testing the wheel directly. It needs a
system Python >= 3.11 and Node >= 20.19.0 for OpenSpec.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install specrunway-0.1.0-py3-none-any.whl   # or: pip install .
.venv/bin/python -m pip install "specify-cli @ git+https://github.com/github/spec-kit.git@v1.2.1"
npm install --global @fission-ai/openspec@1.14.3
.venv/bin/specrunway --version
```

From a source checkout, `npm ci --prefix tooling/openspec` installs the pinned
OpenSpec locally; `.venv/bin` and `tooling/openspec/node_modules/.bin` take
precedence over PATH (see `docs/TOOLCHAIN.md`). The rest of this runbook uses
bare `specrunway`; in the fallback use `.venv/bin/specrunway` or activate the
venv first. After section 2 creates `local.yaml`, verify wiring with
`.venv/bin/specrunway doctor --json` (exit 0 when ok).

## 2. Guided first use

From an empty control directory, the wizard removes the need to hand-write
`local.yaml` and `request.md`:

```bash
mkdir control && cd control
specrunway wizard
```

It performs two phases:

1. **Configuration**: discovers sibling Git checkouts and asks only for stable
   wiring: Store location, repository paths/ids, remote identities, and agent
   profile. It writes `local.yaml`, then runs the same bootstrap as
   `specrunway init`. The Store must live outside any existing Git checkout;
   when the control directory is a checkout, the default is a sibling
   `<control>-specrunway-store`. Test commands, dependencies, and integration
   checks are intentionally not requested here.
2. **Request**: asks for a short change summary,
   why/what/context/acceptance, participating repositories, execution order,
   task text, dependencies, and a change-scoped test command per participating
   repository. A monorepo can use a module-specific command. It also asks
   whether a combined integration check exists; if not, the manifest omits
   `integration_profile` and no integration round runs. It writes
   `requests/<change>.md` and
   `.specrunway/requests/<change>.manifest.yaml`, then calls
   `specrunway plan` with both. Task ids are assigned in the selected order;
   a repository with no dependency answer is independent.

Repeat runs on a configured checkout skip the configuration questions. Use
`--reconfigure` to revisit wiring, `--change`/`--description` to pre-seed the
request, `--request` to reuse an existing brief, and `--json` to keep stdout
parseable while prompts go to stderr. The wizard stops after planning; run,
approval, recovery, and archive stay explicit.

The manual configuration path remains available:

## 2a. Control checkout

`local.yaml` lives only in the control checkout (never in business repos):

```yaml
store:
  id: my-store
  path: /abs/path/to/store          # OpenSpec Store repository
repos:
  repo-a:
    path: /abs/path/to/repo-a       # existing Git checkout
    remote_identity: https://example.org/repo-a.git
agent_profile: primary-coding-agent
max_workers: 1
test_profiles:                     # trusted argv per manifest test_profile
  go-unit:
    command: ["go", "test", "./..."]
    cwd: cloudevents-server        # relative to the repo worktree
  k8s-validate:
    command: ["bash", "scripts/validate_k8s_yaml.sh"]

integration_profiles:              # executable combined check, trusted config
  quota-e2e:
    command: ["go", "test", "./test/e2e/..."]
    repo: operator                 # worktree to run from (default: first repo)
    timeout_seconds: 900
```

```bash
specrunway init --json     # Store setup + Specify workspace + bundled step
specrunway doctor --json   # wiring findings, exit 1 on errors
```

`init` is idempotent, creates the Store directory, registers the Store,
initializes `.specify` only when absent, installs the `specrunway` step from
the installed package, and never writes outside the control checkout. You do
not need to type the upstream `openspec`/`specify` commands yourself.

## 3. Plan

```bash
specrunway plan my-change --store my-store --request request.md --json
```

- Generates proposal/design/tasks/spec deltas in the Store when the change
  is new; accepts an existing complete manual plan otherwise.
- Task routing comes from the manifest (`task_ids`, `depends_on`,
  `allowed_paths`, `test_profile`). Forward dependencies, unknown repos,
  duplicate/missing tasks, and unknown profiles fail before execution.
- Planning success is NOT implementation completion; checkboxes stay
  unchecked.

## 4. Run and approve

```bash
specrunway run --change my-change --json          # freezes snapshot + starts native run
specrunway approve --execution <id> --kind plan --actor <you> --json
specrunway resume --execution <id> --json         # or: specrunway run --execution <id> --continue
specrunway status --execution <id> --json
```

Execution order:

1. `prepare` → ordered repos from `repo_order`.
2. Native plan gate pauses until a matching `self_asserted` receipt exists;
   `resume` re-checks the receipt and the live planning digest before
   supplying the native verdict.
3. `run-repo` fan-out with `max_concurrency: 1`: per-repo worktree at the
   frozen base OID, bounded prompt, agent CLI (argv only), trusted tests,
   result identity/ancestry/path validation, result + receipt persistence.
4. `verify-round` re-runs trusted tests; `repair-round` retries only failing
   repos with prior test feedback, bounded by `repo_max_attempts`. Test
   profiles are frozen from `test_profiles` in the snapshot (`command`, `cwd`,
   `timeout_seconds`, digest); editing `local.yaml` later does not change a
   running execution.
5. `integration-round` writes `matrix.json` (accepted head/result per repo),
   exports `SPECRUNWAY_MATRIX` + `SPECRUNWAY_HEAD_<REPO>`, and runs the frozen
   integration command. Failure is fed back to the last repository and
   retried within `integration_max_repairs`; a repeated failure at the same
   matrix head stops as `no-progress`. `ready_for_review` requires a passed
   receipt bound to the current matrix.
6. `accept-tasks` flips only the mapped tasks.md checkboxes (single writer).
7. Native implementation gate pauses for the implementation approval bound
   to the accepted-results digest; after approval `resume` completes at
   `ready_for_review`.

## 5. Failure handling

| Situation | Command | Behavior |
|---|---|---|
| Gate pause | `specrunway resume` | Checks receipt + digests, resumes native run |
| Retryable native failure | `specrunway resume` | Native resume; completed steps are not re-run |
| Blocked budget/no-progress | — | `specrunway status` shows `blocked`; preserve worktrees for takeover |
| Orphan `running`, owner dead | `specrunway recover` | Old run preserved `abandoned-running`, new native run same execution, verified receipts reused |
| Orphan `running`, owner alive | — | `specrunway recover` refuses `orphan-alive`; stop the process first |
| Archive outcome unknown | `specrunway recover` | Path-based reconciliation records the proven result; mixed state stays blocked |

Counters (`budgets`), accepted results, verification rows, and operation
intents/receipts live in `<control>/.specrunway/runs/<execution>/` and survive
process restarts. Never edit Specify's private run state.

## 6. Archive

```bash
specrunway archive --execution <id> --json                             # merged_commits (default)
specrunway archive --execution <id> --policy validated_commits \
            --confirm-validated --json                          # reviewed commits only
```

Preflight blocks when: phase is not `ready_for_review`, results are not
accepted/verified, mapped tasks remain unchecked, the implementation
approval no longer binds the results, final trusted tests fail or run at a
different head, or `merged_commits` finds an accepted head not merged into
the base ref (`partial-merge`). `validated_commits` requires explicit
selection plus `--confirm-validated` and never claims a main-branch merge.

Archive writes intent + backup before applying OpenSpec deltas, verifies the
resulting path/specs, and records a receipt. A successful archive is never
replayed. Backup: `<control>/.specrunway/runs/<execution>/archive-backup/<stamp>/`
(`change/` tree, `before.json`, `after.json`).

Restore drill: copy `archive-backup/<stamp>/change` back to the Store change
path to inspect or re-validate the pre-archive bytes; do not re-run archive
for the recorded execution (it returns `already_archived`).

## 7. Cleanup

```bash
openspec store unregister my-store --json   # disposable fixtures only
rm -rf <control>/.specrunway/runs/<execution>      # after evidence is captured
```

Preserve a usable failure scene (worktrees, logs, receipts) before cleanup
when investigating a failure.
