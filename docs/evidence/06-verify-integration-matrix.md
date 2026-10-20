# Change 06 evidence: combined-matrix integration verification

Pinned toolchain unchanged (OpenSpec 1.14.3, specify-cli 1.2.1,
Python 3.14). Change 06 closes the archived `trusted-verification` gaps:
executing the configured integration profile against the accepted commit
matrix and persisting integration repair counters.

## Implemented (L16)

- `specrunway/models/local.py` — optional
  `integration_profiles: {name: {command: [argv...], repo?: <repo_id>,
  timeout_seconds?: int}}` in the machine-only control config; argv,
  repo, and timeout are shape-checked.
- `specrunway/models/records.py` + `freezer.py` — snapshots may freeze
  `integration = {profile, command, cwd_repo, timeout_seconds,
  config_digest}`; the argv and digest are immutable for the execution.
- `specrunway/integration.py` — resolves the manifest-named profile
  (refusing unknown/misconfigured profiles before any agent work), builds
  the accepted commit matrix (repo id, head, result digest, verification),
  writes `integration/round-<n>/matrix.json`, exports `SPECRUNWAY_MATRIX`
  and `SPECRUNWAY_HEAD_<REPO>`, runs the frozen argv in the configured
  worktree, and persists a receipt with log/matrix refs.
- `specrunway/bridge/actions.py` + `bridge/workflow.py` — new workflow
  step `integration-round` after repository repair:
  - requires accepted + verified results for every repo;
  - a failing integration command feeds the log tail to the last
    repository's agent (retry forced; verified-result reuse is skipped),
    re-runs trusted tests, and retries the combined check;
  - bounded by `integration_max_repairs`; identical heads + exit code stop
    as `no-progress`; exhaustion enters phase `blocked`;
  - `integration_repairs` / `integration_rounds` are CAS-persisted in run
    state, so a restarted CLI or recovered native run cannot reset them;
  - `complete` refuses `integration-required`, `integration-failed`, or
    `integration-stale` (receipt matrix digest must equal the live matrix).

## Verified

`tests/test_integration.py` (7 tests, deterministic fake agent + real git):

1. Unknown integration profile refused before execution
   (`integration-profile-missing`).
2. Profile pointing at a repo outside `repo_order` refused
   (`integration-repo`).
3. Repo tests green + integration exit 1 with `integration_max_repairs=0`
   → `integration-exhausted`, phase `blocked`, `complete` refuses
   `integration-failed`, never `ready_for_review`.
4. Fail-then-pass integration check → one repair round, `repairs_used=1`,
   `integration_rounds=2`, the repairing prompt contains
   `## Integration failure feedback`, completion succeeds, and a fresh
   `FileRunStore` reads the same counters.
5. Repeated failure at an unchanged head/exit code → `no-progress` after
   one repair instead of burning the remaining budget.
6. Snapshot without a frozen profile → `complete` refuses
   `integration-required`.
7. A new accepted head after a passed integration check → `complete`
   refuses `integration-stale`.

Also updated: `tests/test_runner_flow.py` runs the real Specify engine with
an `e2e` integration profile and reaches `ready_for_review`;
`tests/test_bridge_step.py` seeds matrix-bound integration evidence for the
installed-step probe.

Commands and outcomes:

```text
$ .venv/bin/python -m pytest tests/test_integration.py -q   # 7 passed
$ .venv/bin/python -m pytest tests/ -q                     # 194 passed
$ .venv/bin/ruff check src tests                           # clean
$ .venv/bin/python scripts/check_handoff.py                # passed (L01-L16)
$ tooling/openspec/node_modules/.bin/openspec validate --all --strict --json
  # all valid
```

Acceptance linkage: V1-A07 (integration repair budget and persistence),
V1-A09 (combined matrix execution and blocking).
