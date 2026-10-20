# Implementation state

Updated: 20 October 2026 (L06–L09 session).

## Completed preparation

- Exported the full English design and task/acceptance material from revision 2.
- Recorded the confirmed local-first scope, central Store/cross-repository requirement, and exclusion of Specstride.
- Prepared five ordered OpenSpec changes with requirements, designs, and unchecked tasks.
- Provided repository development-tool setup and a next-agent implementation prompt.

## Completed work: L01 (compatibility gate)

- Imported the handoff package into this repository (README merged, `.gitignore` merged from fragment, AGENTS.md/openspec/scripts/tooling/docs in place), and generated the OpenSpec ↔ OpenCode integration with `openspec init --tools opencode` (`.opencode/` commands + skills).
- Installed pinned OpenSpec (`@fission-ai/openspec@1.14.3` via `tooling/openspec/package.json`) and pinned Specify (`specify-cli 1.2.1` from `github/spec-kit@v1.2.1`, commit `9dca9bf42a031765ee5e5f2371137f2f26967e11`) into the repo-root `.venv`.
- Executed every L01 probe (Store routing/JSON, custom hub step install, gates/fan-out/fan-in/loop, resume-failed/paused/SIGINT/SIGKILL orphan) in a disposable fixture; pass decision recorded in `toolchain.lock.json` + `docs/evidence/L01/compatibility-report.md` + sanitized fixtures.
- Committed (`d4357f9`) and pushed `origin main`.

## Completed work: change 02 (L02-L05)

- Toolchain recorded: distribution `hub-cli==0.1.0` (setuptools, `src/` layout), console script `hub`, `requires-python >= 3.11`, runtime dep `PyYAML>=6.0`; dev tooling `pytest>=8` + `ruff>=0.4` (`.venv` editable install; reproducible via `pip install -e .[dev]`).
- L02: `hubcoord.cli` with `hub doctor` (envelope `hub/v1`, walk-up control-root detection, explicit `--root`, per-repo wiring findings, JSON + text output) and honest `not-implemented` stubs (exit 69) for plan/run/approve/status/resume/recover/archive mapped to owning OpenSpec changes. Business checkouts verified untouched (no tool init required).
- L03: `hubcoord.models` — manifest machine validation (IDs, tree/path traversal, unknown keys/profiles, task routing duplicates/gaps, acceptance coverage, forward-only dependencies with cycle rejection per repo_order + wiring cross-check, budget ranges, completion policies); `local.yaml` machine validation (`max_workers=1`, remote-identity parsing; `hubcoord.remotes` for `github:owner/repo`/https/ssh/scp identity ↔ origin URL matching); record validators for snapshot (manifest digest binding), untrusted result, self_asserted approval, operations (operation-key, intents, statuses); `json_digest` + `strip_checkbox_markers` for future planning digests.
- L04: `hubcoord.openspec_adapter` — typed argv wrappers (`shell=False`, cwd = explicit store path, `--store <id>`) for `store setup`, `new change`, `status`, `instructions apply`, `validate [--strict]`, `archive --yes`; real JSON contract keys enforced (missing-key/wrong-shape/root-routing → `OpenSpecProtocolError`); upstream error envelopes mapped to stable codes (`unknown_store`, `no_registered_stores`, `change-exists`, timeout, tool-missing); strict-validate exit-1-with-items-payload treated as a failure RESULT, not a command error.
- L05: `hubcoord.runstore.FileRunStore` — `fcntl` exclusive checkout lock (blocking deadline + non-blocking) with `LockTimeoutError`; atomic JSON writes (tmp + fsync + `os.replace`, verified with 200 KB replace); revision compare-and-swap state updates with immutable `execution_id`/`created_at` and corrupt/foreign state detection; active-owner record exactly one active execution per checkout (idempotent claim, conflict rejection, guarded release); effect-before-receipt operation intents (`pending → recorded | uncertain → reconciled`) with `[no-intent]`/`[operation-key-reuse]` guards and state-index mirroring.
- Verification: `pytest -q` → 119 passed (incl. 5 real-CLI integration tests against pinned OpenSpec 1.14.3 in disposable stores, locking/ownership/multiprocessing tests); `openspec validate --all --strict --json` → 5/5; `scripts/check_handoff.py` → passed. Commands/exit codes: `docs/evidence/02-build-local-foundation.md`.

## Not implemented

`hub run/status/resume/recover/archive` behavior (change 03 remaining / change 04): worktree-based repo execution loop wiring into a run command, single-writer checkbox updates, integration matrix + fan-in, code review pack, budgets/exhaustion, hub step bridge package, native resume/recover flow, explicit archive + completion policy verification, release README/replay. Live agent profile exercise deferred to release acceptance.

## Completed work: change 03 so far (L06 + L07 + L08)

- L06 task 1.1 done: `hubcoord.planning` — `hub plan` real: request-driven generation (proposal/design/tasks/spec deltas with `[Txxx]` routing labels), manual-plan acceptance, `crosscheck_task_routing`, `.hub/plans/<id>/{manifest.yaml,plan-summary.json}` landing.
- L07 task 2.1 done: `hubcoord.freezer` — planning/context digests (checkbox-normalized, rule-aware), argv-only base-OID resolution, machine-validated snapshots; `hubcoord.approvals` — self_asserted `hub approve` recomputing subject digests from frozen content, `require_gate` refusal points, staleness verification; `hubcoord.toolresolvers`.
- L08 task 3.1 done: `hubcoord.launcher` — `AgentProfile` with `{prompt_file}` argv template (real `primary-coding-agent` profile → `opencode run --auto --pure --file <prompt>`; measured opencode 1.18.33 flags), `launch_process` (argv list, `shell=False`, own process group via `start_new_session=True`), `run_agent` structured outcome (completed/failed/timeout/cancelled + exit/log paths), `kill_proc_group`/`cancel` group kills covering agent-spawned grandchildren.
- L08 task 3.1 done: `hubcoord.launcher` — `AgentProfile` with `{prompt_file}` argv template (real `primary-coding-agent` profile → `opencode run --auto --pure --file <prompt>`; measured opencode 1.18.33 flags), `launch_process` (argv list, `shell=False`, own process group via `start_new_session=True`), `run_agent` structured outcome (completed/failed/timeout/cancelled + exit/log paths), `kill_proc_group`/`cancel` group kills covering agent-spawned grandchildren.
- L09 task 4.1 done: `hubcoord.worktrees` — detached worktrees at frozen base OIDs with original-checkout preservation checks; `hubcoord.testprofiles` — trusted argv test runner producing runner receipts; `hubcoord.results` — `accept_result` gating identity/ancestry/allowed-paths/trusted-receipt/digest binding before result acceptance + `persist_result` into the run tree.
- Verification: `pytest -q` → 158 passed (9 new worktree/result tests incl. foreign-result and receipt-mismatch rejections; 8 launcher; 9 freeze/approval; 8 planning incl. real-CLI); `openspec validate --all --strict --json` → 5/5; `scripts/check_handoff.py` → passed. Details: `docs/evidence/03-deliver-two-repo-loop.md`.

## Current change

`03-deliver-two-repo-loop` (source tasks L06-L12 core loop) — L06/L07/L08/L09 complete; L10-L12 remaining.

## Exact next action

Execute `openspec/changes/03-deliver-two-repo-loop/tasks.md` in order: next is task 5.1 (L10) — package the `type: hub` Specify step bridge (one step package delegating to functions in the same package; standardized `output.data` envelope; installed imports verified against the pinned CLI), then L11 ordered two-repo workflow with gates/fan-in and `ready_for_review` boundary, then L12 bounded repair budgets.
