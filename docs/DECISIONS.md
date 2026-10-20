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
| D08 | Preserve provisional `hub` / `hub/v1` identifiers | The proposed SpecRunway name is not a prerequisite or an approved rename |
| D09 | English files; no PDF deliverable | Repository-readable Markdown is the primary code-agent handoff |

## Source of truth

The current change's requirements define intended observable behavior; its design defines implementation choices. `docs/DESIGN.md` supplies the full architecture, and `docs/IMPLEMENTATION_PLAN.md` maps stable source task IDs to changes. `tasks.md` in the active OpenSpec change owns implementation progress. `docs/ACCEPTANCE.md` owns verification status/evidence. The older Excel file is a reference snapshot, not a second live tracker.

When a material requirement conflict appears, record the resolution here and update the affected requirements before coding. Do not silently relax a failed requirement or turn a missing integration into a successful mock-only claim.

## Development change versus product change

The five prepared OpenSpec changes build this software. Their completion and archive affect this repository's specification baseline. The future product will operate on a user's separately registered central Store and business repositories. Keep test fixtures, root selection, run IDs, approvals, and archive operations scoped to the correct layer.
