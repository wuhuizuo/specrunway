# Spec Delta

## Purpose

Maps a central change to stable repository and task identities with an explicit executable order and verifiable repository bindings.

## ADDED Requirements

### Requirement: Complete routing
The manifest SHALL map each executable task ID to exactly one declared repository and an acceptance criterion.

#### Scenario: Missing or duplicate task
- **WHEN** a manifest omits or duplicates an executable task ID
- **THEN** preflight rejects it before code changes.

### Requirement: Monotonic repository order
Local v1 SHALL execute repositories in explicit repo_order and SHALL reject cycles or dependencies on later repositories.

#### Scenario: Backward dependency
- **WHEN** a repository depends on one that appears later in repo_order
- **THEN** preflight reports the invalid order and does not schedule work.

### Requirement: Machine path separation
Portable manifests SHALL use stable repository identities while machine configuration resolves paths and verifies the expected Git remote.

#### Scenario: Wrong checkout
- **WHEN** a mapped path resolves to another repository or remote
- **THEN** preflight fails without running an agent.
