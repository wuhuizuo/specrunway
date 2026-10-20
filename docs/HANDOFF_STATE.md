# Implementation state

Updated: 20 October 2026 (L02-L05 session).

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

`hub plan/run/approve/status/resume/recover/archive` behavior (change 03/04): manifest-driven planning artifacts, execution freeze/snapshot creation, agent launcher (Specify workflow + hub step), identity/ancestry/allowed-path verification, single-writer checkbox updates, integration matrix, code review pack, budgets/exhaustion, native resume/recover flow, explicit archive + completion policy verification, release README/replay. No live agent profile exercise yet.

## Current change

`03-deliver-two-repo-loop` (source tasks L06-L12 core loop) — not started.

## Exact next action

Execute `openspec/changes/03-deliver-two-repo-loop/tasks.md` in order: implement `hub plan` (create/refresh planning artifacts + machine validation gates), execution freeze (`manifest_digest`/`planning_digest`/`context_digest` + base `commit OIDs` into `snapshot.json` via L05 FileRunStore), `hub run` (Spec Kit workflow start with the hub custom step in the control checkout's Specify env, honoring frozen inputs and `repo_order`), identity/result verification against L04-/L05-probes, and two-repository end-to-end delivery with trusted test execution. Reuse L01 fixture mechanics — do not re-probe the compatibility gate.
