# Spec Delta

## Purpose

Records reproducible upstream compatibility evidence so implementation and release decisions use measured tool contracts.

## ADDED Requirements

### Requirement: Exact upstream identities
The compatibility report SHALL identify exact OpenSpec and Specify versions, interpreter versions, and workflow and step implementation digests.

#### Scenario: Candidate release evaluated
- **WHEN** the compatibility probes run
- **THEN** the report records actual installed identities and each probe outcome rather than declaring the candidate supported in advance.

### Requirement: Control flow probes
The compatibility suite SHALL exercise a real installed custom step, non-TTY gates, sequential fan-out, bounded loops, and paused or failed resume at the pinned Specify release.

#### Scenario: Real step import
- **WHEN** the probe step executes inside the Specify environment
- **THEN** its package imports and output envelope are verified through the actual workflow command.

### Requirement: Store protocol probes
The compatibility suite SHALL distinguish OpenSpec planning status from implementation completion and verify explicit Store selection and malformed-response handling.

#### Scenario: Wrong Store or invalid response
- **WHEN** a selected root is incorrect or critical JSON is unsupported
- **THEN** the probe reports failure and prevents dependent production integration.

### Requirement: Interrupted run observation
The compatibility suite SHALL record native state and child-process behavior after abrupt exit without editing private engine state.

#### Scenario: Native run remains running
- **WHEN** a stopped workflow leaves native status running
- **THEN** the report records that normal resume is unavailable and documents the reconciliation path.
