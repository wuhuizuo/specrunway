# Central Store change `user-docs-v1`: operator documentation set

Date: 1 November 2026. Change: `user-docs-v1` in the `specrunway-docs` Store,
archived as `2026-11-01-user-docs-v1`. Execution:
`66c09fdc-40ce-4993-a718-c4806422eeae`.

This is the first central-Store change executed against this repository itself
(dogfood), and the first one that used the guided operator flow end to end. It
also records three product gaps found only on the live path.

## Layout used

- Control checkout: `.sr-control/` inside this repository, ignored by Git. It
  holds `local.yaml`, `.specify/`, `.specrunway/`, and `requests/`.
- Store: `/Users/wuhuizuo/Documents/Obsidian/agents-specrunway-store`, store id
  `specrunway-docs`. The id was renamed from `specrunway-store` because that
  name is registered on this machine for a different checkout
  (`/Users/wuhuizuo/Documents/Obsidian/agents/openspec-store`), which already
  carries four applied capabilities.
- Business repository: this checkout, `repo_id: specrunway`, `base_ref: main`.
- The change declares no `integration_profile`; the generated workflow omitted
  `integration-round` and completion relied on per-repository verification
  (decision D13).

## Tool identities

| Tool | Version | Note |
| --- | --- | --- |
| specrunway | 0.1.0 (editable `.venv`, from `0f6bede`) | matches the run's base commit |
| OpenSpec | 1.15.0 | frozen in `snapshot.json` |
| specify-cli | 1.2.1 | reinstalled with `uv tool install --force` from `v1.2.1`; the machine had 1.1.0 |
| opencode | 2.2.5 | **deviation**: the supported baseline is 2.1.4 |
| agent model | `deepseek/deepseek-flash` | configured as opencode's default; the profile passes no `--model` |

The `opencode` deviation is a real one and is not written up as the baseline.
`snapshot.json` recorded `openspec: 1.15.0` and `spec_kit: 1.2.1`; `opencode`
is not part of that record because the profile resolves it from `PATH`.

## Commands and results

| Step | Command | Result |
| --- | --- | --- |
| store registration | `openspec store register <path> --id specrunway-docs --json` | exit 0; doctor `Issues: none` |
| bootstrap | `specrunway init --json` | exit 0; `ok: true` |
| wiring | `specrunway doctor --json` | exit 0; six `ok` findings |
| plan | `specrunway plan user-docs-v1 --store specrunway-docs --request … --manifest …` | exit 0; 4/4 artifacts, strict validation passed |
| freeze (attempt A) | `specrunway run --change user-docs-v1 --json` | exit 0; paused at `plan-gate`; snapshot `tools` were `unknown` because the lock file was missing from the control root |
| re-freeze | `specrunway run --change user-docs-v1 --json` | exit 0; new execution, `tools` recorded |
| plan approval | `specrunway approve --kind plan --actor wuhuizuo` | digest `b88b6ba6ae90ecbc…`, `self_asserted` |
| run | `specrunway run --execution … --continue` | **failed** at `implement:repo:0` |
| recovery | `specrunway resume --execution …` | exit 0; paused at `implementation-gate` |
| implementation approval | `specrunway approve --kind implementation --actor wuhuizuo` | digest `2ce2c39677c9c032…` |
| completion | `specrunway run --execution … --continue` | exit 0; native status `completed`, phase `ready_for_review` |
| merge | `git merge --ff-only 0b606fd` | fast-forward into `main` |
| archive | `specrunway archive --execution …` | exit 0; `merged_commits`, archived as `2026-11-01-user-docs-v1` |

Trusted verification ran the frozen profile
`.venv/bin/python scripts/check_handoff.py` (cwd `.`, 120s) against the
accepted head and returned exit 0. Agent prose was not used as evidence.

## Accepted result

- Head commit: `0b606fdc7265a2300a588f52f3b22e51b4c5ff01`
- Result digest: `cd3280679f3b6b2e90effc2e4b70780e10d612656a805f59213c5f293cc20adc`
- Changed paths: `README.md`, `docs/HANDOFF_STATE.md`, `docs/user/README.md`,
  `docs/user/quickstart.md`, `docs/user/concepts.md`,
  `docs/user/commands.md`, `docs/user/troubleshooting.md`
- The original checkout was not modified during repository execution, and the
  result passed the allowed-path check (`docs`, `README.md`).
- Budget: 2 of 3 attempts.

Independent checks performed on the accepted content, not reported by the
agent: every CLI flag mentioned in `docs/user/` exists in
`specrunway <cmd> --help`; every backticked kebab-case error code appears in
`src/specrunway/`; every lifecycle phase name matches the implementation; the
documents do not claim `python -m specrunway`, which does not work.

## Failure record: attempt 1

The first fan-out attempt exited 1 immediately:

```text
> build · flint-40b-free
Error: Free usage limit reached. Connect a provider or subscribe to OpenCode Go
to keep going, or switch models.
```

opencode selected a free model rather than the authorized provider because
`~/.config/opencode/opencode.json` had no `model` key and the profile does not
pass `--model`. Fixing that key to `deepseek/deepseek-flash` and smoke-testing
`opencode run --auto … --file` produced `> build · deepseek-flash` / `OK`.
`resume` then re-ran only the failed step.

## Product gaps found

1. **No way to abandon an execution.** `FileRunStore.release_activity` has no
   production caller and no CLI surface, so once an execution exists the next
   `specrunway run --change` is refused with `ExecutionConflictError`. The
   re-freeze above required calling the store API directly, which is not an
   operator-facing action. This is the most valuable finding of the run.
2. **`doctor` does not probe the agent.** It validates control wiring only, so
   a broken default model is not discovered until the first fan-out attempt.
   The P0 dogfood report already asked for an agent preflight; this is a second
   independent occurrence.
3. **Failed steps are not visible in `status`.** After the agent failure the
   phase still read `implementing` with `pending_gate: plan`; the failing step
   (`implement:repo:0`) and its reason existed only in
   `logs/specrunway/1/agent.log`.
4. **Archived capability keeps a placeholder Purpose.** The planner emits a
   spec delta without `## Purpose`, so `openspec archive` wrote
   `TBD - created by archiving change …` into
   `openspec/specs/specrunway-delivery/spec.md` and `openspec validate --all
   --strict` failed on the Store until the Purpose was written by hand. The
   planner should emit a Purpose for new capabilities.

## Post-archive repair

`openspec/specs/specrunway-delivery/spec.md` received a real Purpose, and the
Store then passed `openspec validate --all --strict --store specrunway-docs`
(2/2 items). The Store commit is `24d6f45`; the archive backup remains under
`.sr-control/.specrunway/runs/66c09fdc-…/archive-backup/20261101T095036Z/`.

## Boundaries

- Approval stayed local `self_asserted`; it is not team authority.
- Worktrees isolate ordinary edits; they are not a hostile-process sandbox.
- The Store lives inside a synced notes vault. No sync conflict occurred during
  this run, but the placement remains a known risk for `archive`.
- `repo-attempt` for attempt 1 is recorded as `uncertain` and stays in the
  execution history; archive preflight only blocks on `archive` intents.
