# Change 04 evidence: recovery and archive

Commands run from the repository root with the pinned toolchain
(specify-cli 1.2.1, OpenSpec 1.14.3). Fixtures are disposable local
repositories; no network, database, or v2 component is involved.

## L13 normal resume and orphan-running recovery (task 1.1)

Built:

- `src/hubcoord/recovery.py`
  - `execution_status` — phase, pending gate, native run id, preserved
    abandoned runs, revision, active owner, budgets, results,
    verification, approvals, operation intents/receipts.
  - `resume_execution` — recomputes the live planning digest from the Store
    change and refuses when it no longer matches the frozen snapshot
    (`approval-stale`); requires the pending gate receipt (`no-approval`);
    then follows the native contract: `specify workflow resume` for paused
    or failed runs, `continue_execution` for gate pauses. It never re-runs
    completed native steps.
  - `recover_execution` — for a native run still reporting `running`:
    refuses while the recorded owner PID is alive (`orphan-alive`); after
    the operator confirms termination it appends the old run to
    `native_runs` (`abandoned-running`) for diagnosis, marks the execution
    `interrupted`, and starts a NEW native run under the SAME
    `execution_id`. The old native run's private state is never edited.
  - `reusable_result` — before any new attempt, a recorded accepted result
    is reused only when its stored bytes match `result_digest`, the run
    state agrees, the accepted commit still exists and descends from the
    frozen base, and the trusted test receipt is `passed`. Any mismatch
    raises `evidence-conflict` instead of repeating the side effect.
- `hub status`, `hub resume`, `hub recover` are real commands (stub
  machinery removed).
- `run-repo` calls `reusable_result` before spending an attempt, so a
  replacement native run reuses verified completed work.

Verified (`tests/test_recovery.py`, 6 tests + `test_runner_flow.py`):

1. Changed plan content after approval → `resume` exits 1 with
   `approval-stale` and no native advance.
2. Missing pending gate receipt → `no-approval`.
3. Verified accepted result → `reusable_result` returns `reused: true`
   with the accepted head; tampering with `result.json` after the fact →
   `evidence-conflict`.
4. Orphan `running` with a dead owner → new native run id, old run
   preserved as `abandoned-running`, phase `interrupted`
   (`test_orphan_running_recovery_preserves_old_run`).
5. Orphan `running` with a live owner → `orphan-alive` refusal.
6. `hub status` reports phase/pending gate/approvals/repo order.
7. End-to-end loop now resumes the paused plan gate through
   `hub resume` (real Specify CLI + real git fixtures) and reaches the
   implementation gate; see `tests/test_runner_flow.py`.
8. Locking/atomic-write/revision coverage remains from
   `tests/test_runstore.py` (two-writer lock timeout, CAS revision
   conflict, atomic JSON) and is exercised by the intent/receipt paths
   above.

## L14 explicit archive and local backup (tasks 2.1, 2.2)

Built:

- `src/hubcoord/archive.py`
  - `archive_execution` preflight: phase must be `ready_for_review`;
    every required repo needs a passed accepted result AND passed
    verification row (`unaccepted-code`); all mapped tasks.md checkboxes
    must be `[x]`; the implementation approval must still bind the current
    accepted-results digest (`approval-stale`); the trusted tests are run
    once more in each worktree and must pass at the accepted head
    (`verification-stale`).
  - Completion policy: `merged_commits` (default, or manifest
    `completion_policy`) verifies each accepted head is an ancestor of the
    repository's base ref and otherwise refuses `partial-merge`;
    `validated_commits` requires `--policy validated_commits` plus
    `--confirm-validated` and records reviewed commits without a merge
    claim (`confirmation-required`).
  - Backup: the Store change directory is copied to
    `<run>/archive-backup/<stamp>/change` with `before.json` (change path +
    specs-tree digest) and `after.json` after success.
  - Intent/receipt: the archive operation key includes the planning digest
    and is written BEFORE OpenSpec applies deltas; success records
    `archived_as`, path, `specs_updated`, and the resulting specs digest,
    then sets phase `archived`. A recorded intent is returned as
    `already_archived` and is never replayed.
  - Failure paths mark the operation `uncertain`, set phase `blocked`, and
    keep the backup and evidence (`archive-uncertain`); an active+archived
    path conflict blocks (`archive-mixed`).
  - `reconcile_pending_archive` (also called from `hub recover`): proves
    the actual outcome from paths before retrying — completed archive gets
    a receipt without applying deltas again; an unapplied intent is
    reconciled so a new attempt is possible; mixed/lost states stay
    blocked.

Verified (`tests/test_archive.py`, 8 tests, real pinned OpenSpec CLI and a
registered disposable store):

1. Default policy blocks `partial-merge` before any delta is applied;
   after merging the accepted head into `main`, archive succeeds, the
   change moves to `openspec/changes/archive/<date>-ship-demo`, the backup
   exists, and phase is `archived`. A second call returns
   `already_archived` without replay.
2. Tampering with the accepted result after review → `approval-stale`.
3. Unchecked mapped task → `unaccepted-code`.
4. Non-`ready_for_review` phase → `not-ready`.
5. `validated_commits` without confirmation → `confirmation-required`;
   with `--confirm-validated` it archives and makes no merge claim.
6. Completed archive without a receipt (simulated crash after the move) →
   reconciliation records the receipt and phase `archived`, no replay.
7. Mixed active+archived paths → `archive-mixed`, evidence preserved.
8. Intent with no applied changes → reconciled as `not-applied`, allowing
   a later attempt.

Full suite after change 04: `pytest -q` → 185 passed;
`ruff check src tests` → clean.

Acceptance linkage: V1-A08 (locking, revisions, intent/receipt atomicity),
V1-A10 (normal resume, retryable failure, orphan reconciliation, receipt
reuse), V1-A11 (explicit archive policy, stale review, missing
acceptance, partial merge), V1-A12 (uncertain archive reconciliation,
mixed state, backup). Remaining release-level gaps are enumerated in
`docs/HANDOFF_STATE.md` (live-agent run, fresh-directory install matrix).
