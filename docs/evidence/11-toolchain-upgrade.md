# Toolchain upgrade: opencode 2.1.4 and OpenSpec 1.15.0

Date: 25 October 2026. Decision: D14 in `docs/DECISIONS.md`; pins:
`toolchain.lock.json` and `tooling/openspec/package.json`.

Environment: macOS (Darwin 25.6.0, arm64), Python 3.14.5, Node 25.5.0,
uv 0.12.23, specify-cli 1.2.1, OpenSpec 1.15.0, opencode 2.1.4 (Homebrew).
The previous release evidence used OpenSpec 1.14.3 and opencode 1.18.33; those
documents are kept as historical records and are not rewritten.

## Changed

- `tooling/openspec/package.json` and `package-lock.json`: OpenSpec pinned
  exactly at `1.15.0` (integrity
  `sha512-lG/EPEiL22bB70yKJhWWSPk1UQGLnwO7Dp+hNc/jUmBwb0qxPLzHCUkXEfkny4iYDOsgnsNQmc39/g9QcvnBnA==`).
- `src/specrunway/launcher.py`: the `primary-coding-agent` profile drops
  `--pure` because opencode 2.x removed it. The argv template is now
  `opencode run --auto "<fixed message>" --file <prompt_file>`.
- `tests/test_launcher.py`: asserts the profile does not pass `--pure` and keeps
  `--file` as the last prompt attachment.
- `toolchain.lock.json`: OpenSpec 1.15.0 plus the upgraded-from note, a new
  `agent` block for opencode 2.1.4, and the re-run strict validation result.
- `docs/TOOLCHAIN.md`, `docs/RUNBOOK.md`, `README.md`: current pins, the agent
  argv shape, the removed flag, and the model note.
- `docs/DECISIONS.md` D14 records the upgrade and the re-verification rule.

## Commands and results

| Command | Result |
| --- | --- |
| `npm install --prefix tooling/openspec --save-exact @fission-ai/openspec@1.15.0` | exit 0; one package changed; lock file updated |
| `tooling/openspec/node_modules/.bin/openspec --version` | `1.15.0` |
| `openspec store --help` | Store subcommands still present (`setup`, `register`, `unregister`, `list`, `doctor`) |
| `opencode --version` | `opencode v2.1.4` |
| `opencode run --help` | `--auto` and `--file` present; `--pure` is gone |
| `.venv/bin/python -m pytest -q` | `226 passed in 232.64s`, exit 0 (includes real pinned-OpenSpec adapter, planning, archive, and bridge integration tests) |
| `.venv/bin/python -m pytest -q tests/test_launcher.py` | `8 passed in 3.02s` |
| `bash scripts/openspec.sh validate --all --strict` | `11 passed, 0 failed` |
| `.venv/bin/python -c "import json; json.load(open('toolchain.lock.json'))"` | lock parses |

## Live agent launcher probe (opencode 2.1.4)

A prompt file containing `Reply with exactly: OK. Do not create, modify, or
delete any files.` was launched through the shipped `run_agent` path.

- First probe, no `--model`: opencode selected its free default
  (`build · flint-40b-free`), retried, and returned exit 1 with
  `Upstream request failed: Endpoint is unavailable.` The profile does not pin
  a model, so this is an opencode/provider configuration issue rather than a
  launcher defect.
- Second probe with `--model deepseek/deepseek-flash`: `status: completed`,
  `exit: 0`, duration 1.095 s; the log shows `> build · deepseek-flash` and
  `OK.`

The product profile was not changed to pin a model: model choice stays with
opencode configuration. Operators should confirm their opencode default model
before a run.

## Compatibility notes

- OpenSpec 1.15.0 keeps the JSON contracts used by the adapter (`store setup`,
  `new change`, `status`, `instructions apply`, `validate`, `archive`); the
  full suite and the strict validation above are the re-verification.
- The L01 compatibility report remains the record of the 1.14.3 gate. The
  upgrade does not claim that every L01 probe was replayed manually on
  1.15.0; the suite exercises the same production adapter surfaces against the
  new pinned binary, and the strict validation covers the repository specs.
- No full two-repo live coordinator run was repeated at opencode 2.1.4. The
  historical live replay (opencode 1.18.33) remains the end-to-end record;
  V1-A02 records this upgrade as a launcher-level live probe.

## Non-claims

- This is not a new release and does not change the original release matrix.
- The free opencode model path was not made reliable; it remains a provider
  availability issue.
