# Confirmed implementation decisions

Decision date: 19 October 2026. These decisions supplement the revision 2 design exported below.

| ID | Decision | Consequence |
| --- | --- | --- |
| D01 | Central Store and cross-repository changes remain essential | Preserve routing, dependency commits, global verification and archive coordination |
| D02 | Build local v1 first; team v2 later | No team service dependency or v2 implementation in the required v1 sequence |
| D03 | Exclude Specstride from current implementation | No installation, adapter, integration experiment, or mandatory comparison |
| D04 | Prefer Specify workflow as runtime | Prove the released custom-step, gate, loop and recovery contracts in L01 |
| D05 | Use OpenSpec to manage this repository's development | Maintain one set of proposal/spec/design/tasks artifacts for each change |
| D06 | Bootstrap with upstream tools directly | Product self-hosting is unnecessary for initial development |
| D07 | Keep portable business contracts and replaceable execution | Product business state does not depend on private engine state layout |
| D08 | ~~Preserve provisional `hub` / `hub/v1` identifiers~~ Superseded by D10 | Historical: the pre-release names were provisional |
| D09 | English files; no PDF deliverable | Repository-readable Markdown is the primary code-agent handoff |
| D10 | Rename the pre-release product to **SpecRunway** (20 October 2026, supersedes D08) | CLI `specrunway`, Python package `specrunway`, schema `specrunway/v1`, control directory `.specrunway/`, workflow step type `specrunway`, step package `tooling/specrunwaystep`. Full rename with no compatibility shims: v1 has not shipped, stored runs are disposable fixtures, and mixed identifiers would be worse than a clean break. Historical L01 probe fixtures keep their original `hub` text because they record what upstream was invoked with at that time; future replays use the new names. |
| D11 | Add a deterministic onboarding wizard after the v1 dogfood run (25 October 2026) | `specrunway wizard` collects `local.yaml` wiring, drafts `request.md` and a routing manifest from bounded answers, then calls the existing `init` and `plan` paths. It does not use a coding agent to write requirements, does not create approvals, and does not execute work. Request drafting stays inspectable and editable; implementation remains explicit and gated. Default `plan` routing must follow configured repository ids rather than fixture names. |
| D12 | Use `mise` for developer interpreter versions (25 October 2026) | `mise.toml` pins Python 3.14.5 and Node 24.4.1 (npm 11.4.2), matching the L01 compatibility lock, and owns `.venv` creation/activation plus bootstrap/check tasks. Python and Node package resolution remains with pip and npm inside the project; `specify-cli` and the editable package stay in the project venv. Changing a pinned interpreter requires updating the compatibility record and re-running L01 probes rather than editing `toolchain.lock.json` silently. |
 

## Source of truth

The current change's requirements define intended observable behavior; its design defines implementation choices. `docs/DESIGN.md` supplies the full architecture, and `docs/IMPLEMENTATION_PLAN.md` maps stable source task IDs to changes. `tasks.md` in the active OpenSpec change owns implementation progress. `docs/ACCEPTANCE.md` owns verification status/evidence. The older Excel file is a reference snapshot, not a second live tracker.

When a material requirement conflict appears, record the resolution here and update the affected requirements before coding. Do not silently relax a failed requirement or turn a missing integration into a successful mock-only claim.

## Development change versus product change

The five prepared OpenSpec changes build this software. Their completion and archive affect this repository's specification baseline. The future product will operate on a user's separately registered central Store and business repositories. Keep test fixtures, root selection, run IDs, approvals, and archive operations scoped to the correct layer.
