# L01 Upstream compatibility report

Scope change: `01-verify-upstream-contracts` (source task L01). Date: 2026-10-19.
Decision: **pass** — all mandatory probes at the pinned releases produced real, recorded
outcomes. Production code (L02+) may build against the measured contracts below.
This report proves tool contracts only; it is not an implementation- or
acceptance-completeness claim. Machine-private details were sanitized
(``<tmp>``/``<home>`` placeholders); raw probe logs stayed in disposable scratch.

## 1 Pinned identities (task 1.1)

| Tool | Identity measured | Provenance |
| --- | --- | --- |
| OpenSpec CLI | `1.14.3` | npm `@fission-ai/openspec@1.14.3`, pinned in `tooling/openspec/package.json`; lock entry integrity `sha512-ALFW1d5b…YfG==` |
| Specify CLI | `1.2.1` | `specify-cli @ git+https://github.com/github/spec-kit.git@v1.2.1`; `direct_url.json` records commit `9dca9bf42a031765ee5e5f2371137f2f26967e11` |
| Node | `v24.4.1` (≥20.19.0) | satisfies OpenSpec 1.14.3 requirement |
| Python | `3.14.5` dev + isolated runtime venv (≥3.11) | |
| Git | `2.50.1 (Apple Git-155)` | |

Fresh-environment reproduction (same day, clean temp dir): clean `npm install`
re-resolves OpenSpec `1.14.3`; a fresh venv pip install re-resolves Specify
`1.2.1` with the identical upstream commit id. Fixtures: `fixtures/json/tool-versions.txt`,
`fixtures/json/fresh-openspec-version.txt`, `fixtures/json/fresh-specify-version.txt`.
The repository's `toolchain.lock.json` records the full set of identities,
digests of the probe step package and workflows, and probed OS (macOS 26.6.2
arm64; Linux marked untested).

## 2 OpenSpec Store probes (task 1.2)

All commands run with argv through the repo's pinned CLI wrapper
(`bash scripts/openspec.sh …`), store `lt01store` created in a disposable temp
directory, then unregistered. Exit codes recorded in evidence JSON.

| Probe | Command (abridged) | Exit | Result |
| --- | --- | --- | --- |
| Store creation + registration | `store setup lt01store --path <tmp>/store --json` | 0 | JSON reports registered store, git initialized+committed, file list |
| Explicit root resolution | `new change probe-root --store lt01store --json` | 0 | `root.source: "store"`, `root.store_id: "lt01store"` |
| Unknown store id | `status --change probe-root --store no-such-store --json` | 1 | JSON error object `code: unknown_store` with list of registered stores |
| Fresh change strict validate | `validate probe-root --type change --strict --json --store` | 1 | Fails with "Change must have at least one delta" (clean error fixture) |
| Complete planning validate | same + filled proposal/design/specs/tasks | 0 | `valid: true` |
| Planning vs implementation | `status …`, `instructions apply …` | 0 | `isPlanningComplete: true`, `isComplete: true` **while** apply progress 0/2 — checkbox flip moves apply to 1/2 |

Key contract learned: planning-complete (`status`) and implementation progress
(`instructions apply`) are distinct query paths; only the latter reflects the
`- [ ]` checkbox source state, confirming V1-A04's future pass criteria.

## 3 Specify control-flow probes (task 1.3)

Environment: `specify init . --non-interactive --ignore-agent-tools` in the
disposable control workspace; hub step installed with
`specify workflow step add hub --dev <tmp>/step/hub` (exit 0; `step list`
shows `hub v0.1.0` under Custom). The package proves multi-file loading:
`__init__.py` imports actions from `./actions` inside the Specify runtime.

Probe workflows (committed under `fixtures/probe-workflows/`) exercise a
hub/v1 envelope (`api_version, action, ok, business IDs, data, evidence,
warnings`) exactly as `docs/DESIGN.md` §4.1 specifies, then verify:

| Probe | Run evidence | Result |
| --- | --- | --- |
| Non-TTY gate pausing | `run probe-main.yaml --json` → exit 0, `status: paused`, `current_step: plan-review`, gate JSON with options and `choice: null` | PASS |
| Gate resume with verdict | `resume l01main --input plan_verdict=approve implementation_verdict=approve` → `status: completed` (exit 0), gate choices recorded | PASS |
| Ordered fan-out (`max_concurrency: 1`) | step ids `implement:repo:0`, `implement:repo:1`; scratch order repo-a → repo-b | PASS |
| Fan-in aggregation | `collect` output `results` aggregates the fan-out output incl. ordered item envelopes | PASS |
| Bounded do-while (cap) | `max_iterations: 3` caps at 3 verify-rounds although condition still true (`repair_threshold: 10`) | PASS |
| Condition-driven stop | `repair_threshold: 2`: exactly 2 iterations; `needs_repair` false stops before cap (run `l01loop2`) | PASS |
| Loop alias visibility | iterations 2/3 project as `integration:verify-round:1`, `integration:verify-round:2` while the base id keeps the latest result for the loop condition | PASS |
| Envelope flow | `{{ steps.prepare.output.data.repos }}` and `{{ item }}` resolve through expression namespace `inputs/steps/item` | PASS |

The validation error `Do-while step … is missing 'steps' field` proved schema
edge shapes: `do-while` bodies use `steps:` lists while fan-out uses a `step:`
template — matching the reference workflow in `docs/DESIGN.md` §2.5.

## 4 Resume and interruption probes (task 1.4)

| Probe | Command (abridged) | Exit | Recorded behavior |
| --- | --- | --- | --- |
| Failed-step resume | `run probe-fail-resume.yaml --input fail_now=true --json` | 1 | `status: failed` at `repo-run`; deterministic probe error string |
| Completed-work preservation | `status` + `resume l01fail --input fail_now=false` | 0 | Early note executed exactly once (scratch count 1); only failed step and successors re-ran; final `completed` |
| Graceful interrupt (SIGINT) | start run; `kill -INT` at t+6s | 0 | `status: paused` at in-flight step; `log.jsonl` records `workflow_interrupted` between `step_started` and resume steps; in-flight step re-executes from its start on resume (wait step ran twice, both visible in scratch) |
| Abrupt exit (SIGKILL) | start `probe-orphan.yaml` (spawns `sleep 300` ×2), `kill -9` engine at t+5s | 137 | Native state stays `status: running`; `state.json` remains valid, persisted execution tree preserves completed occurrences (`prepare`, `spawn-children`) |
| Orphan resume refusal | `workflow resume l01orphan --json` | 1 | `Error: Cannot resume run 'l01orphan' with status 'running'.` |
| Child-process termination check | `ps -o pid,ppid,pgid …` after engine death | 0 | Both spawned `sleep 300` survived parent SIGKILL; PPID reparented to 1, PGID unchanged. Children reaped manually afterwards (exit 0), confirming process-group wide take-over remains necessary |

Details: `fixtures/l01interrupt-log.jsonl.gz` (interrupt event sequence),
`fixtures/l01orphan-state.json.gz` (orphan running state), scratch order logs
in `fixtures/probe-*scratch.ndjson`, JSON fixtures under `fixtures/json/`.

### Operator-relevant findings (bounded)

1. **Background-job signal disposition artifact**: POSIX shells start
   background jobs with SIGINT ignored; the disposition survives `exec`, so
   `( trap - INT; exec specify … ) &` was required before SIGINT paused the
   engine. Spec Kit's engine itself behaved exactly as documented
   (KeyboardInterrupt → PAUSED + `workflow_interrupted`) once the default
   handler was active. The future Hub launcher must start native runs with
   default signal dispositions and check on what it launches — silently
   dispositioned agents would break the graceful-pause contract.
2. **No mid-step continuation**: resume re-executes the in-flight step from
   its start; upstream preserves *completed* occurrences, not partial step
   progress. Hub-side operation receipts must therefore cover in-flight
   side effects (matches DESIGN §2.8 intent-before-effect rule).
3. **Orphan-running is a reconciliation gate, not a resume path**: native
   resume refuses status `running` (exit 1). Recovery must (a) confirm the
   engine process and its children are gone via process group inspection,
   (b) reap survivors (`kill -TERM` succeeded on both children here),
   (c) then start a fresh native run for a new execution while reusing
   verified receipts — exactly the DESIGN §2.8 contract; never edit private
   engine state.
4. **State JSON stays readable after every kill path** (V1-A08 linkage):
   all five run directories parsed cleanly post-mortem.
5. **Expression namespace**: `inputs.*`, `steps.*`, `item`, `fan_in.*`,
   `context.run_id` supported; fan-out exposes ordered `output.results`;
   do-while re-evaluates conditions against the latest iteration projection.

## 5 Required-probe coverage vs tasks

| tasks.md item | Verification evidence |
| --- | --- |
| 1.1 | §1 (identities + fresh repro + provenance) |
| 1.2 | §2 (disposable store + root resolution + success/error JSON + planning-vs-apply) |
| 1.3 | §3 (real install, real imports, envelope, gates/fan-out/loop/fan-in) |
| 1.4 | §4 (failed resume, graceful pause+resume, SIGKILL orphan, child reaping) |
| 1.5 | This report + `toolchain.lock.json` + fixtures; decision: pass |

Upstream contract statement: OpenSpec authoritative planning surface and Spec
Kit workflow control flow both measured at release candidates — record these
as the baseline for L02–L05 typed adapters (`--store` argv, `--json` bodies,
resume semantics, fan-out ordering, loop aliases, orphan refusal).
Blocks: none. The L01 gate passes; proceed to `02-build-local-foundation`.
