# local-project Specification

## Purpose
Provides one locally installed command package and central configuration while preserving existing business repositories.

## Requirements

### Requirement: Standalone local invocation
The system SHALL provide its local CLI without requiring a network service, database, broker, account system, or team backend.

#### Scenario: Fresh local setup
- **WHEN** the required package and pinned external tools are installed
- **THEN** the CLI can locate its central configuration and run diagnostics locally.

### Requirement: Central tool configuration
The system SHALL keep tool initialization and machine-specific repository mappings in the central control workspace.

#### Scenario: Business repositories unchanged
- **WHEN** the coordinator is configured for two existing repositories
- **THEN** no tool initialization is required in their original checkouts.

### Requirement: Typed OpenSpec operations
The system SHALL invoke OpenSpec with explicit Store selection and argv arguments and SHALL reject unsupported critical response data.

#### Scenario: Invalid planning response
- **WHEN** OpenSpec returns malformed or unsupported critical JSON
- **THEN** the operation fails with a diagnostic and no implementation is accepted.
