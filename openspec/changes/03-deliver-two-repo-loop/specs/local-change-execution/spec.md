# Spec Delta

## Purpose

Carries a prepared central change through ordered repository implementation with separate worktrees and traceable accepted results.

## ADDED Requirements

### Requirement: Central planning entry
The system SHALL generate or accept complete OpenSpec planning artifacts and validate explicit task routing before implementation.

#### Scenario: Manual plan accepted
- **WHEN** a user supplies an already completed valid plan
- **THEN** the coordinator can run it without generating a competing specification set.

### Requirement: Separate worktrees
The system SHALL execute agent code changes in separate worktrees rooted at frozen base commits and preserve original checkout contents.

#### Scenario: Uncommitted original files
- **WHEN** the original checkout contains uncommitted work
- **THEN** a run leaves that content intact and starts from the declared base commit.

### Requirement: Ordered dependency results
The system SHALL pass accepted upstream commit and contract references to a downstream repository after its prerequisites succeed.

#### Scenario: Upstream failed
- **WHEN** the first repository has no accepted result
- **THEN** the dependent repository does not proceed using a mutable branch as substitute evidence.

### Requirement: Result validation
The system SHALL verify execution, repository and task identities, context digest, commit ancestry, changed paths, and trusted test evidence before accepting a result.

#### Scenario: Foreign result
- **WHEN** an agent reports a different head or context digest
- **THEN** the coordinator rejects it and does not mark central tasks complete.
