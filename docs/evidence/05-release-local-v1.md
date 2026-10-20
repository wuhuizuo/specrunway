# Change 05 evidence: local v1 release replays

Pinned toolchain: OpenSpec 1.14.3 (npm lock in `tooling/openspec/`),
specify-cli 1.2.1 (`v1.2.1`, commit 9dca9bf42), Python 3.14.5, real agent
CLI profile `opencode` 1.18.33 (`opencode run --auto --pure --file`).

## Installation in a fresh directory (V1-A14, V1-A02)

```text
$ python3 -m venv "$TMP/venv"                       # TMP = disposable temp dir
$ "$TMP/venv/bin/python" -m pip install -q <repo>   # exit 0
$ "$TMP/venv/bin/hub" --version                     # hub 0.1.0
$ python3 -m pip wheel --no-deps -w "$TMP/dist" <repo>
  produced hub_cli-0.1.0-py3-none-any.whl
$ python3 -m venv "$TMP/venv-wheel"
$ "$TMP/venv-wheel/bin/python" -m pip install -q \
    "$TMP/dist/hub_cli-0.1.0-py3-none-any.whl"      # exit 0
$ "$TMP/venv-wheel/bin/hub" --help                  # commands: doctor, status,
  resume, recover, archive, run, plan, approve
$ "$TMP/venv-wheel/bin/hub" doctor --root "$TMP/control" --json
  exit 1 before store setup: [store-missing], [remote-missing]
  after `openspec store setup l15store --path ...` and adding the repo remote:
  exit 0 with ok findings local-yaml, store.id, store.path, agent-profile,
  repo:repo-a, max_workers
```

Only the wheel (dependency: PyYAML) and the pinned upstream CLIs are
required. No server, database, broker, or v2 package is imported; the
installed `hub` ran `doctor` from a directory outside the development
checkout.

## Runbook replay matrix (V1-A14)

`docs/RUNBOOK.md` describes the same commands; each path below was executed
with the pinned upstream CLIs in this repository's test suite (real git
repositories, real Specify engine and OpenSpec CLI; deterministic fake
coding-agent CLI shadowing the real profile argv when a live model is not
available).

| Path | Command | Result | Evidence |
|---|---|---|---|
| Normal loop | `hub run --change demo` → `hub approve --kind plan` → `hub resume` → `hub approve --kind implementation` → `hub run --continue` | plan gate paused, ordered repo-a→repo-b, repo-b prompt carried repo-a accepted head, tasks.md checked, implementation gate paused, final `ready_for_review`; original checkouts unchanged | `tests/test_runner_flow.py` |
| Repair | `verify-round`/`repair-round` with failing tests | one repair round passes after feedback; max two repairs; exhaustion/no-progress stop at phase `blocked`; counters persist across a fresh store handle | `tests/test_budget_repair.py` |
| Abnormal recovery | `hub recover` on orphan `running` (owner dead), `hub resume` after drift | old native run preserved `abandoned-running`, new native run same execution, verified receipt reuse; stale plan → `approval-stale`; live owner → `orphan-alive` | `tests/test_recovery.py` |
| Timed-out / killed agent | launcher process-group kill | child and grandchild exit; run marked uncertain; no duplicate effect | `tests/test_launcher.py`; `tests/test_runstore.py` |
| Archive + backup | `hub archive` (`merged_commits`, then `validated_commits` with confirmation) | partial merge / stale approval / unchecked tasks block; success moves the change to `changes/archive/<date>-…`, writes `archive-backup/<stamp>/{change,before.json,after.json}` with byte-identical pre-archive files; replay returns `already_archived` | `tests/test_archive.py` |
| Interrupted archive | intent recorded, process "killed" before receipt | path-based reconciliation records the proven result without applying deltas again; mixed active/archive state blocks; `not-applied` allows retry | `tests/test_archive.py` |
| Cleanup | `openspec store unregister <id>` | fixtures unregistered; temp control/runs removed | fixtures in the suites above |

## Acceptance matrix

| Case | Status | Mode | Evidence |
|---|---|---|---|
| V1-A01 Pinned tool and step contracts | Passed | upstream probes | `docs/evidence/L01/compatibility-report.md`, `toolchain.lock.json` |
| V1-A02 Standalone local use and repo changes | Passed | fixture agent; live model Blocked | install above; `tests/test_runner_flow.py` (originals untouched) |
| V1-A03 Configuration and dependency order | Passed | fixtures | `tests/test_manifest.py`, `tests/test_local.py`, `tests/test_planning.py` |
| V1-A04 Planning versus implementation completion | Passed | fixtures | `docs/evidence/03-…`; `tests/test_archive.py` (`not-ready`) |
| V1-A05 Local approval and digest drift | Passed | fixtures | `tests/test_freeze_approvals.py` |
| V1-A06 Worktrees and result validation | Passed | fixture agent | `tests/test_worktrees_results.py`, `tests/test_launcher.py` |
| V1-A07 Test and repair budgets | Passed | fixtures | `tests/test_budget_repair.py` |
| V1-A08 Local locking and atomic files | Passed | fixtures | `tests/test_runstore.py`, `tests/test_archive.py`, `tests/test_recovery.py` |
| V1-A09 Sequential two-repo execution | Passed | fixture agent | `tests/test_runner_flow.py` |
| V1-A10 Resume and orphan recovery | Passed | fixtures | `tests/test_recovery.py`, `tests/test_runner_flow.py` |
| V1-A11 Explicit archive and code acceptance | Passed | real OpenSpec CLI | `tests/test_archive.py` |
| V1-A12 Uncertain archive outcome | Passed | fixtures | `tests/test_archive.py` |
| V1-A13 Portable business data | Passed | schema review + test | `tests/test_archive.py::test_portable_business_payloads`, `docs/examples/` |
| V1-A14 Installation and human takeover | Passed for fixture replays; live-agent replay Blocked | install + fixtures | this document; `docs/RUNBOOK.md` |

## Blocker: live coding-agent run

The release-level live case (real `primary-coding-agent` model execution on
two fixture repositories, recorded with the actual model identity) was not
run in this session because no model credentials/entitlement were available
in the environment. Per `docs/ACCEPTANCE.md`, coordination cases proven with
the deterministic fake agent are reported in fixture-agent mode, and the
live-agent sub-case is **Blocked**, not Passed. The exact command to run it
is unchanged: point `agent_profile: primary-coding-agent` at the installed
`opencode` 1.18.33 and execute `hub run` from the runbook.

## Known limitations (v1, deliberate)

- One active execution per control/Store checkout (`max_workers: 1`); no
  parallel repo execution.
- A worktree isolates ordinary edits, not hostile same-user processes.
- Approval is `self_asserted`; no team identity or tamper-resistant audit.
- `merged_commits` verifies merge ancestry only; it never pushes or merges.
- `validated_commits` records reviewed commits without a main-branch claim.
- No Jenkins integration, Web UI, HTTP service, database, or v2 code paths.
- Requires an initialized Specify workspace and the installed hub step.

## Checks

```text
$ .venv/bin/python -m pytest tests/ -q        # 186 passed
$ .venv/bin/ruff check src tests              # clean
$ tooling/openspec/node_modules/.bin/openspec validate --all --strict --json
  # 5/5 changes valid
$ .venv/bin/python scripts/check_handoff.py   # passed
```
