# Acceptance procedures and evidence

All cases start as Not run. Required v1 release cases are V1-A01 through V1-A14. v2/Migration and Optional cases are reference-only in this implementation.

## Evidence rules

Use Passed, Failed, Blocked, or Not run. A passing record names the actual tool versions, commands and exit codes, commit matrix where relevant, and sanitized evidence files. Tests with fake agents prove deterministic coordination behavior; they do not prove a real coding-agent integration. Record which mode each case used.

Before v1 release, run installed-package replays on disposable repositories. Bind final verification to accepted commits. Do not infer acceptance from completed checkboxes, generated plans, or agent success text.

## V1-A01 Pinned tool and step contracts
Version: v1; scope: Required.
**Steps:** Capture --version/--help and JSON. Install the hub step. Exercise non-TTY gates, loops, fan-out, normal resume, and a killed running process.
**Pass criteria:** Record behavior of the selected release. Distinguish valid and malformed responses. Main-branch documentation alone is insufficient.
**Expected evidence:** Compatibility report; fixtures; SDK trace
**Status:** Passed (compatibility-gate scope, open-spec/dev side; replayed at release via V1-A14)
**Actual evidence:** `docs/evidence/L01/compatibility-report.md`; `toolchain.lock.json`; `docs/evidence/L01/fixtures/` (OpenSpec 1.14.3 npm lock integrity; Specify 1.2.1 @ commit 9dca9bf42; probe JSON/scratch logs)

## V1-A02 Standalone local use and repo changes
Version: v1; scope: Required.
**Steps:** Install one Hub package, agreed upstream tools, and one agent. Run two Git checkouts; compare diff and untracked files before/after.
**Pass criteria:** No server, database, or v2 dependency is needed. Business repositories contain only intended code/test changes.
**Expected evidence:** Installation log; Git diff/status
**Status:** Passed (fixture-agent mode; live-agent run Blocked)
**Actual evidence:** `docs/evidence/05-release-local-v1.md` (fresh wheel install, wheel/venv versions); `tests/test_runner_flow.py` (two checkouts, intended worktree changes only, originals unchanged)

## V1-A03 Configuration and explicit dependency order
Version: v1; scope: Required.
**Steps:** Try unknown repo/remote, duplicate or missing tasks, forward dependencies, cycles, invalid paths, and unknown profiles.
**Pass criteria:** Preflight fails without editing code. repo_order satisfies dependencies. Machine paths never enter shared manifests.
**Expected evidence:** Validation findings; clean worktree
**Status:** Passed
**Actual evidence:** `tests/test_manifest.py`, `tests/test_local.py`, `tests/test_planning.py` (unknown repo/remote, duplicate/missing tasks, forward dependency, invalid paths, unknown profile)

## V1-A04 Planning versus implementation completion
Version: v1; scope: Required.
**Steps:** Generate complete planning artifacts. Query status. Request archive before implementation tasks have run.
**Pass criteria:** Planning may be complete while implementation remains false. Premature archive is blocked.
**Expected evidence:** Status JSON; archive preflight
**Status:** Passed
**Actual evidence:** `docs/evidence/03-deliver-two-repo-loop.md` (planning_complete vs tasks unchecked); `tests/test_archive.py` (`not-ready` archive refusal)

## V1-A05 Local approval and digest drift
Version: v1; scope: Required.
**Steps:** Approve a plan, then change design/rules/task text. Separately change only checkboxes. Try injecting a gate approval directly.
**Pass criteria:** Content drift invalidates approval. Checkboxes preserve planning_digest. Execution requires a matching approval receipt.
**Expected evidence:** Digests; local approval receipt
**Status:** Passed
**Actual evidence:** `tests/test_freeze_approvals.py` (checkbox-only invariance, text/rule drift, injected-verdict refusal, stale receipt)

## V1-A06 Worktrees and result validation
Version: v1; scope: Required.
**Steps:** Keep uncommitted files in the original checkout. Supply wrong result digest/head and unexpected changed paths.
**Pass criteria:** The original checkout is preserved. Invalid results are rejected. A worktree is not claimed to sandbox a hostile same-user process.
**Expected evidence:** Git/test results; rejection log
**Status:** Passed (fixture-agent mode; same-user sandbox caveat recorded)
**Actual evidence:** `tests/test_worktrees_results.py` (untracked preservation, foreign head/digest/path rejection); `tests/test_launcher.py` (real process-group kill)

## V1-A07 Test and repair budgets
Version: v1; scope: Required.
**Steps:** Cause unit/integration failures. Allow initial work plus at most two repairs. Repeat one failure and restart before continuing.
**Pass criteria:** Feedback reaches the agent. Budgets survive recovery. Repeated failure or exhausted budget stops work; failed verification cannot become ready.
**Expected evidence:** Test/repair receipts; persisted budget
**Status:** Passed
**Actual evidence:** `tests/test_budget_repair.py` (feedback delivery, two repairs max, no-progress, exhaustion, counters across restart, failed verification cannot become ready)

## V1-A08 Local locking and atomic files
Version: v1; scope: Required.
**Steps:** Run two writers against one checkout. Kill during temporary state writing, and after an external effect but before its receipt.
**Pass criteria:** The second writer is blocked. Committed JSON stays readable. Proven completed effects are reconciled rather than repeated.
**Expected evidence:** Lock test; state revision; operation intent
**Status:** Passed
**Actual evidence:** `tests/test_runstore.py` (two-writer lock, CAS revision, atomic JSON); `tests/test_archive.py` (intent/receipt, uncertain reconciliation); `tests/test_recovery.py`

## V1-A09 Sequential two-repo execution
Version: v1; scope: Required.
**Steps:** Run both repositories in repo_order. The second consumes the first accepted commit and contract.
**Pass criteria:** Order is correct. Both results and the integration matrix are traceable. Actual parallel execution is unnecessary.
**Expected evidence:** Commit matrix; ordered events
**Status:** Passed (fixture-agent mode)
**Actual evidence:** `tests/test_runner_flow.py` (ordered fan-out, repo-b prompt carries repo-a accepted head, both results traceable)

## V1-A10 Normal resume and orphan-running recovery
Version: v1; scope: Required.
**Steps:** Resume a gate pause and retryable failure. Kill a running process, confirm children exit, then reconcile/recover.
**Pass criteria:** Paused/failed runs follow upstream resume. Do not force-edit running state. A new native run may reuse verified receipts under the same execution.
**Expected evidence:** Native-run mapping; receipt reuse
**Status:** Passed
**Actual evidence:** `tests/test_recovery.py` (stale plan, receipt reuse/evidence conflict, orphan dead vs live, old-run preservation); `tests/test_runner_flow.py` (`hub resume`)

## V1-A11 Explicit archive and code acceptance
Version: v1; scope: Required.
**Steps:** Finish run at ready_for_review. Try archive with unaccepted code, stale final approval, or partial merge. Separately select validated_commits explicitly.
**Pass criteria:** Missing conditions block archive clearly. Personal validated_commits requires its own confirmation and makes no main-branch merge claim.
**Expected evidence:** Completion policy; final review; Git refs
**Status:** Passed
**Actual evidence:** `tests/test_archive.py` (partial merge, stale approval, unchecked tasks, validated_commits confirmation, replay refusal)

## V1-A12 Uncertain archive outcome
Version: v1; scope: Required.
**Steps:** Kill after archive but before receipt. Construct mixed active/archive state and a changed specification baseline.
**Pass criteria:** Proven completion gets a receipt. Mixed/uncertain state is preserved and blocked. Delta specifications are not applied again blindly.
**Expected evidence:** Archive intent; before/after state; backup
**Status:** Passed
**Actual evidence:** `tests/test_archive.py` (completed-without-receipt reconciliation, mixed state block, not-applied retry, backup bytes + before/after)

## V1-A13 Portable business data
Version: v1; scope: Required.
**Steps:** Inspect manifest, result, approval, and shared summaries. Separate machine runtime from the shared Store.
**Pass criteria:** Use stable IDs, relative paths, and schema versions. Shared portable data contains no secrets or absolute checkout paths.
**Expected evidence:** Schema validation; portable refs
**Status:** Passed
**Actual evidence:** `tests/test_archive.py::test_portable_business_payloads` (approval/result schema, no absolute checkout paths or secrets in shared payloads); `docs/examples/`

## V1-A14 Installation and human takeover
Version: v1; scope: Required.
**Steps:** Install in a fresh directory. Follow the README through planning, run, approval, recovery, backup, and cleanup.
**Pass criteria:** No team component is required. Preserve a usable failure scene. Replay normal, repair, and abnormal-recovery paths at pinned versions.
**Expected evidence:** Release replays; backup/restore drill
**Status:** Passed (fixture-agent replays; live-agent install replay Blocked)
**Actual evidence:** `docs/evidence/05-release-local-v1.md` (fresh venv wheel install, runbook replay matrix); `docs/RUNBOOK.md`

## V2-A01 Authentication and project authorization
Version: v2; scope: Required.
**Steps:** Use two users/projects. Forge actor, read/approve another project, and violate separation-of-duty policy.
**Pass criteria:** Authentication supplies actor. Unauthorized actions fail. Clients cannot choose a trusted approval identity.
**Expected evidence:** Authentication and RBAC audit
**Status:** Not run
**Actual evidence:** None

## V2-A02 API idempotency and concurrent updates
Version: v2; scope: Required.
**Steps:** Retry the same key/payload; reuse the key with different payload; submit stale If-Match.
**Pass criteria:** Same request returns the same outcome. Payload/revision conflict returns 409. Only one execution is created.
**Expected evidence:** API fixtures; DB constraints
**Status:** Not run
**Actual evidence:** None

## V2-A03 Queue and outbox recovery
Version: v2; scope: Required.
**Steps:** Crash after DB commit before dispatch. Duplicate messages. Race cancellation with dispatch.
**Pass criteria:** Outbox retries delivery. Logical jobs deduplicate. Cancellation reaches a defined terminal state. Accepted work is not silently lost.
**Expected evidence:** Outbox and job records
**Status:** Not run
**Actual evidence:** None

## V2-A04 Orchestrator ownership and persistent state
Version: v2; scope: Required.
**Steps:** Resume concurrently. Lose an owner. Rebuild the runner with its pinned image and persistent workspace.
**Pass criteria:** Only one owner holds an execution. Original SDK state remains accessible. Fencing rejects the stale owner.
**Expected evidence:** Owner epochs; volume/image record
**Status:** Not run
**Actual evidence:** None

## V2-A05 Remote execution and data visibility
Version: v2; scope: Required.
**Steps:** Clone on another runner. Attempt out-of-scope writes, cross-project artifact reads, and credential access.
**Pass criteria:** Workers see only allowed repositories/context. Client machine paths are not remote paths. Object access respects project authorization.
**Expected evidence:** Mount, network, secret, and access tests
**Status:** Not run
**Actual evidence:** None

## V2-A06 Lost workers and late results
Version: v2; scope: Required.
**Steps:** Expire heartbeat, confirm termination, then create a new attempt. Submit a result from the old epoch.
**Pass criteria:** Old results are audit-only. They cannot overwrite current results or publish. Cancellation does not launch duplicate work.
**Expected evidence:** Lease and fencing timeline
**Status:** Not run
**Actual evidence:** None

## V2-A07 Team quotas and dependencies
Version: v2; scope: Required.
**Steps:** Submit multiple repo tasks from several users. Remove some capacity. Leave a cross-repo prerequisite unfinished.
**Pass criteria:** Global/project/repo quotas hold. Dispatch only ready tasks. Project fairness prevents starvation.
**Expected evidence:** Scheduler trace; ready batches
**Status:** Not run
**Actual evidence:** None

## V2-A08 Trusted approval and local history
Version: v2; scope: Required.
**Steps:** Approve on the platform, then change plan/code. Import local self_asserted approval. Try bypassing gate parameters.
**Pass criteria:** Stale approvals fail. Local records remain history. Server authorization and digest checks cannot be bypassed.
**Expected evidence:** Approval events; rejected requests
**Status:** Not run
**Actual evidence:** None

## V2-A09 Store concurrency and archive consistency
Version: v2; scope: Required.
**Steps:** Modify one capability from two changes. Kill after archive/push before recording. Cause a Git CAS conflict.
**Pass criteria:** Writes serialize per Store. Conflicts stop or re-evaluate. Never force push. Proven completed archive is not replayed.
**Expected evidence:** Writer lock; Git/receipt matrix
**Status:** Not run
**Actual evidence:** None

## V2-A10 Audit, budgets, and readable evidence
Version: v2; scope: Required.
**Steps:** Check budgets after restart. Read logs as an authorized reviewer. Let temporary artifact URLs expire.
**Pass criteria:** Budgets persist. Permanent refs/hashes still resolve. Logs omit secrets. Events trace authenticated actors.
**Expected evidence:** Metrics; artifact and audit checks
**Status:** Not run
**Actual evidence:** None

## V2-A11 Team pilot and partial merge
Version: v2; scope: Required.
**Steps:** Two users run normal, repair, and owner-rebuild paths across runners. Merge repo A while repo B fails.
**Pass criteria:** Collaboration works. Partial merge blocks archive. Human compensation and final re-verification are explicit.
**Expected evidence:** Pilot report; completion receipts
**Status:** Not run
**Actual evidence:** None

## V2-A12 Backup, restore, and rollback
Version: v2; scope: Required.
**Steps:** Restore DB, artifacts, and native workspace. Pause submit/archive. Roll back a failed upgrade to the old image.
**Pass criteria:** Reconcile before reopening dispatch. Measure RPO/RTO. Do not automatically undo code merges or historical archive.
**Expected evidence:** Restore and rollback drill
**Status:** Not run
**Actual evidence:** None

## MIG-A01 Portable bundle contents
Version: Migration; scope: Required.
**Steps:** Export completed/cancelled executions. Check the file inventory, sizes, paths, and hashes.
**Pass criteria:** Stable IDs and content match. No secrets, absolute paths, or live process handles. Reject path traversal and unsafe archive entries.
**Expected evidence:** Bundle manifest; hash report
**Status:** Not run
**Actual evidence:** None

## MIG-A02 Repeated import and identity conflict
Version: Migration; scope: Required.
**Steps:** Import one bundle twice. Reuse a UID with a different remote or content.
**Pass criteria:** Repeated import is idempotent. Identity/content conflicts are rejected rather than overwritten.
**Expected evidence:** Import receipts; identity mapping
**Status:** Not run
**Actual evidence:** None

## MIG-A03 History cannot grant team authorization
Version: Migration; scope: Required.
**Steps:** Import local approval and attempt to reuse it for a new team execution.
**Pass criteria:** Preserve read-only self_asserted provenance. The new execution needs authenticated team approval.
**Expected evidence:** Historical record; fresh team approval
**Status:** Not run
**Actual evidence:** None

## MIG-A04 No hot migration of active work
Version: Migration; scope: Required.
**Steps:** Try exporting running/paused work as executable state, then switch backend.
**Pass criteria:** Active runs never enter the team queue. Finish or cancel locally and create a new team execution.
**Expected evidence:** Export finding; new execution identity
**Status:** Not run
**Actual evidence:** None

## MIG-A05 Archived history and coexistence
Version: Migration; scope: Required.
**Steps:** Import an archived receipt and request archive again. Stop v2 and return to local use.
**Pass criteria:** History does not replay archive. Local history and new work remain usable. Only one backend advances a change at a time.
**Expected evidence:** Archive/import audit; rollback record
**Status:** Not run
**Actual evidence:** None

## OPT-A01 Two independent local repos in parallel
Version: Optional; scope: Optional.
**Steps:** Enable max_workers=2, fail one worker, and include a dependent task.
**Pass criteria:** Independent intervals overlap. Dependencies stay ordered. Each worktree has one writer and supports cancellation.
**Expected evidence:** Timing and lock trace
**Status:** Not run
**Actual evidence:** None

## OPT-A02 One Jenkins runner
Version: Optional; scope: Optional.
**Steps:** Change workspace mapping and run the same CLI. Preserve runtime before resuming.
**Pass criteria:** Machine mappings may change. Paused state survives. Execution still uses the local backend.
**Expected evidence:** Runner report
**Status:** Not run
**Actual evidence:** None

## OPT-A03 Web and API consistency
Version: Optional; scope: Optional.
**Steps:** Try the same stale approval and unauthorized operation through UI and API.
**Pass criteria:** Both reject it. UI has no authorization bypass or duplicate business state machine.
**Expected evidence:** UI/API test report
**Status:** Not run
**Actual evidence:** None
