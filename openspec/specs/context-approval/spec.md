# context-approval Specification

## Purpose
Binds local plan and implementation decisions to the exact frozen content and code evidence reviewed by the operator.

## Requirements

### Requirement: Frozen context
The system SHALL freeze planning, rules, referenced specifications, repository base commits, and tool/profile identities for an execution.

#### Scenario: Changed approved input
- **WHEN** planning text or an applicable rule changes after approval
- **THEN** the existing approval cannot authorize the changed content.

### Requirement: Checkbox normalization
The planning digest SHALL exclude checkbox completion markers while including task wording, routing, dependencies, and acceptance criteria.

#### Scenario: Checkbox only change
- **WHEN** only a task completion marker changes
- **THEN** the planning digest remains unchanged.

#### Scenario: Task text change
- **WHEN** a task description changes
- **THEN** the planning digest changes.

### Requirement: Local approval provenance
The system SHALL record local approvals as self_asserted and require a matching scope and subject digest before advancing its review gate.

#### Scenario: Injected verdict
- **WHEN** a caller supplies an approve verdict without a matching receipt
- **THEN** the coordinator refuses to advance.

### Requirement: Review completion boundary
A successful reviewed run SHALL finish at ready_for_review while leaving code acceptance and specification archive as explicit later operations.

#### Scenario: Tests turn green
- **WHEN** implementation and integration verification pass
- **THEN** the run still requires the configured human review and does not archive automatically.
