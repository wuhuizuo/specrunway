# Implementation state

Updated: 20 October 2026 (L06 session).

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

`hub run/approve/status/resume/recover/archive` behavior (change 03 remaining / change 04): execution freeze/snapshot creation, agent launcher (Specify workflow + hub step), identity/ancestry/allowed-path verification, single-writer checkbox updates, integration matrix, code review pack, budgets/exhaustion, native resume/recover flow, explicit archive + completion policy verification, release README/replay. No live agent profile exercise yet.

## Completed work: change 03 so far (L06)

- L06 task 1.1 done: `hubcoord.planning` — `hub plan` is now real (no longer a stub): generation path (request-driven scaffolding of proposal/design/tasks/spec deltas per repo with `[Txxx]` routing labels), manual-plan acceptance path (complete change + deterministic validated manifest from labeled tasks), `crosscheck_task_routing` exact-match gate, `.hub/plans/<change_id>/{manifest.yaml,plan-summary.json}` landing; `openspec_adapter.status()` now returns `change_root`.
- Mismatch/wrong-store/incomplete/new-without-request rejections verified live (task-routing, store-unknown, plan-incomplete, plan-request-required); all exit 1 with stable codes; success exit 0.
- Verification: `pytest -q` → 131 passed (8 new planning tests incl. 4 real-CLI against pinned OpenSpec 1.14.3); `openspec validate --all --strict --json` → 5/5; `scripts/check_handoff.py` → passed. Details: `docs/evidence/03-deliver-two-repo-loop.md`.

## Current change

`03-deliver-two-repo-loop` (source tasks L06-L12 core loop) — L06 complete; L07-L12 remaining.

## Exact next action

Execute `openspec/changes/03-deliver-two-repo-loop/tasks.md` in order: next is task 2.1 (L07) — freeze planning/context/manifest content + per-repo base commit OIDs into `snapshot.json` with digests via `json_digest` + `strip_checkbox_markers` (checkbox-only invariance), and implement `hub approve` recording self_asserted approvals bound to the frozen subject digests. Then L08 agent launcher, L09 worktrees/trusted tests, L10 hub step package, L11 two-repo workflow, L12 budgets. Reuse L01/L06 fixture mechanics; do not re-probe the compatibility gate.
