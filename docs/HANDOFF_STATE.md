# Implementation state

Updated: 20 October 2026 (L01-L16 complete; integration verification closed; changes archived).

## Completed preparation

- Exported the full English design and task/acceptance material from revision 2.
- Recorded the confirmed local-first scope, central Store/cross-repository requirement, and exclusion of Specstride.
- Prepared five ordered OpenSpec changes with requirements, designs, and unchecked tasks.
- Provided repository development-tool setup and a next-agent implementation prompt.

## Completed work: L01 (compatibility gate)

- Imported the handoff package into this repository (README merged, `.gitignore` merged from fragment, AGENTS.md/openspec/scripts/tooling/docs in place), and generated the OpenSpec ↔ OpenCode integration with `openspec init --tools opencode` (`.opencode/` commands + skills).
- Installed pinned OpenSpec (`@fission-ai/openspec@1.14.3` via `tooling/openspec/package.json`) and pinned Specify (`specify-cli 1.2.1` from `github/spec-kit@v1.2.1`, commit `9dca9bf42a031765ee5e5f2371137f2f26967e11`) into the repo-root `.venv`.
- Executed every L01 probe (Store routing/JSON, custom specrunway step install, gates/fan-out/fan-in/loop, resume-failed/paused/SIGINT/SIGKILL orphan) in a disposable fixture; pass decision recorded in `toolchain.lock.json` + `docs/evidence/L01/compatibility-report.md` + sanitized fixtures.
- Committed (`d4357f9`) and pushed `origin main`.

## Completed work: change 02 (L02-L05)

- Toolchain recorded: distribution `specrunway-cli==0.1.0` (setuptools, `src/` layout), console script `specrunway`, `requires-python >= 3.11`, runtime dep `PyYAML>=6.0`; dev tooling `pytest>=8` + `ruff>=0.4` (`.venv` editable install; reproducible via `pip install -e .[dev]`).
- L02: `specrunway.cli` with `specrunway doctor` (envelope `specrunway/v1`, walk-up control-root detection, explicit `--root`, per-repo wiring findings, JSON + text output) and honest `not-implemented` stubs (exit 69) for plan/run/approve/status/resume/recover/archive mapped to owning OpenSpec changes. Business checkouts verified untouched (no tool init required).
- L03: `specrunway.models` — manifest machine validation (IDs, tree/path traversal, unknown keys/profiles, task routing duplicates/gaps, acceptance coverage, forward-only dependencies with cycle rejection per repo_order + wiring cross-check, budget ranges, completion policies); `local.yaml` machine validation (`max_workers=1`, remote-identity parsing; `specrunway.remotes` for `github:owner/repo`/https/ssh/scp identity ↔ origin URL matching); record validators for snapshot (manifest digest binding), untrusted result, self_asserted approval, operations (operation-key, intents, statuses); `json_digest` + `strip_checkbox_markers` for future planning digests.
- L04: `specrunway.openspec_adapter` — typed argv wrappers (`shell=False`, cwd = explicit store path, `--store <id>`) for `store setup`, `new change`, `status`, `instructions apply`, `validate [--strict]`, `archive --yes`; real JSON contract keys enforced (missing-key/wrong-shape/root-routing → `OpenSpecProtocolError`); upstream error envelopes mapped to stable codes (`unknown_store`, `no_registered_stores`, `change-exists`, timeout, tool-missing); strict-validate exit-1-with-items-payload treated as a failure RESULT, not a command error.
- L05: `specrunway.runstore.FileRunStore` — `fcntl` exclusive checkout lock (blocking deadline + non-blocking) with `LockTimeoutError`; atomic JSON writes (tmp + fsync + `os.replace`, verified with 200 KB replace); revision compare-and-swap state updates with immutable `execution_id`/`created_at` and corrupt/foreign state detection; active-owner record exactly one active execution per checkout (idempotent claim, conflict rejection, guarded release); effect-before-receipt operation intents (`pending → recorded | uncertain → reconciled`) with `[no-intent]`/`[operation-key-reuse]` guards and state-index mirroring.
- Verification: `pytest -q` → 119 passed (incl. 5 real-CLI integration tests against pinned OpenSpec 1.14.3 in disposable stores, locking/ownership/multiprocessing tests); `openspec validate --all --strict --json` → 5/5; `scripts/check_handoff.py` → passed. Commands/exit codes: `docs/evidence/02-build-local-foundation.md`.

## Not implemented

`specrunway run/status/resume/recover/archive` behavior (change 03 remaining / change 04): the `specrunway run` command that starts/owns Specify workflow runs (bridge exists; workflow YAML generation + gate verdict supply pending), single-writer checkbox updates after accepted results, integration combined matrix, code review pack, budgets/exhaustion enforcement + native resume/recover flow, explicit archive + completion policy verification, release README/replay. Live agent profile exercise deferred to release acceptance.

## Completed work: change 03 so far (L06 + L07 + L08)

- L06 task 1.1 done: `specrunway.planning` — `specrunway plan` real: request-driven generation (proposal/design/tasks/spec deltas with `[Txxx]` routing labels), manual-plan acceptance, `crosscheck_task_routing`, `.specrunway/plans/<id>/{manifest.yaml,plan-summary.json}` landing.
- L07 task 2.1 done: `specrunway.freezer` — planning/context digests (checkbox-normalized, rule-aware), argv-only base-OID resolution, machine-validated snapshots; `specrunway.approvals` — self_asserted `specrunway approve` recomputing subject digests from frozen content, `require_gate` refusal points, staleness verification; `specrunway.toolresolvers`.
- L08 task 3.1 done: `specrunway.launcher` — `AgentProfile` with `{prompt_file}` argv template (real `primary-coding-agent` profile → `opencode run --auto --pure --file <prompt>`; measured opencode 1.18.33 flags), `launch_process` (argv list, `shell=False`, own process group via `start_new_session=True`), `run_agent` structured outcome (completed/failed/timeout/cancelled + exit/log paths), `kill_proc_group`/`cancel` group kills covering agent-spawned grandchildren.
- L08 task 3.1 done: `specrunway.launcher` — `AgentProfile` with `{prompt_file}` argv template (real `primary-coding-agent` profile → `opencode run --auto --pure --file <prompt>`; measured opencode 1.18.33 flags), `launch_process` (argv list, `shell=False`, own process group via `start_new_session=True`), `run_agent` structured outcome (completed/failed/timeout/cancelled + exit/log paths), `kill_proc_group`/`cancel` group kills covering agent-spawned grandchildren.
- L09 task 4.1 done: `specrunway.worktrees` — detached worktrees at frozen base OIDs with original-checkout preservation checks; `specrunway.testprofiles` — trusted argv test runner producing runner receipts; `specrunway.results` — `accept_result` gating identity/ancestry/allowed-paths/trusted-receipt/digest binding before result acceptance + `persist_result` into the run tree.
- L16 change 06 done: frozen integration profile (control `integration_profiles`), combined-matrix execution (`SPECRUNWAY_MATRIX`), `integration-round` workflow step with feedback-driven bounded repair, persisted `integration_repairs`/`integration_rounds`, and completion guards (`integration-required`/`failed`/`stale`). Verified with 7 integration tests + real-CLI runner flow; full suite 194 passed.
- Live-agent release replay done (after L15): real `opencode` 1.18.33 / `deepseek-flash` on a disposable two-repo fixture — plan gate, ordered repo-a→repo-b, accepted results, implementation gate, `ready_for_review`, merged commits, explicit `merged_commits` archive with backup. Fixed defects found only in the live path: `--file` array argv order, `AgentOutcome.reason`, prompt trusted-command/result contract, archive reconciliation of `uncertain` intents. A02/A06/A14 live sub-cases now Passed; no live-agent blocker remains.
- L15 tasks 1.1-1.3 done: v1 release replays. Fresh venv install from source and from `specrunway-0.1.0-py3-none-any.whl`; `specrunway doctor` exit 0 on a minimal wired control checkout; `docs/RUNBOOK.md` written; `docs/evidence/05-release-local-v1.md` records the install log, runbook replay matrix, acceptance matrix V1-A01..A14, the live-agent blocker, and known limitations. `docs/ACCEPTANCE.md` statuses updated: A01-A14 Passed except the live-agent sub-cases of A02/A06/A14 (Blocked: no model credentials in the environment).
- L13 task 1.1 done: `specrunway/recovery.py` (`execution_status`, `resume_execution` with live-plan drift refusal + pending-gate receipt check + native resume, `recover_execution` preserving an orphan running native run and starting a new one under the same execution, `reusable_result` evidence-checked receipt reuse); real `specrunway status`/`resume`/`recover`. Verified: 6 recovery tests incl. stale plan, evidence conflict, orphan dead-vs-live owner, plus `specrunway resume` in the real two-repo loop.
- L14 tasks 2.1/2.2 done: `specrunway/archive.py` explicit preflight (ready phase, accepted+verified results, all mapped checkboxes, approval binding, fresh trusted tests), `merged_commits` merge-ancestry enforcement vs explicit `validated_commits` confirmation, change-dir backup with before/after digests, intent/receipt around `openspec archive`, mixed/uncertain outcome blocking, and path-based reconciliation that never re-applies deltas. Verified with 8 tests against the real pinned OpenSpec CLI + registered disposable store.
- L12 task 7.1 done: manifest budgets enforced (`repo_max_attempts`, `integration_max_repairs`, `total_minutes`), `verify-round` persists verification rows, new `repair-round` step re-attempts failing repos with prior-feedback prompts and stops on `budget-exhausted`/`no-progress` (phase `blocked`), `complete` refuses failed verification. Verified with fake-agent failure scenarios, persistent counters after a fresh store handle, and 171 passing tests.
- L11 task 6.1 done: `specrunway/runner.py` (freeze → native workflow → gate-pause → receipt-checked `--continue` → `ready_for_review`), `bridge/workflow.py` (ordered workflow generation with native plan/implementation gates), `checkboxes.py` + bridge `accept-tasks` (single-writer tasks.md acceptance with op receipts), real `specrunway run` CLI. Verified end-to-end with the pinned specify CLI and a deterministic fake agent shadowing `opencode`: plan gate paused, `specrunway approve --kind plan`, ordered repo-a → repo-b fan-out (repo-b prompt carried repo-a's accepted head), tasks.md flipped, implementation gate paused, approval bound the accepted results tree, `--continue` completed at `ready_for_review`, original checkouts untouched. Also fixed a latent L10 defect: `run-repo` called nonexistent module-level runstore helpers.
- L10 task 5.1 done: `specrunway.bridge` — production `type: specrunway` step (prepare / run-repo / verify-round / collect-summary / gate-check / complete actions with the standardized envelope); `bridge/prompt.py` bounded prompt builder; `tooling/specrunwaystep` install shim delegating to the same package. Verified end-to-end with the pinned specify-cli 1.2.1: step install + real workflow run finished `status: completed` and the coordinator phase reached `ready_for_review`.
- Verification: `pytest -q` → 163 passed (5 bridge incl. pinned-CLI end-to-end; 9 worktree/result; 8 launcher; 9 freeze/approval; 8 planning); `openspec validate --all --strict --json` → 5/5; `scripts/check_handoff.py` → passed. Details: `docs/evidence/03-deliver-two-repo-loop.md`.

## Current change

`05-release-local-v1` — L15 complete. All five OpenSpec changes (L01-L15) are implemented and validated.

## Repository state

- All five development changes are archived under
  `openspec/changes/archive/2026-10-20-*`; their deltas are applied to the
  baseline under `openspec/specs/`.
- `README.md` now describes the implemented SpecRunway product and points to
  `docs/RUNBOOK.md`; the pre-archive handoff instructions are historical.
- `scripts/check_handoff.py` covers both active and archived changes (active
  may be zero after archive) and still asserts L01-L15 coverage.

## Exact next action

v1 implementation (L01-L16), live-agent acceptance, docs, and all development-change archives are complete. Remaining work is publication only: tag `v0.1.0` / GitHub Release (awaiting explicit approval) and any v2 work, which stays deferred. No further v1 code tasks are planned.
