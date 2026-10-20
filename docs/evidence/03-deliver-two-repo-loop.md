# Evidence: change 03 — L06 planning, L07 freeze/approvals, L08 launcher,
# L09 worktrees/tests/results, L10 hub step bridge

Change: `03-deliver-two-repo-loop` source tasks L06 (task 1.1, V1-A04),
L07 (task 2.1, V1-A05), L08 (task 3.1, V1-A06), L09 (task 4.1, V1-A06 + V1-A07),
L10 (task 5.1, V1-A01).

## What was built

- `src/hubcoord/planning.py`
  - `plan()` — central planning entry: loads `local.yaml` (relative paths resolved),
    enforces `--store` against the configured store id, runs `openspec store setup`,
    then generation or manual planned loading.
  - Generation path (new change or existing incomplete one + `--request`):
    `openspec new change`, then request-driven scaffolding of
    `proposal.md` (Why/What Changes sections), `design.md` (Approach), `tasks.md`
    (per-repo `## Repo:` sections with `- [ ] r.s [Txxx] description` lines from the
    binding manifest routing), and per-repo capability deltas
    `specs/<repo_id>-delivery/spec.md` with RFC2119 requirement + scenario
    (`Spec-Head/Spec-Title/Spec-Body/Spec-When/Spec-Then` request block overrides).
  - Manual plan path (existing complete change): accepted with routing derived via
    `extract_task_ids(tasks.md)` + deterministic `_manual_manifest`
    (one repo per labeled task group, forward-only dependencies, acceptance
    covering every task id), validated by `validate_manifest`.
  - `crosscheck_task_routing()` — declared-vs-found routing must match exactly
    (missing/undeclared task ids reject the plan as `task-routing`).
  - Final artifacts + summary land in the control repo under
    `.hub/plans/<change_id>/{manifest.yaml,plan-summary.json}` via
    `atomic_write_json`.
- `src/hubcoord/openspec_adapter.py` — `status()` now also returns
  `change_root` (required by the manual-plan path).
- `src/hubcoord/cli.py` — real `hub plan` command (replaces the stub):
  positional change id, `--store/--request/--manifest/--root/--json`,
  hub/v1 envelope on success, `[{code}] message` errors, exit 1 on failure,
  exit 1 envelope (not crash) for missing control root.
- Request-embedded task text format: `T001: description` and `T088 ; desc` are
  parsed by `parse_task_texts` (`T-id[:;] text` lines).

## Verified rules (live CLI, pinned OpenSpec 1.14.3)

- `hub plan gen-change --request --manifest` created a complete change set:
  `proposal.md, design.md, tasks.md, specs/repo-a-delivery/spec.md, specs/repo-b-delivery/spec.md`.
- `tasks.md` rendering preserved manifest routing exactly with `[T001]/[T002]`
  labels; `openspec instructions apply` observed
  `progress total 2 / complete 0 / remaining 2`.
- `openspec validate gen-change --strict` exit 0 with all items valid.
- Manual-plan flow accepted a fully hand-written change and produced a
  validated manifest + summary (routing repo-a[T101], repo-b[T102],
  acceptance ids covering both).
- Rejections observed: `task-routing` (manifest missing T002 accepts T102),
  `store-unknown` (--store mismatch), `plan-incomplete` (no artifacts),
  `plan-request-required`, `test-profile` (non-empty string rule).
- Exit codes: all failures exit 1; all successes exit 0; no crash surfaces.

## Commands and results

```
.venv/bin/hub plan add-global-rate-limit --store lt02store --request /tmp/request.txt --manifest /tmp/l06-manifest.yaml --json
  -> exit 0, data.task_ids [T001, T002], planning_complete true, generated 5 files
openspec validate add-global-rate-limit --store lt02store --strict --json -> exit 0 (all items valid)
openspec instructions apply --change add-global-rate-limit --store lt02store -> progress {total:2, complete:0, remaining:2}
openspec validate --all --strict --json -> all 5 changes valid
python3 scripts/check_handoff.py -> {"result": "passed"} (15 source tasks, 23 checkboxes)
.venv/bin/python -m pytest -q -> 131 passed
```

## Test coverage added (`tests/test_planning.py`, 8 tests)

Real-CLI: generation path existence/shape, manual acceptance path with
manifest wiring, routing-mismatch rejection, incomplete-change rejection,
unknown-wrong-store rejection. Unit: extract/render/crosscheck helpers,
request task-text format.

## L07 freeze + approvals (task 2.1)

Built:

- `src/hubcoord/freezer.py` — context freeze:
  - `compute_planning_digest(change_path, manifest)`: canonical
    `[relpath, text]` pairs over `proposal.md`, `design.md`, `tasks.md`
    (checkbox markers stripped with `strip_checkbox_markers`), and all
    `specs/**/*.md` deltas, plus the manifest routing dict — digested via
    `json_digest`.
  - `compute_context_digest`: planning content plus per-repo rule files
    (`AGENTS.md`, `CLAUDE.md` when present at repo roots).
  - `resolve_base_oid(repo_path, base_ref)`: argv-only `git --no-pager -C
    <path> rev-parse --verify <ref>`; missing `.git` → `repo-not-git`;
    unresolvable ref → `base-ref-unknown`.
  - `freeze_execution(...)`: builds snapshot (manifest embedded +
    `manifest_digest`, `planning_digest`, `context_digest`, per-repo
    `base_ref`/`base_oid`/`remote_identity`, tools version block, RFC 3339
    `created_at`) and runs `validate_snapshot` (hub/v1, machine-checked
    digest binding).
  - `is_snapshot_immutable(existing, fresh)`: equality ignoring
    `created_at` — snapshot content immutability for re-freeze.
- `src/hubcoord/approvals.py` — local approvals:
  - `record_approval(store, execution_id, kind, snapshot, actor, decision,
    result)`: recomputes the subject digest from FROZEN content (never from
    caller input) — `plan` → snapshot `planning_digest`; `implementation` →
    validated `result.json` `result_digest`; writes
    `runs/<exec>/approvals/<kind>.json` via `atomic_write_json` and mirrors
    into `state.json.approvals` with CAS. v1 hard-codes
    `auth_level: self_asserted` (validator refuses `authenticated`).
  - `require_gate(store, execution_id, kind[, expected_subject_digest])`:
    the gate-advance refusal point — refuses when approval file missing
    (`no-approval` — the injected-verdict refusal), the recorded decision is
    reject (`approval-rejected`), or the recorded `subject_digest` does not
    bind the frozen content or the caller-claimed value
    (`approval-mismatch`).
  - `verify_frozen_approval(...)`: recompute-from-frozen-content binding
    check; raises `approval-stale` when the live input digest differs from
    the stored approval.
- `src/hubcoord/toolresolvers.py` — shared dev-convention binary resolution
  (openspec + specify; explicit → dev hints → PATH); `planning` refactored
  onto it.
- `hub approve` CLI (real): `--execution --kind {plan,implementation}
  --actor [--decision]` — records the operator's own confirmation bound to
  the recomputed digest; refuses (exit 1) with a stable code when the
  snapshot is missing (`snapshot-missing`) or an implementation approval
  lacks a validated `result.json` (`result-required`).

Verified behaviors (tests in `tests/test_freeze_approvals.py`, 9):

1. Snapshot binds each digest to its content (`manifest_digest ==
   json_digest(embedded manifest)`; recomputed planning/context digests
   match snapshot fields; base_oids 40-hex; tools block frozen).
2. Snapshot immutability: `created_at`-only change is immutably equal;
   a digest change is not.
3. Checkbox normalization: toggling `- [ ]` → `- [x]` leaves the planning
   digest unchanged; changing a task description changes it.
4. Rule drift: adding `AGENTS.md` to repo-b changes the context digest.
5. Approval receipt: `record_approval` writes the file + state mirror;
   `require_gate` passes with the receipt.
6. Injected verdict refusal: absent receipt → `no-approval`; recorded
   reject → `approval-rejected`; caller-claimed foreign subject →
   `approval-mismatch`.
7. Changed approved input: after a task-text edit the recomputed planning
   digest differs from the stored approval → `approval-stale`; before the
   edit the verification passes.
8. Implementation approval binds the validated result's `result_digest`;
   the gate then requires exactly that digest.
9. `hub approve` CLI records the self_asserted receipt (JSON envelope
   shows digest + auth_level) and refuses implementation approval without
   a result (exit 1, `result-required`).

Full suite at L07: `pytest -q` → 141 passed.

## L08 agent launcher (task 3.1)

Built `src/hubcoord/launcher.py`:

- `AgentProfile` — frozen argv template with a `{prompt_file}` placeholder;
  `resolved(prompt_file)` substitutes the absolute prompt path. The real
  packaged profile `primary-coding-agent` drives the actually used coding
  agent CLI (measured here: opencode 1.18.33):
  `opencode run --auto --pure --file {prompt_file} "Execute the attached
  prompt file exactly; do not ask interactive questions."` — verified flags
  via `opencode run --help` in this environment (non-interactive,
  file-attached run).
- `launch_process(argv, cwd, log_path)` — argv list only, `shell=False`,
  explicit `cwd`, output redirected to a single sanitized log file
  (`agent.log` under the run artifacts dir), `start_new_session=True` so the
  agent owns a killable process group. Resolves the executable on PATH or
  absolute; stable errors `agent-binary-missing`, `cwd-missing`,
  `prompt-file-missing` (argv never becomes shell text).
- `run_agent(...)` — synchronous launch returning a structured
  `AgentOutcome` (`status` ∈ completed/failed/timeout/cancelled,
  `exit_code`, `duration_seconds`, `log_path`, `reason`); timeout kills the
  process group (SIGTERM → grace → SIGKILL) and reports `timeout`.
- `kill_proc_group` / `cancel` — operator cancellation takes down agent
  children AND grandchildren spawned by the agent (process-group kill).

Verified behaviors (`tests/test_launcher.py`, 8 tests, fake agents):

1. Fake agent completes: structured outcome `completed`/exit 0, log file
   written, prompt file content seen by the agent, cwd honored.
2. Failing agent: `failed`, exit 3, stderr captured in the log.
3. Timeout: `timeout` status, process killed, wall-clock bounded.
4. Process-group control: agent spawning a `sleep 120` grandchild dies
   together with its child on group kill; `cancel()` then reports
   `cancelled`.
5. Cancel of a running launch stops it (`poll()` non-None).
6. Stable rejections: missing prompt/cwd/binary.
7. Profile registry: unknown profile → `profile-unknown`; real profile
   resolves `{prompt_file}` fully (no placeholder left).
8. No shell interpolation: argv list + `shell=False` asserted against a
   real execution.

Full suite at L08: `pytest -q` → 149 passed.

## L09 worktrees + trusted tests + result validation (task 4.1)

Built:

- `src/hubcoord/worktrees.py` — `create_worktree(repo, base_oid,
  execution_dir, repo_id)` via argv-only `git worktree add --detach
  <target> <base_oid>` (stable errors `repo-not-git`, `worktree-exists`,
  `worktree-create`); `original_status`/`assert_original_preserved`
  (porcelain snapshot equality across operations), `commit_all`,
  `head_oid`, `is_ancestor` (merge-base --is-ancestor).
- `src/hubcoord/testprofiles.py` — trusted test runner: registry
  `TEST_PROFILES` with explicit argv (unit → `python -m pytest -q`,
  `python` replaced by the trusted interpreter); `resolve_test_profile`
  (`unknown-profile`), `run_test_command` (argv list, shell=False, explicit
  cwd, stdout/stderr to a runner-produced log, timeout → status `error`)
  returning a runner receipt {status passed/failed/error, exit_code,
  command, started/finished, duration, log_path, reason}.
- `src/hubcoord/results.py` — independent result validation
  (`accept_result`): shape via `validate_result`; identity binding
  (`execution-mismatch`, `repo-mismatch`, `repo-not-in-manifest`,
  `task-unmapped`); commit binding (`base-mismatch`,
  `head-not-descendant` incl. nonexistent heads; `ancestry-check-failed`);
  changed-path policy (`path-unsafe` at shape level, `path-not-allowed`
  against manifest `allowed_paths` with normalized prefix tests); trusted
  evidence (`receipt-missing`, `receipt-mismatch` agent claim vs runner
  receipt, `receipt-command-mismatch`); payload binding
  (`digest-mismatch` via `compute_result_digest` over the record minus
  `result_digest`). `persist_result` copies the accepted record into the
  immutable run tree `results/<repo>/<attempt>/result.json`.

Verified behaviors (`tests/test_worktrees_results.py`, 9 tests):

1. Worktree detached exactly at the frozen base OID; original checkout
   with an untracked uncommitted file stays byte-identical per
   `status --porcelain` before/after.
2. Second worktree creation at the same path refused (`worktree-exists`).
3. Accepted path: committed change in the worktree, runner receipt
   passed, result.json validated end-to-end, persisted copy readable with
   the head commit inside.
4. Foreign result with a nonexistent/foreign head → `head-not-descendant`.
5. Wrong execution_id → `execution-mismatch`; stray extra task id →
   `task-unmapped`.
6. Path outside allowed_paths → `path-not-allowed`; `../secret` caught by
   the shape validator (must be a relative normed path).
7. Agent claims passed with no receipt → `receipt-missing`; claims passed
   while the receipt recorded failed → `receipt-mismatch`.
8. Tampered result body → `digest-mismatch`.
9. Trusted runner runs REAL pytest in a fixture project: passing suite →
   `passed` receipt; failing test → `failed` receipt; unknown profile →
   `unknown-profile`.

Full suite at L09: `pytest -q` → 158 passed.

## L10 production hub step bridge (task 5.1)

Built:

- `src/hubcoord/bridge/` — the production `type: hub` step package:
  - `__init__.py`: `HubStep(StepBase)` with `type_key: hub`; resolves
    `{{ expressions }}` through the public
    `specify_cli.workflows.expressions.evaluate_expression`; maps
    `HubActionError` to `StepStatus.FAILED` with the error envelope; never
    touches private engine state.
  - `actions.py`: standardized envelope (`api_version/action/ok/store_uid/
    change_uid/execution_id/data/evidence/warnings` + `error` when failed)
    and the dispatch of production actions:
    - `prepare` — frozen snapshot in, ordered repo rows with base OID,
      task routing, allowed paths, test profiles, phase.
    - `run-repo` — the synchronous per-repo engine: idempotent worktree
      creation from the frozen base OID; bounded prompt assembly
      (`bridge/prompt.py`: tasks, allowed paths, approved plan bytes,
      capability delta, existing repo rule files, dependency accepted
      results, prior-attempt feedback); operation intent FIRST
      (`<exec>:repo:<id>:<attempt>:<input_digest>`), agent launch via
      `launcher.run_agent`, trusted tests via `testprofiles`, receipt
      persisted under `tests_receipts/<repo>/<attempt>.json`, result
      validated via `results.accept_result`, persisted copy +
      operation receipt, state budgets/results update.
    - `verify-round` — re-runs trusted tests per repo worktree and
      returns `needs_repair`.
    - `collect-summary` — fan-in of accepted results + implementation
      approval state.
    - `gate-check` — approval receipt presence check (the injected-
      verdict refusal at gate advance).
    - `complete` — sets the run state phase `ready_for_review`
      (never archives).
  - `prompt.py`: bounded prompt builder (no shell text ever).
- `tooling/hubstep/{step.yml,__init__.py}` — the install shim: Specify
  loads this `__init__.py` from the control checkout's
  `.specify/workflows/steps/hub/`, and it immediately imports
  `hubcoord.bridge` (single-package delegation; no duplicated engine).

Verified against the pinned Specify CLI (specify-cli 1.2.1, real run):

1. `specify init --here --force --non-interactive --ignore-agent-tools`
   in a disposable control; `specify workflow step add hub --dev
   tooling/hubstep` (exit 0).
2. A real bridge-probe workflow (`prepare` → `gate` → `complete`) ran
   through `specify workflow run <wf> --json --input execution=...
   --input control_root=... --input plan_verdict=approve` → exit 0,
   `status: completed`; the hub envelope data from the installed step
   landed in the coordinator run state: `phase == ready_for_review`.
3. Direct action coverage (`tests/test_bridge_step.py`, 5 tests):
   prepare ordering/base OID; gate-check refusal (`no-approval`) then
   acceptance after self_asserted receipt; collect-summary aggregation
   (passed rows + implementation approval); complete →
   `ready_for_review` non-archive; the installed-CLI end-to-end test.

Full suite at L10: `pytest -q` → 163 passed.

## L11 ordered two-repository execution (task 6.1)

Built:

- `src/hubcoord/runner.py` — the execution controller:
  - `prepare_execution` validates the accepted plan manifest, then freezes
    plan/rule/context bytes, base OIDs, and tool versions into
    `snapshot.json` while holding the checkout lock; it claims the
    active-owner record and sets `awaiting_plan_review`.
  - `start_execution` refuses an uninitialized control checkout, writes the
    generated workflow under `.specify/workflows/run-<id8>.yaml`, and runs
    `specify workflow run <wf> --json` (argv only, explicit cwd). A native
    gate pause is a normal outcome: `pending_gate=plan|implementation`
    and the matching public phase are persisted.
  - `continue_execution` requires the matching approval receipt through
    `approvals.require_gate` BEFORE supplying a native gate verdict; it
    resumes the stored `native_run_id` with `--input <verdict_input>=approve`.
  - No auto-archive: a completed workflow ends at `ready_for_review`.
- `src/hubcoord/bridge/workflow.py` — deterministic workflow generation:
  `prepare` → native `plan-gate` → ordered `fan-out` of `run-repo`
  (`max_concurrency: 1`, items = frozen `repo_order`) → `fan-in` →
  `verify-round` → `accept-tasks` → native `implementation-gate` →
  `complete`. Only hub steps carry business rules.
- `src/hubcoord/checkboxes.py` + bridge `accept-tasks` action — the single
  coordinator writer that flips only the mapped `- [ ]` lines to `- [x]`
  in the Store change `tasks.md` (intent first, receipt with before/after
  digests, idempotent by content digest, `task-unmapped` for unknown IDs).
- `bridge/prompt.py` now states the `execution_id` and `attempt` so an
  agent can produce an identity-correct `result.json`.
- `hub run` CLI: `--change` freezes a new execution; `--execution ... --continue`
  advances past the pending gate; unknown/unsupported combinations return
  stable `hub/v1` errors.

Defect found and fixed while wiring the real loop:

- L10's `run-repo`/`accept-tasks` imported hypothetical module-level
  `runstore` helpers (`write_intent`, `record_receipt`,
  `mark_uncertain`). L10's tests paused before any repo attempt, so the
  ImportError was latent. The bridge now calls the real
  `FileRunStore` methods; `accept-tasks` adds intent-first ops.

Verified (real pinned Specify CLI 1.2.1 + real git fixtures; fake agent
shadowing `opencode` with the identical argv shape):

1. `pytest tests/test_runner_flow.py -q` → 3 passed
   (`test_two_repo_loop_reaches_ready_for_review` is the L11 loop):
   - `hub run --change demo` → exit 0, native `status: paused`,
     `current_step_id: plan-gate`, phase `awaiting_plan_review`;
     `tasks.md` still unchecked.
   - `hub approve --kind plan` → exit 0, self_asserted receipt bound to
     the frozen `planning_digest`.
   - `hub run --execution <id> --continue` → exit 0, paused at
     `implementation-gate`; both repo results accepted
     (`repo-a`, `repo-b`), phase `awaiting_implementation_review`,
     `T001` checkbox flipped.
   - Downstream context: `prompts/repo-b-1.md` contains
     `repo-a: <accepted head commit>` + digest, so repo-b consumed the
     first repo's accepted commit before editing.
   - `hub approve --kind implementation` binds
     `subject_digest_for_results` (accepted results tree), then
     `hub run --continue` → native `status: completed`, phase
     `ready_for_review`, both task checkboxes checked, and neither
     original checkout gained the agent commit (`git log` unchanged).
   - Refusal: `--continue` without a receipt → exit 1 (`no-approval`),
     no native advance.
2. Full suite: `pytest -q` → 166 passed.
3. Lint: `ruff check src tests` → clean.

Acceptance linkage: V1-A02 (standalone local use, business checkouts keep
only the intended worktree changes), V1-A09 (ordered two-repo execution
with downstream consumption of the first accepted commit). Full V1-A02
release closure still requires the live-agent run recorded in the release
evidence.
