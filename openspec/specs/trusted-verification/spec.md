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
