# Evidence: change 03 — L06 planning, L07 freeze/approvals, L08 agent launcher

Change: `03-deliver-two-repo-loop` source tasks L06 (task 1.1, V1-A04),
L07 (task 2.1, V1-A05), L08 (task 3.1, V1-A06).

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
