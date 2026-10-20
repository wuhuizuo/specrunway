# local-release Specification

## Purpose
Demonstrates that an independently installed local distribution satisfies every required v1 acceptance case and supports human operation.

## Requirements

### Requirement: Installed distribution acceptance
The local v1 release SHALL pass all V1-A01 through V1-A14 cases using the installed distribution and pinned upstream tools.

#### Scenario: Missing live-agent evidence
- **WHEN** the real agent profile has not completed the required two-repository demonstration
- **THEN** release remains blocked even when deterministic fixture tests pass.

### Requirement: Reproducible operational replays
The release SHALL retain normal, deliberate failure and repair, and abnormal recovery replays plus a backup and restore procedure.

#### Scenario: Fresh operator setup
- **WHEN** an implementer follows the documented installation and runbook in a new directory
- **THEN** the supported workflow and takeover procedures can be reproduced.

### Requirement: Portable contract evidence
Shared execution summaries SHALL retain stable IDs, schema versions, relative artifact references, and content digests without credentials or machine checkout paths.

#### Scenario: Portable data inspection
- **WHEN** the release fixture is exported for review
- **THEN** its shared metadata contains no secret or absolute machine checkout path.
