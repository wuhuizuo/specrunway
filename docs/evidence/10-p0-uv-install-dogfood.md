# P0 dogfood: uv install path executed by SpecRunway

Date: 25 October 2026. This is a dogfood record, not a release event.

Environment: macOS (Darwin 25.6.0, arm64), Python 3.14.5, uv 0.12.23,
Node 25.5.0, OpenSpec 1.14.3 (repository pin), specify-cli 1.2.1,
opencode 1.18.33 (pinned for this run; the Homebrew 2.1.4 install is
incompatible with the frozen agent profile, see Findings).

## What ran

A disposable central Store (`/tmp/specrunway-dogfood-p0/store`, store id
`p0-store`), a disposable control checkout
(`/tmp/specrunway-dogfood-p0/control`), and this repository as the single
business repository. The change `p0-uv-install` (delivery task P0: make `uv`
the primary install path) was planned, executed, reviewed, merged, and archived
through `specrunway` itself. The frozen base was `9fa90c1`; the accepted head
was `501af3d`.

The two generated planning artifacts that carried quality are the routing
manifest (`control/requests/p0-uv-install.manifest.yaml`) and the request
(`control/requests/p0-uv-install.md`); both were authored by hand because the
wizard's interactive prompt flow is not scriptable for this repository shape.
Test profile: a change-scoped `p0-unit` (`bash -c` wrapper with `PYTHONPATH=src`
and the checkout's pinned OpenSpec/specify binaries on `PATH`).

## Commands and results

| Command | Result |
| --- | --- |
| `specrunway init --root <control> --json` | exit 0; Store `p0-store` set up, Specify workspace initialized, bundled step installed |
| `specrunway plan p0-uv-install --store p0-store --request ... --manifest ...` | exit 0; generated `proposal.md`, `design.md`, `tasks.md`, `specs/specrunway-delivery/spec.md`; tasks `T001`-`T003` |
| `specrunway run --change p0-uv-install` | exit 0; paused at `plan-gate`; execution `f0cb25a8-1583-4cc7-9920-a258df2864a3`, native run `bc955372` |
| `specrunway approve --kind plan --actor wuhuizuo` | exit 0; subject digest `bd3cc6a1…` |
| `specrunway run --execution <id> --continue` (first attempt) | exit 1; `agent did not complete: exit 1`; `logs/specrunway/1/agent.log` = `Unrecognized flag: --pure in command opencode run` (Homebrew opencode 2.1.4) |
| retry with pinned opencode 1.18.33 and isolated `XDG_DATA_HOME` via `specrunway resume` | exit 0; attempt 2 executed; paused at `implementation-gate` |
| accepted result | head `501af3d`, `result_digest e2e95fd0…`, trusted receipt `exit 0`, `217 passed, 9 skipped` in 205.96 s |
| `specrunway approve --kind implementation --actor wuhuizuo` | exit 0; subject digest `c4c91b5a…` |
| `specrunway run --execution <id> --continue` | exit 0; native status `completed`; phase `ready_for_review` |
| `git merge --ff-only 501af3d` (original checkout) | fast-forward `9fa90c1..501af3d`, three documentation files |
| `mise run check` (original checkout) | `226 passed` in 260.07 s; `ruff` clean; OpenSpec strict `11 passed, 0 failed`; handoff check passed |
| `specrunway archive --execution <id>` | exit 0; policy `merged_commits`; archived as `2026-10-25-p0-uv-install`; final worktree tests `217 passed, 9 skipped` in 201.55 s; backup under `runs/<execution>/archive-backup/20261025T134045Z/` |

The first attempt used the `pending_gate: plan` path in `specrunway resume` and
retried the failed native step without editing private Specify state. Attempt 1
had already consumed one repository attempt (`budgets.specrunway.attempts_used`
became 2), so the launch failure is visible in the budget ledger even though the
agent never started work.

## uv distribution validation

Isolated from the user configuration (`UV_TOOL_DIR`, `UV_TOOL_BIN_DIR`):

- `uv tool install "specrunway @ git+https://github.com/wuhuizuo/specrunway.git"`
  → `Installed 1 executable: specrunway`; `/tmp/uvbin-p0/specrunway --version`
  → `specrunway 0.1.0`, exit 0. No pre-created virtual environment and no
  user-managed Python were needed; uv resolved a managed/system interpreter.
- `uv tool update-shell --help` → exit 0 (documented command exists).
- `specify version` → `specify 1.2.1`; `specify --version` → also `specify 1.2.1`.
- `openspec --version` (repository pin) → `1.14.3`.
- Upstream OpenSpec package declares `"engines": {"node": ">=20.19.0"}`, matching
  the documented Node requirement.

This validates the install commands added by the change, but does not validate a
clean machine with no system Python at all (uv's managed-Python download path was
not exercised end to end here).

## Findings from the dogfood run

1. **Agent launch is version-coupled and fails opaquely.** The frozen profile
   passes `--pure`, which opencode 2.1.4 rejects (`Unrecognized flag`). The pinned
   1.18.33 also cannot read a database written by 2.1.4 (`no such column:
   project_id`), so a fresh `XDG_DATA_HOME` was required. The user-facing result
   is `agent did not complete: exit 1` with the real cause only in a run log.
   Candidate follow-ups: a doctor/launcher preflight that reports the resolved
   agent binary and version, and documentation of the supported agent version.
2. **A fresh worktree does not satisfy this Python repository's own tests.**
   Nine tests skip in the worktree because they guard on repository-relative
   `.venv/bin/specify` and `tooling/openspec/node_modules` paths that exist only
   in the primary checkout; the agent had to run `npm ci --prefix
   tooling/openspec` inside the worktree to unskip archive tests. The merged
   checkout ran the full suite with `226 passed`. Self-hosted changes need a
   change-scoped profile that provisions tool paths inside the worktree (or
   tests that resolve tools through `PATH`).
3. **The plan generator dropped request prose.** `proposal.md` rendered
   `## What Changes` as "See design and tasks." because section extraction looks
   for a heading named exactly `what`; the request heading was `What Changes`.
   Request content loss is visible in the accepted plan artifacts.
4. **Pre-agent launch failures consume a repository attempt.** Attempt 1 never
   started the agent but incremented `budgets.<repo>.attempts_used`. With the
   default three attempts this is survivable; it is still misleading evidence of
   agent effort.
5. **Tool resolution depends on where the package is installed.** The global
   `openspec` on this machine is 1.0.2 and has no `store` subcommand; a source
   checkout resolves the pinned 1.14.3 first, but a wheel install falls back to
   `PATH`. This confirms that the uv install path must pin the global OpenSpec
   version, and that `doctor` should assert a Store-capable OpenSpec.
6. **Post-archive bookkeeping is slightly stale.** After archive the phase is
   `archived` and `pending_gate` is null, but `active_owner` still reports the
   archive process pid. It did not block the run.

## Artifacts

Disposable (not in Git): `/tmp/specrunway-dogfood-p0/control/.specrunway/runs/
f0cb25a8-1583-4cc7-9920-a258df2864a3/` (status, snapshot, receipts, prompts,
worktree, archive backup, sanitized raw logs) and
`/tmp/specrunway-dogfood-p0/store/` (archived change and
`openspec/specs/specrunway-delivery/spec.md`). The Store id `p0-store` is a
disposable local registration.

Committed: the accepted documentation change (`501af3d`), this evidence file,
and the `docs/HANDOFF_STATE.md` update.

## Non-claims

- The change was documentation-only; this run does not demonstrate agent quality
  on code changes.
- The run used a live `opencode` 1.18.33 agent with a real model, but it is not
  the release acceptance matrix and does not change any V1 acceptance status.
- The archive applied deltas to the disposable Store, not to this repository's
  `openspec/` baseline.
