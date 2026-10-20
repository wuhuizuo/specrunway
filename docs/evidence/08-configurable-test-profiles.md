# Change 08 evidence: configurable, frozen test profiles

## Implemented (L18)

- `local.yaml` may declare `test_profiles: {name: {command: [argv...],
  cwd?: "<relative>", timeout_seconds?: int}}`. The schema rejects empty
  argv, absolute cwd, parent traversal, non-slug names, and non-positive
  timeouts; configured profiles override the built-in registry by name.
- `specrunway/testprofiles.py`: `TestProfile` now carries `cwd` and
  `timeout_seconds`; `freeze_test_profiles` resolves every profile referenced
  by the manifest and stores `command`/`cwd`/`timeout_seconds`/`config_digest`
  in `snapshot.test_profiles`; `profile_for_repo` prefers frozen data and
  falls back to the built-in `unit` profile for legacy snapshots.
- Freeze happens in `hub run` before any agent work; unknown profiles refuse
  execution. `local.yaml` edits after freeze do not affect the execution.
- Consumers now use the frozen profile and its relative cwd: run-repo trusted
  receipts, verify-round/repair-round, integration repair verification, the
  prompt's trusted `test_command`/`test_cwd`, and the archive final-matrix
  check.
- Examples/RUNBOOK show Go (`go test ./...` in a subdirectory) and
  kustomize/Helm (`bash scripts/validate_k8s_yaml.sh`) profiles.

## Verified

`tests/test_test_profiles.py` (5 tests, real git + fake agent):

1. Unsafe absolute/`..` cwd and an empty argv are rejected by config
   validation (`test-cwd`).
2. A repository whose tests live in `sub/` runs the frozen profile from the
   worktree subdirectory: the trusted receipt records
   `.../worktrees/repo-a/sub` and passes; the snapshot stores `cwd: "sub"`.
3. After freezing, changing the control command to a failing one leaves
   verification passing — the frozen argv is authoritative.
4. An unknown profile refuses freeze (`unknown-profile`).
5. A snapshot without `test_profiles` falls back to the built-in `unit`
   profile.

Full suite: `pytest -q` → 203 passed. `ruff check src tests` → clean.
`scripts/check_handoff.py` → L01-L18 coverage. `openspec validate --all
--strict` → valid.

Acceptance linkage: V1-A03 (profile validation), V1-A06 (trusted evidence),
V1-A07 (repair feedback uses the same trusted command).
