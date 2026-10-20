# SpecRunway
Spec-driven execution across repositories.

---

# Central Store Coordinator implementation handoff

Build the standalone local v1 of a specification-driven coordinator for changes across repositories.
Central OpenSpec Store and cross-repository delivery are required. Specstride is excluded from the current implementation.
All application behavior in this package is proposed; no application has been implemented or accepted yet.

## Import this package

The package was prepared outside a connected Git checkout. It has not changed, initialized, committed, or pushed your target repository.

1. Extract into a temporary directory and inspect the target repository, its status, and all applicable AGENTS.md files.
2. Copy the package contents to the intended repository root. If a path already exists, review and merge it; preserve existing instructions and user changes. Do not overwrite an existing AGENTS.md or OpenSpec configuration blindly.
3. Merge `.gitignore.fragment` into the existing `.gitignore`. Keep the development OpenSpec directory in this repository distinct from disposable runtime Store fixtures.
4. Follow `docs/TOOLCHAIN.md`, then run the OpenSpec validation commands below. Planning files are already supplied: do not regenerate them from a blank prompt.
5. Give the next code agent `docs/HANDOFF.md`. Implement one ordered change at a time, with the compatibility gate first.

## Read in this order

- `AGENTS.md`: scope, invariants, and implementation discipline.
- `docs/DECISIONS.md`: latest decisions, including the exclusion of Specstride.
- `docs/DESIGN.md`: complete English design and shared v1/v2 contracts.
- `docs/IMPLEMENTATION_PLAN.md`: task IDs, dependencies, estimates, and five change boundaries.
- `docs/ACCEPTANCE.md`: acceptance procedures and evidence requirements.
- `docs/HANDOFF_STATE.md`: what has actually been done and what is still pending.

## Development workflow and product runtime

Use this repository's OpenSpec changes to build the coordinator. Use Specify workflow as the coordinator's runtime once implemented. OpenSpec is the sole planning authority for this project's own implementation; do not generate a second competing Spec Kit spec/plan/tasks set.

The coordinator must bootstrap without calling itself. Initial compatibility probes invoke the upstream OpenSpec and Specify CLIs directly, using disposable fixtures.

## First commands in the target repository

Node 20.19.0 or newer and Python 3.11 or newer are the starting tool requirements.

```bash
npm --prefix tooling/openspec install
bash scripts/openspec.sh --version
bash scripts/openspec.sh init --tools codex
python3 scripts/check_handoff.py
bash scripts/openspec.sh validate --all --strict --json
bash scripts/openspec.sh status --change 01-verify-upstream-contracts --json
bash scripts/openspec.sh instructions apply --change 01-verify-upstream-contracts --json
```

`--tools codex` configures the development agent integration. Use the installed CLI's supported tool ID for another agent. Check generated files and retain project-specific instructions. Confirm that the resolved planning root is this repository before any change mutation; do not use an unrelated global default Store.

If the environment is offline, prepare the exact tool versions through the organization's approved package distribution and record that provenance in the compatibility report.

## Implementation order

| Change | Source tasks | Exit condition |
| --- | --- | --- |
| 01-verify-upstream-contracts | L01 | Real CLI/SDK compatibility evidence and a pinned toolchain |
| 02-build-local-foundation | L02-L05 | CLI, schemas, routing, OpenSpec adapter, atomic state and locks |
| 03-deliver-two-repo-loop | L06-L12 | Planning, approval, two ordered repositories, trusted tests and bounded repair |
| 04-harden-recovery-and-archive | L13-L14 | Normal resume, abnormal recovery, explicit and reconcilable archive |
| 05-release-local-v1 | L15 | Installed-package replay and all required v1 acceptance evidence |

All five change directories are prepared, but application tasks remain unchecked. Generated planning completeness is not implementation completeness. L16/L17 and every v2 task remain outside the required v1 sequence.

## Daily agent cycle

Inspect the active change with `status` and `instructions apply`, implement its next unchecked task, run the task's meaningful checks, and update the checkbox only after the evidence exists. Record verification details under `docs/evidence/` without secrets or machine-specific paths in portable records. Update `docs/HANDOFF_STATE.md` at checkpoints. Run OpenSpec strict validation and the applicable code checks before finishing a change.

Archive a development change only after its work and required review are complete. Development-change archive and the future product's `specrunway archive` command are separate operations. No push, merge, deployment, or product Store archive follows merely from a green test.
