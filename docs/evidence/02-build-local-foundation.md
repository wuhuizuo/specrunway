# Change 02 Evidence: build-local-foundation (L02-L05)


> Naming note (decision D10): transcripts below predate the SpecRunway rename. `hub`/`hubcoord` names in commands and paths are historical; current commands use `specrunway`.

Date: 2026-10-20
Branch: main @ d4357f9 (L01) → this change

## Toolchain and install

```bash
cd /Users/zuowuhui/apps/github.com/wuhuizuo/specrunway
.venv/bin/pip install -q -e . pytest ruff   # exit 0
.venv/bin/ruff check src/ tests/            # "All checks passed!" (exit 0)
```

Distribution: `hub-cli==0.1.0` (`src/` layout, setuptools), console script `hub`,
`requires-python >= 3.11`, runtime dep `PyYAML>=6.0`, dev extra `pytest>=8, ruff>=0.4`.
`python -m platform`: macOS 26.6.2 (arm64), CPython 3.14.5 (same venv hosts pinned Specify 1.2.1).

## L02: single-package CLI and central layout

- `hub --version` → `hub 0.1.0`.
- `hub doctor --root <fixture-control> --json` → envelope `{"api_version":"hub/v1","action":"doctor"}`, all findings ok, `EXIT=0`.
- Walk-up detection: run from `${fixture}/control` (no `--root`) → control root found, `EXIT=0`; run from business checkout `<fixture>/repo-a` → `no-control-checkout`, `EXIT=1`.
- Explicit-root misuse: `hub doctor --root /tmp/empty` → `local-yaml: not found`, `EXIT=1`.
- Unimplemented subcommands (`plan run approve status resume recover archive`) → hub/v1 envelope, `code: "not-implemented"`, `EXIT=69`; see `openspec/changes/03-*|04-*`.
- Business checkouts untouched: `git status --porcelain` in `repo-a`/`repo-b` = 0 entries after doctor runs; no `.specify/`, no tool init written.

## L03: manifest/mapping machine validation

`tools = hubcoord.models` (manifest, local, records, common).

Verified failures (each asserted by test id, all `GroupedValidationError`):

- malformed IDs: store_uid/change_uid non-UUID; change_id non-slug; `api_version: hub/v2` → reject.
- task routing: lowercase task ids, duplicated task ids (within repo, across repos, into acceptance `verifies`), unmapped acceptance rows, uncovered tasks, `acceptance` missing → reject.
- traversal: `../`, absolute, `..\\`, empty segment in allowed_paths/changed_paths → reject.
- unknown profiles: `test_profile` not in declared control profiles → `unknown-profile`; without a control profile catalog validation stays shape-level.
- ordering: forward dependency (later repo depends earlier), 2-node cycle, repo in repos∉repo_order, repo_order slot without entry → reject before any agent invocation (`validate_checkout_wiring` runs before `hub plan/run` can proceed; no agent exists in change 02).
- wiring: store missing / no openspec dir → `store-missing` / `store-uninitialized`; non-git path → `repo-not-git`; origin URL not matching declared `remote_identity` (`github:owner/repo` vs https/ssh/scp URL spellings) → `wrong-checkout`; unknown host/path forms → `remote-identity`.
- local.yaml shapes: relative paths (store/repos), `max_workers != 1` → `not-supported-in-v1` (v1 = one execution per checkout), agent_profile missing, unknown keys.
- records: snapshot binds embedded manifest via `json_digest` (mutation → `digest-mismatch`); base_oid/40-hex, tools keys, RFC3339 stamps enforced; result validates untrusted agent output shape (decisions implemented/skipped/blocked, tests_claimed statuses, digest format); approvals enforce `auth_level: "self_asserted"`; operations enforce colon-separated operation_key, intent digest, status ∈ {pending, recorded, uncertain, reconciled}.
- digests: `json_digest` canonical sorted-key JSON; `strip_checkbox_markers` flips `- [x]`/`- [ ]` to `- ` for planning-digest input (checkbox excluded, task text kept).

## L04: typed OpenSpec adapter

`hubcoord.openspec_adapter.OpenSpecAdapter` (argv, `shell=False`, cwd = explicit store path, `--store <id>` on every change command; 300 s timeout).

Live integration (pinned OpenSpec 1.14.3 via `tooling/openspec/node_modules/.bin/openspec`, disposable store each run, `store unregister` cleanup):

| Command sequence | Result |
| --- | --- |
| `store setup <id> --path <dir> --json` | exit 0; keys `store{}`+`registry{}` required |
| `new change probe-change --store <id> --json` | exit 0; `change{id,path,metadataPath,schema}`; duplicate → error surfaces (message contains `exists`) |
| `status --change probe-change --store --json` | `isPlanningComplete` false before artifacts; true after artifacts |
| `instructions apply --change … --json` | `progress {total, complete, remaining}` + task rows; apply 0/1 → checkbox flip → 1/1 (planning vs implementation separation preserved) |
| `validate probe-change --store --strict --json` | exit 0 + `valid:true`, `issues:[]`; RFC2119-less spec: exit 1 BUT structured `items[] valid:false` payload — adapter treats as result, `valid:false`, issues surfaced |
| `archive probe-change --store --yes --json` | exit 0; `archivedAs`, `path`, `specsUpdated:true`, `totals{added:1}`; change dir moved to `changes/archive/<date>-<id>` |

Unknown store → error envelope (`unknown_store`/`no_registered_stores`), surfaced via `OpenSpecCommandError(code=…)`; tests assert message contains one of both codes
(exit-code 1 with clean JSON error payloads).

Protocol guards: success payloads missing required keys (`store+registry`, `change+root`, `changeName+artifactPaths+root`, `progress+tasks`, `items+summary`, `archive+root`) → `OpenSpecProtocolError`; wrong root routing (`root.source != store` / other `store_id`) → `OpenSpecProtocolError`; non-dict payloads → `OpenSpecProtocolError`. This rejects unsupported critical protocol data instead of silently proceeding.

## L05: JSON state, atomic writes, ownership, operations

`hubcoord.runstore.FileRunStore` (`<control>/.hub/…`):

- atomic writes: tmp-file + fsync + `os.replace` (test writes a 200 KB payload mid-stream: no torn reads); leftover tmp files asserted absent.
- revisions: `update_state(execution, mutate, expected_revision)` CAS; wrong expected → `RevisionConflictError`; immutable `execution_id`/`created_at` survive mutation attempts; missing keys in foreign state → `StateCorruptError`; foreign `execution_id` in file → `StateCorruptError`.
- interrupted write simulation: handcrafted torn JSON (`'{"phase":…'`) → `StateCorruptError` on read (not silent reset).
- ownership: `claim_activity` idempotent per execution; conflicting execution → `ExecutionConflictError`; `release_activity` refuses foreign execution; owner record persists for a running (non-blocked) run.
- locks: `fcntl` exclusive lock with blocking deadline (`lock(timeout=…)`, raises `LockTimeoutError("`control checkout is locked by another hub process`")`) and non-blocking probe mode; separate OS process can acquire after holder exit (multiprocessing test).
- effect-before-receipt: `write_intent` (status pending) must precede any receipt; `record_receipt` without intent → `[no-intent]`; `write_intent` reusing an open key → `[operation-key-reuse]`; crash between intent and receipt keeps exactly one `pending` row ` `(reconciliation surface); `mark_uncertain` → `uncertain` (with findings), `reconcile` → `reconciled` and mirrors into `state.json.operations` via CAS with bounded retry.

## Test totals

`.venv/bin/python -m pytest -q` → `119 passed in 33.42s` (exit 0), including 5 real-CLI integration tests (full lifecycle + strict-validate failure path + unknown-store + change-exists + protocol guards) and locking/ownership/multiprocessing tests.

Repository planning validation after the change:

```bash
bash scripts/openspec.sh validate --all --strict --json   # exit 0; totals {items:5, passed:5, failed:0}
python3 scripts/check_handoff.py                          # {"changes":5,"source_tasks":15,"checkbox_tasks":23,…,"result":"passed"}
```

## Deferred notes

- `hub plan/run/approve/status/resume/recover/archive` remain explicit stubs (exit 69); their behavior lands in 03-deliver-two-repo-loop / 04-harden-recovery-and-archive.
- `hub doctor`'s per-repo wiring rows report model codes (`store-missing`, `store-uninitialized`, `repo-not-git`, `remote-missing`, `wrong-checkout`) — findings carry `[code] message`; no legacy doctor codes remain.