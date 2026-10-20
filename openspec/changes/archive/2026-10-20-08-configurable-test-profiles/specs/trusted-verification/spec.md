# Spec Delta

## Purpose

Closes the test-command expressiveness gap in the archived
trusted-verification baseline so real non-Python repositories can be verified
through trusted, frozen commands.

## ADDED Requirements

### Requirement: Control-declared test profiles
The control checkout SHALL allow named test profiles with an argv command, an optional relative working directory inside the worktree, and a timeout.

#### Scenario: Tests in a subdirectory
- **WHEN** a repository keeps its tests in a subdirectory and the profile sets that relative cwd
- **THEN** the trusted runner executes the command there and records the receipt.

#### Scenario: Unsafe profile
- **WHEN** a profile uses an absolute cwd, a parent traversal, or an empty argv
- **THEN** configuration validation fails before any execution exists.

### Requirement: Frozen test profiles
Execution SHALL freeze every referenced test profile (argv, cwd, timeout, digest) in the snapshot, and verification SHALL use the frozen profile.

#### Scenario: Profile edited after freeze
- **WHEN** the control configuration changes after the snapshot was frozen
- **THEN** the execution keeps using the frozen command.

#### Scenario: Unknown profile
- **WHEN** the manifest references a profile that neither configuration nor the built-in registry defines
- **THEN** execution is refused before agent work starts.

#### Scenario: Legacy snapshot
- **WHEN** a snapshot lacks frozen test profiles
- **THEN** the built-in `unit` profile remains the fallback for compatibility.
