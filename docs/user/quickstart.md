# Quickstart: install to ready_for_review

This page is the shortest supported path for local SpecRunway. It ends at
`ready_for_review`; merging and archive remain explicit operator actions. The
full lifecycle is in [concepts.md](concepts.md).

## 1. Prepare the machine

You need:

- a control directory for SpecRunway configuration and run state;
- one or more existing Git checkouts (the change's repositories);
- a directory for the central OpenSpec Store that is not inside another Git
  checkout;
- Node.js >= 20.19.0 for OpenSpec;
- `opencode` 2.1.4 or newer with a model configured (the shipped profile does
  not pass `--model`);
- `uv` for the primary install path.

SpecRunway creates a separate Git worktree for each repository in an
execution. It does not copy uncommitted files from your checkouts and does not
overwrite them. Commit or stash anything you do not want in the worktree base.

## 2. Install the CLI

```bash
uv tool install "specrunway @ git+https://github.com/wuhuizuo/specrunway.git"
uv tool install "specify-cli @ git+https://github.com/github/spec-kit.git@v1.2.1"
npm install --global @fission-ai/openspec@1.15.0
uv tool update-shell          # once, if ~/.local/bin is not on PATH
```

Open a new shell after `uv tool update-shell`, then check the tools:

```bash
specrunway --version          # specrunway 0.1.0
opencode --version            # 2.1.4 or newer
specify version               # 1.2.1
openspec --version            # 1.15.0
```

`uv` provisions a private Python for `specrunway` and `specify-cli`; you do not
install Python or activate a virtual environment. OpenSpec is still a Node
package and is installed globally by npm.

From a source checkout, install the current tree with `uv tool install .` and
the pinned OpenSpec locally with `npm ci --prefix tooling/openspec`; install
`specify-cli` with the `uv tool install` command above. A released wheel can be
installed with `uv tool install ./specrunway-0.1.0-py3-none-any.whl`.

### Manual install fallback

Use this path only when `uv` is unavailable. It needs Python >= 3.11 and a
user-managed virtual environment.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install specrunway-0.1.0-py3-none-any.whl   # or: pip install .
.venv/bin/python -m pip install "specify-cli @ git+https://github.com/github/spec-kit.git@v1.2.1"
npm install --global @fission-ai/openspec@1.15.0
.venv/bin/specrunway --version
```

With the fallback, prefix the remaining commands with `.venv/bin/` or activate
the venv first.

## 3. Create the control checkout and run the wizard

Create an empty directory for the control checkout and run the guided setup
there:

```bash
mkdir ~/work/specrunway-control
cd ~/work/specrunway-control
specrunway wizard
```

The wizard has two phases.

1. **Configuration.** It discovers sibling Git checkouts and asks for the
   Store id and path, repository paths and ids, and the agent profile. It
   writes `local.yaml`, then runs the same bootstrap as `specrunway init`:
   Store registration, `.specify` initialization, and the bundled
   `specrunway` workflow step. If the control directory is inside a Git
   checkout, the default Store is a sibling named
   `<enclosing-checkout>-specrunway-store`, because OpenSpec refuses a Store
   nested inside another checkout.
2. **Request.** It asks for a change summary, why, what, optional context,
   acceptance criteria, participating repositories, execution order, tasks,
   base refs, allowed paths, a change-scoped test command per repository, and
   whether a combined integration check exists. It writes
   `requests/<change>.md` and `.specrunway/requests/<change>.manifest.yaml`,
   adds the change-scoped test profiles to `local.yaml`, and calls
   `specrunway plan`.

A repository with no dependency answer is independent. Omit integration when
there is no real combined check; SpecRunway does not invent a placeholder.

The wizard stops after planning. Run, approval, recovery, and archive remain
explicit. Every generated file is editable before the run.

Useful variants:

```bash
specrunway wizard --skip-plan            # configure only
specrunway wizard --request my.md --manifest my-manifest.yaml --change my-change
specrunway wizard --reconfigure          # revisit local.yaml wiring
specrunway wizard --force                # replace existing generated files
```

## 4. Verify the control checkout

```bash
specrunway doctor --json
```

Exit code 0 means the wiring is sound. `doctor` checks `local.yaml`, the Store,
the repository paths, Git identity, and remote identities; it does not probe
the agent or the upstream CLI versions. A non-zero exit lists findings that
must be fixed before planning or running.

## 5. Plan

The wizard normally plans the change already. To plan again, or to use the
manual configuration path:

```bash
specrunway plan my-change --store my-store --request request.md --json
```

`plan` generates proposal, design, tasks, and specification deltas when the
change is new, or accepts an existing complete plan. Tasks are written as
`- [ ] 1.1 [T001] ...`; the routing manifest maps each task id to exactly one
repository. Planning success is not implementation completion: checkboxes stay
unchecked.

On success the envelope reports `change_id`, `change_path`, `manifest_path`,
`task_ids`, and `planning_complete: true`.

## 6. Start the run and approve the plan

```bash
specrunway run --change my-change --json
```

The command freezes the snapshot (planning bytes, routing, base commits, test
profiles, and tool versions), creates the execution, starts the native Specify
workflow, and pauses at the plan gate. The phase becomes
`awaiting_plan_review`; the envelope contains the `execution_id`. Keep it:

```bash
EXEC=00000000-0000-0000-0000-000000000000   # value from run --json
specrunway approve --execution "$EXEC" --kind plan --actor "$USER"
specrunway run --execution "$EXEC" --continue
```

`approve` records a local `self_asserted` receipt bound to the frozen planning
digest. `run --continue` checks that receipt against the frozen snapshot. Use
`specrunway resume` instead when you want the live plan bytes revalidated; it
refuses with `approval-stale` if the approved content changed after freeze.
Both paths supply the native gate verdict.

The repositories then run in the frozen `repo_order`. Each repository gets a
worktree at its base commit, an agent attempt, and a trusted test run. Results
that fail identity, ancestry, path, digest, or test-receipt checks are
rejected and may be repaired within the configured budget. If the manifest
declares an integration profile, the combined check runs after the repository
results are accepted.

## 7. Approve the implementation and reach ready_for_review

When all repository results and the optional integration check are accepted,
the run pauses at the implementation gate and the phase becomes
`awaiting_implementation_review`. Review the accepted commits and evidence
first:

```bash
specrunway status --execution "$EXEC" --json
```

Then record the second approval and continue:

```bash
specrunway approve --execution "$EXEC" --kind implementation --actor "$USER"
specrunway run --execution "$EXEC" --continue
specrunway status --execution "$EXEC" --json
```

The phase is now `ready_for_review`. This means the implementation evidence
was reviewed and accepted; it does not mean the code is merged or the change
is archived.

## 8. Finish explicitly

Merge the accepted commits into the configured base refs through your normal
code-review process, then archive:

```bash
specrunway archive --execution "$EXEC" --json
```

The default `merged_commits` policy verifies that every accepted head is
contained in the base ref. A personal project may instead select
`validated_commits` explicitly:

```bash
specrunway archive --execution "$EXEC" \
  --policy validated_commits --confirm-validated --json
```

Archive is never automatic. It saves a local backup, writes an operation
intent, applies the OpenSpec change, and records a receipt. See
[troubleshooting.md](troubleshooting.md) if archive refuses or the outcome is
uncertain.

## 9. Manual configuration (without the wizard)

Write `local.yaml` in the control checkout:

```yaml
store:
  id: my-store
  path: /abs/path/to/store
repos:
  repo-a:
    path: /abs/path/to/repo-a
    remote_identity: github:example-org/repo-a
  repo-b:
    path: /abs/path/to/repo-b
    remote_identity: github:example-org/repo-b
agent_profile: primary-coding-agent
max_workers: 1
test_profiles:
  repo-a-unit:
    command: ["python", "-m", "pytest", "-q"]
    cwd: .
  repo-b-unit:                     # one profile per manifest test_profile
    command: ["python", "-m", "pytest", "-q"]
    cwd: .
```

Then:

```bash
specrunway init --json
specrunway doctor --json
specrunway plan my-change --store my-store \
  --request request.md --manifest manifest.yaml --json
specrunway run --change my-change --json
```

The rest of the flow, including both approvals and archive, is unchanged.
Manifest fields and routing rules are described in `docs/RUNBOOK.md` and
`docs/DESIGN.md`.

## Where to go next

- [concepts.md](concepts.md) explains the objects and lifecycle.
- [commands.md](commands.md) is the command and error-code reference.
- [troubleshooting.md](troubleshooting.md) is symptom-first recovery.
