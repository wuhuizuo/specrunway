# execution-recovery Specification

## Purpose
Resumes local execution through verified receipts and native runtime contracts while avoiding duplicate work after abnormal process exit.

## Requirements

### Requirement: Normal native resume
The system SHALL use the supported Specify resume contract for paused or failed runs and retain valid completed results.

#### Scenario: Paused gate resumed
- **WHEN** the local approval and frozen inputs remain valid
- **THEN** execution continues without rerunning verified completed work.

### Requirement: Orphan running recovery
The system SHALL confirm child termination and reconcile receipts before replacing an orphan running native run with a new native run under the same business execution.

#### Scenario: Native status running
- **WHEN** an interrupted native run cannot be resumed
- **THEN** the coordinator preserves it for diagnosis and never force-edits its private status.

### Requirement: Verified receipt reuse
Recovery SHALL reuse an external operation only when its stable operation key and actual Git or artifact evidence still match.

#### Scenario: Stale receipt
- **WHEN** a referenced result file or commit no longer matches
- **THEN** recovery blocks reuse and reports the evidence conflict.
