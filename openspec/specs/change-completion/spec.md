# change-completion Specification

## Purpose
Archives specifications only after the approved final cross-repository code state satisfies the selected explicit completion policy.

## Requirements

### Requirement: Explicit completion policy
The system SHALL enforce merged_commits by default and require explicit selection and confirmation for validated_commits.

#### Scenario: Unaccepted code
- **WHEN** required commits are not accepted under the selected policy
- **THEN** archive preflight fails.

### Requirement: Partial merge block
The system SHALL preserve partial_merge and block archive while any required repository remains unaccepted or final verification is stale.

#### Scenario: Only one repository merged
- **WHEN** repository A is accepted but repository B failed
- **THEN** the coordinator retains both results and refuses archive.

### Requirement: Archive reconciliation
The system SHALL record archive intent and before state, verify resulting specifications and paths, and reconcile an unknown outcome before another archive attempt.

#### Scenario: Archive succeeded without receipt
- **WHEN** the process exits after archive but before recording completion
- **THEN** recovery proves the actual result and records it without applying deltas again.

#### Scenario: Mixed archive state
- **WHEN** active and archived paths or specification baselines conflict
- **THEN** the coordinator preserves evidence and blocks automatic replay.
