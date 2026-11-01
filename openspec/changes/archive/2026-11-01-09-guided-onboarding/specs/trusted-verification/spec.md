# Spec Delta

## Purpose

Clarifies that a central change with independent repositories may complete
without a combined integration command, while every declared integration
profile keeps the existing resolve, freeze, run, and gate behavior.

## MODIFIED Requirements

### Requirement: Combined commit matrix

Global verification SHALL identify the accepted commit and artifact for every participating repository and execute the configured integration profile when the manifest declares one. When no profile is declared, completion SHALL rely on per-repository trusted verification and SHALL NOT record a synthetic combined receipt.

#### Scenario: Repository tests pass but integration fails
- **WHEN** the manifest declares an integration profile, all local tests pass, and the combined acceptance check fails
- **THEN** global completion remains blocked.

#### Scenario: No integration profile
- **WHEN** the manifest omits `integration_profile` because the participating repositories are independent
- **THEN** completion still requires every per-repository result and trusted verification to pass, and no integration receipt is claimed.

### Requirement: Frozen integration profile

The coordinator SHALL resolve the manifest's integration profile from trusted control configuration and freeze its argv, working repository, timeout, and digest in the execution snapshot before executing any agent when a profile is declared.

#### Scenario: Unknown integration profile
- **WHEN** the manifest names a profile absent from the control checkout
- **THEN** execution is refused before repository work starts.

#### Scenario: Profile edited after freeze
- **WHEN** the control configuration changes after the snapshot was frozen
- **THEN** the frozen argv and digest remain authoritative for that execution.

#### Scenario: No declared profile
- **WHEN** the manifest has no integration profile
- **THEN** the snapshot contains no integration row and execution starts without resolving a combined command.
