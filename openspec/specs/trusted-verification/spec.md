# trusted-verification Specification

## Purpose
Uses independently executed tests and bounded repair to decide whether the actual repository commit matrix satisfies a central change.

## Requirements

### Requirement: Trusted test execution
The trusted runner SHALL execute configured test argv against recorded commits rather than accept agent-authored success claims.

#### Scenario: Claim without test
- **WHEN** the agent reports green tests without a trusted receipt
- **THEN** the result is not accepted as verified.

### Requirement: Persistent repair limits
The system SHALL persist per-repository and integration repair counters and stop when configured attempts, time, or no-progress limits are reached.

#### Scenario: Resume after repair
- **WHEN** a failed run resumes
- **THEN** it retains consumed attempts and cannot reset its budget.

### Requirement: Combined commit matrix
Global verification SHALL identify the accepted commit and artifact for every participating repository and execute the configured integration profile against that matrix.

#### Scenario: Repository tests pass but integration fails
- **WHEN** all local tests pass while a combined acceptance check fails
- **THEN** global completion remains blocked.

### Requirement: Failure classification
The workflow SHALL distinguish an ordinary failed test eligible for repair from launch, protocol, or exhausted-budget failure.

#### Scenario: Ordinary test failure
- **WHEN** a test completes with a failing result within budget
- **THEN** the workflow can provide exact feedback to a bounded repair round.

### Requirement: Frozen integration profile
The coordinator SHALL resolve the manifest's integration profile from trusted control configuration and freeze its argv, working repository, timeout, and digest in the execution snapshot before executing any agent.

#### Scenario: Unknown integration profile
- **WHEN** the manifest names a profile absent from the control checkout
- **THEN** execution is refused before repository work starts.

#### Scenario: Profile edited after freeze
- **WHEN** the control configuration changes after the snapshot was frozen
- **THEN** the frozen argv and digest remain authoritative for that execution.

### Requirement: Combined matrix execution
Global verification SHALL write the accepted commit matrix, run the frozen integration command against it, and persist a trusted integration receipt.

#### Scenario: Repository tests pass but integration fails
- **WHEN** every per-repository result and trusted test passes while the integration command exits non-zero
- **THEN** the execution cannot reach ready_for_review.

#### Scenario: Integration passes
- **WHEN** the integration command exits zero for the accepted matrix
- **THEN** the integration receipt binds the matrix digest and completion may proceed.

### Requirement: Persistent integration repair budget
Integration repairs SHALL be bounded by integration_max_repairs, persist consumed rounds in run state, reuse explicit failure feedback, and stop on no-progress or exhaustion.

#### Scenario: Repeated identical failure
- **WHEN** the same matrix head fails the integration command with the same failure signature again
- **THEN** the coordinator stops as no-progress instead of consuming remaining rounds.

#### Scenario: Resume after integration repair
- **WHEN** a run is resumed or recovered after consumed integration rounds
- **THEN** the remaining budget reflects the persisted count and cannot reset.
