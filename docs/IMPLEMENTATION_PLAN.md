# Implementation plan

Required v1: L01-L15, estimated 14 person-days, approximately three weeks for one implementer. Estimates have roughly +/-30% uncertainty. No implementation has started.

## Ordered OpenSpec changes

| Change | Source IDs | Prerequisite | Exit condition |
| --- | --- | --- | --- |
| 01-verify-upstream-contracts | L01 | None | A pinned, reproducible compatibility report passes every required probe; application implementation remains pending. |
| 02-build-local-foundation | L02 L03 L04 L05 | 01-verify-upstream-contracts | The CLI, schemas, explicit Store adapter, and local state/locking work in disposable fixture repositories. |
| 03-deliver-two-repo-loop | L06 L07 L08 L09 L10 L11 L12 | 02-build-local-foundation | A central change reaches ready_for_review through two repositories, local review gates, trusted tests, and bounded repair. |
| 04-harden-recovery-and-archive | L13 L14 | 03-deliver-two-repo-loop | Resume/recover and archive fault cases reconcile safely; partial merge and stale evidence block archive. |
| 05-release-local-v1 | L15 | 04-harden-recovery-and-archive | The installed distribution passes all 14 required v1 cases, with live-agent and failure-replay evidence. |

Work on one change at a time. The dependency column is an implementation gate even though OpenSpec can see all prepared planning artifacts. Verify prerequisites against evidence and task completion, rather than directory existence or planningComplete.

## Required local v1 tasks

### L01 Pin tools and prove the minimum interfaces
- Stage: L0 Compatibility; estimate: 1 person-days; dependencies: None.
- Deliverable: toolchain.lock; CLI and SDK fixtures.
- Definition of done: Measure Store resolution, JSON responses, step installation, gates, loops, fan-out, normal resume, and interruption while running.
- Acceptance: V1-A01.

### L02 Create the single-package CLI and central layout
- Stage: L1 Local foundation; estimate: 0.5 person-days; dependencies: L01.
- Deliverable: hub CLI; control and Store checkouts; ignored runtime files.
- Definition of done: Commands find the Hub. Business repositories need no new tool configuration. No server or database is introduced.
- Acceptance: V1-A02.

### L03 Validate the manifest and machine repo mappings
- Stage: L1 Local foundation; estimate: 1 person-days; dependencies: L02.
- Deliverable: hub/v1 object schemas; manifest and local.yaml validation.
- Definition of done: Define manifest/snapshot/result/approval/receipt schemas. Validate IDs, repo/dependency order, remote identity, paths, profiles, and acceptance coverage.
- Acceptance: V1-A03.

### L04 Build the typed OpenSpec adapter
- Stage: L1 Local foundation; estimate: 1 person-days; dependencies: L02.
- Deliverable: argv wrappers for create, status, instructions, validate, archive.
- Definition of done: Use explicit --store and shell=False. Separate planning completion from implementation completion. Reject unsupported critical protocol data.
- Acceptance: V1-A01 V1-A04.

### L05 Implement JSON state and local exclusion
- Stage: L1 Local foundation; estimate: 1 person-days; dependencies: L02.
- Deliverable: FileRunStore; atomic writes; active execution; receipts.
- Definition of done: Only one execution owns a control/Store checkout. Replace state atomically and record intent before external side effects.
- Acceptance: V1-A08.

### L06 Implement the planning entry point
- Stage: L2 End-to-end loop; estimate: 0.75 person-days; dependencies: L03, L04, L05.
- Deliverable: hub plan; artifact generation and validation.
- Definition of done: A request produces complete OpenSpec planning artifacts and explicit repo/task routing. Manually prepared plans are also accepted.
- Acceptance: V1-A04.

### L07 Freeze context and record local approvals
- Stage: L2 End-to-end loop; estimate: 1 person-days; dependencies: L06.
- Deliverable: Snapshots; planning/result digests; self_asserted approvals.
- Definition of done: Bind approval to content. Text or rule changes invalidate it; checkbox-only changes preserve the planning digest. Do not claim team authentication.
- Acceptance: V1-A05.

### L08 Launch one real agent CLI
- Stage: L2 End-to-end loop; estimate: 1 person-days; dependencies: L03, L07.
- Deliverable: argv/cwd/prompt-file launcher; process groups; structured result.
- Definition of done: Support the first CLI actually used. Apply existing repository instructions. Never interpolate agent output into a shell command.
- Acceptance: V1-A06.

### L09 Create worktrees and run trusted tests
- Stage: L2 End-to-end loop; estimate: 1 person-days; dependencies: L08.
- Deliverable: Separate worktrees; test profiles; result validation.
- Definition of done: Preserve original checkouts. Runner tests bind evidence to commits. Reject invalid results, unexpected paths, and unverified success claims.
- Acceptance: V1-A06 V1-A07.

### L10 Package one Spec Kit hub step
- Stage: L2 End-to-end loop; estimate: 0.75 person-days; dependencies: L04, L05, L09.
- Deliverable: type: hub bridge; standardized output.data.
- Definition of done: One step package delegates to functions in the same package. Do not mutate private SDK context or build another workflow engine.
- Acceptance: V1-A01.

### L11 Run the sequential two-repo workflow
- Stage: L2 End-to-end loop; estimate: 1 person-days; dependencies: L10, L07.
- Deliverable: Prepare; gates; fan-out with max=1; fan-in; review.
- Definition of done: Run repositories in explicit order. Reject invalid dependency order before execution. The workflow runs without any v2 component.
- Acceptance: V1-A02 V1-A09.

### L12 Bound test and repair attempts
- Stage: L2 End-to-end loop; estimate: 0.75 person-days; dependencies: L11.
- Deliverable: Per-repo attempts; integration rounds; persisted budgets.
- Definition of done: Allow initial work plus at most two repairs. Test failures enter repair; exhausted budgets stop. Resume preserves counters and no-progress detection.
- Acceptance: V1-A07.

### L13 Implement normal resume and explicit recovery
- Stage: L3 Release reliability; estimate: 1 person-days; dependencies: L12, L05.
- Deliverable: Paused/failed resume; orphan-running reconciliation.
- Definition of done: Do not edit Spec Kit private state. Recover an orphan running run through reconciliation and a new native run under the same Hub execution, reusing verified receipts.
- Acceptance: V1-A08 V1-A10.

### L14 Implement explicit archive and local backup
- Stage: L3 Release reliability; estimate: 0.75 person-days; dependencies: L13, L04.
- Deliverable: Archive preflight; intent; before/after backup; completion.
- Definition of done: ready_for_review does not archive. Validate the selected completion policy and accepted/merged code. Reconcile an uncertain archive before retrying.
- Acceptance: V1-A11 V1-A12.

### L15 Replay, package, and hand over v1
- Stage: L3 Release reliability; estimate: 1.5 person-days; dependencies: L14.
- Deliverable: Installable package; README; fixture replays; v1 release.
- Definition of done: Pass every required v1 case. Demonstrate installation with the Hub, agreed upstream tools, and one agent; backup/restore and stop/takeover procedures work.
- Acceptance: V1-A01 through V1-A14.

## Deferred work

L16 local parallelism and L17 Jenkins integration remain optional. All S01-S20 tasks are v2 reference material and are not authorized implementation scope for this handoff.

| ID | Version | Task | Person-days | Dependencies | Acceptance |
| --- | --- | --- | --- | --- | --- |
| L16 | v1 | Add local parallel execution for independent repos | 1 | L15 | OPT-A01 |
| L17 | v1 | Run the local CLI on one Jenkins runner | 0.5 | L15 | OPT-A02 |
| S01 | v2 | Confirm the team pilot and permission model | 1.5 | L15 | V2-A01 |
| S02 | v2 | Create PostgreSQL metadata and unique constraints | 2 | S01 | V2-A02 |
| S03 | v2 | Implement authenticated project APIs | 1.5 | S02 | V2-A01 V2-A02 |
| S04 | v2 | Implement the durable queue and outbox | 2 | S02 S03 | V2-A03 |
| S05 | v2 | Own orchestrator state and recovery | 2 | S04 | V2-A04 |
| S06 | v2 | Implement the remote worker backend | 2.5 | S04 S05 | V2-A05 |
| S07 | v2 | Add leases, fencing, and takeover | 2 | S06 | V2-A06 |
| S08 | v2 | Enforce quotas and an explicit task DAG | 1.5 | S06 S07 | V2-A07 |
| S09 | v2 | Implement trusted approval and policy checks | 2 | S03 S05 | V2-A01 V2-A08 |
| S10 | v2 | Serialize Store publishing and archive | 2.5 | S07 S09 | V2-A09 |
| S11 | v2 | Provide shared artifact storage | 1.5 | S03 S06 | V2-A05 V2-A10 |
| S12 | v2 | Implement the remote CLI backend | 1.5 | S03 S09 S11 | V2-A02 V2-A08 |
| S13 | v2 | Export portable data and import read-only history | 2 | S10 S11 S12 | MIG-A01 through MIG-A05 |
| S14 | v2 | Add audit, budgets, and operational alerts | 1.5 | S05 S07 S11 | V2-A10 |
| S15 | v2 | Test authorization and credential isolation | 2 | S08 S09 S10 S11 | V2-A01 V2-A05 V2-A08 |
| S16 | v2 | Run the queue and recovery failure matrix | 2 | S13 S14 S15 | V2-A03 V2-A04 V2-A06 V2-A09 |
| S17 | v2 | Pilot two users across multiple runners | 2 | S16 | V2-A07 V2-A11 |
| S18 | v2 | Hand over deployment, backup, and rollback | 1.5 | S16 | V2-A12 |
| S19 | v2 | Release team v2 | 1 | S17 S18 | V2-A01 through V2-A12; MIG-A01 through MIG-A05 |
| S20 | v2 | Add Web execution and approval pages | 3 | S19 | OPT-A03 |

Required team v2 effort remains an estimate of 34.5 person-days. Starting v2 requires a separate decision after v1 acceptance. Do not create service, authentication, queue, database, or Web placeholders now.

## v2 handoff reference

### S01 Confirm the team pilot and permission model
Deliverable: Projects; roles; trust boundary; supported scope.
Done: Confirm at least two users and a need for central execution. Define project boundaries. Local v1 approval grants no team authorization.

### S02 Create PostgreSQL metadata and unique constraints
Deliverable: Projects; executions; jobs; attempts; approvals; outbox.
Done: Define unique business keys, revision/CAS, transactions, and idempotent retries. Keep Spec Kit private state in its native workspace.

### S03 Implement authenticated project APIs
Deliverable: Typed API; Idempotency-Key; If-Match; RBAC.
Done: Derive actor from authentication. Enforce project scope. Return 409 for stale revisions. Do not accept arbitrary shell commands.

### S04 Implement the durable queue and outbox
Deliverable: Transactional outbox; dispatch; deduplication; cancellation.
Done: Recover from a committed DB transaction with no published message, and from duplicate deliveries. Make no exactly-once claim.

### S05 Own orchestrator state and recovery
Deliverable: One execution owner; pinned image; persistent native workspace.
Done: Only one concurrent resume acquires ownership. A replacement runner accesses the original SDK state and matching step implementation.

### S06 Implement the remote worker backend
Deliverable: Controlled clone; image; context delivery; result callback.
Done: Assign paths on the runner. Mount code writable and context read-only. Do not expose the controller or Store to workers.

### S07 Add leases, fencing, and takeover
Deliverable: Heartbeat; epochs; late-result handling.
Done: A stale worker attempt or orchestrator owner cannot accept results or publish Store changes. Confirm termination before reassignment.

### S08 Enforce quotas and an explicit task DAG
Deliverable: Global/project/repo concurrency; ready batches.
Done: Read dependencies from the manifest. Apply explicit resource rules and project fairness. Keep one writer per worktree.

### S09 Implement trusted approval and policy checks
Deliverable: Authenticated approvals; scope/digest binding; role policy.
Done: Clients cannot assert another actor. Changed planning or verification digests invalidate approval before further execution.

### S10 Serialize Store publishing and archive
Deliverable: Store write queue; Git CAS/PR; archive receipts.
Done: Serialize changes to the same Store/capability. Reconcile uncertain archive/push outcomes. Resolve Git conflicts without force push.

### S11 Provide shared artifact storage
Deliverable: Object storage; hashes; authorized access; retention.
Done: Authorize evidence by project. Keep permanent refs and hashes beyond temporary URLs. Exclude secrets from logs.

### S12 Implement the remote CLI backend
Deliverable: hub --backend team; command-to-API mapping.
Done: Select local/team with the same user intent. The server repeats semantic and authorization checks independently of the client.

### S13 Export portable data and import read-only history
Deliverable: Portable bundle; identity mapping; historical provenance.
Done: Import terminal history idempotently. Preserve local approval as history. Open changes use a new team execution and fresh approval.

### S14 Add audit, budgets, and operational alerts
Deliverable: Audit events; cost/round budgets; drift and uncertainty alerts.
Done: Persist budgets across restarts. Trace operations and evidence by project, execution, job, and authenticated actor.

### S15 Test authorization and credential isolation
Deliverable: Project access; mounts; secrets; hostile-input test report.
Done: Reject cross-project access and approval bypass. Workers have no production merge or deployment credentials.

### S16 Run the queue and recovery failure matrix
Deliverable: Duplicate delivery; lost worker; owner rebuild; archive faults.
Done: Reconcile crashes between each external effect and its receipt. Late results never overwrite the accepted current result.

### S17 Pilot two users across multiple runners
Deliverable: Role/machine pilot; partial-merge takeover report.
Done: Replay normal, repair, and owner-rebuild paths. Use existing organizational authorization for real code merges.

### S18 Hand over deployment, backup, and rollback
Deliverable: Single-region deployment; restore drill; version/rollback runbook.
Done: Measure recovery objectives. Pause new jobs/archive independently. Restore active executions with their pinned images.

### S19 Release team v2
Deliverable: Release; compatibility matrix; entry decision.
Done: Pass every required team and migration case. Keep v1 independently usable. Do not transfer active jobs between backends.

### S20 Add Web execution and approval pages
Deliverable: Minimal list/detail views; approvals; evidence links.
Done: Reuse the same API and authorization. Do not duplicate scheduling, approval rules, or the business state machine.

## Migration checklist for the later team phase

| ID | Content | v1 source | v2 treatment | Constraint | Tasks | Acceptance |
| --- | --- | --- | --- | --- | --- | --- |
| M01 | Shared rules and specifications | Hub and Store Git repositories | Retain Git and stable identities; register them to the project | Never treat a personal absolute path as a runner path | S13 | MIG-A01 |
| M02 | Terminal execution results | hub/v1 results, completion, artifact hashes | Import a portable bundle as read-only history | Import creates no executable job | S13 | MIG-A01, A02 |
| M03 | Local approvals | auth_level=self_asserted | Preserve provenance; reapprove new team executions | Never upgrade history to authenticated authorization | S09 S13 | MIG-A03 |
| M04 | Active changes | Run/execution state and owner | Finish or cancel locally; create a new team execution | Do not continue a copied private SDK run from the shared queue | S13 | MIG-A04 |
| M05 | Machine paths and agent configuration | local.yaml and credentials | Replace with repo identities, remotes, and platform profiles | Credentials belong in the server secret store | S06 S13 | MIG-A01 |
| M06 | Archived changes | Store archive and completion receipt | Recognize identity and present read-only history | Do not replay archive or reapply specification deltas | S10 S13 | MIG-A05 |
| M07 | Rollback and coexistence | Local/team execution ownership | Pause team dispatch; reconcile owners; continue new local work | One backend advances a given change at a time | S18 | MIG-A05 |

## Risks and decisions

| ID | Risk | Signal | Response | Responsible role | Tasks |
| --- | --- | --- | --- | --- | --- |
| R01 | v1 scope expands into a platform | Required dependencies include DB, HTTP, queue, accounts, or a general scheduler | Move them to v2. Release v1 against its independent required acceptance cases. | Implementer | L02 L15 |
| R02 | Main branch differs from the selected release | SDK/output/recovery contracts change | Pin and measure versions in L01. Do not retain stale assumptions about nested-step replay. | Implementer | L01 |
| R03 | Local writers or context drift | Multiple CLI writers; changed plans/rules | Use local exclusion and frozen digests; reapprove changes. Resolve cross-clone Git conflicts manually. | Implementer | L05 L07 |
| R04 | Local automation mistaken for enforced isolation | Agent and operator share an OS identity | State the trusted single-user boundary. v2 adds enforced mounts, authorization, and scoped credentials. | Implementer / Runtime | L08 S15 |
| R05 | Forced recovery of a running native run | SDK remains running or child termination is unconfirmed | Reconcile first. Create a new native run when required and reuse verified receipts. Never edit private SDK state. | Implementer | L13 |
| R06 | Uncertain archive or partial merge | External effect succeeds without receipt; some repos remain unaccepted | Block archive; inspect intent and before/after evidence; preserve the work scene. | Implementer / Owner | L14 S10 |
| R07 | Local history becomes trusted team authority | Importer accepts source auth level or schedules active jobs | Import read-only history; require a new execution, server authentication, and fresh approval. | Backend | S09 S13 |
| R08 | Team components share the wrong state backend | Orchestrators write one private .specify directory or shared SQLite | Use one owner per execution, persistent native workspaces, and separate DB metadata from SDK state. | Runtime | S05 |
