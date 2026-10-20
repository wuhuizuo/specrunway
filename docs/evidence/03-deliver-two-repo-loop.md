# Evidence: change 03 — L06 planning entry point

Change: `03-deliver-two-repo-loop` source task L06 (task 1.1, acceptance link V1-A04).

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
