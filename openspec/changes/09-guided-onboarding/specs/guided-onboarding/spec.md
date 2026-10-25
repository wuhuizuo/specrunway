# guided-onboarding Specification

## Purpose

Provides a deterministic interactive onboarding path that turns a control
directory and a short change description into validated SpecRunway inputs,
without requiring the operator to hand-author machine wiring or request files.

## ADDED Requirements

### Requirement: Guided control configuration

The CLI SHALL provide an interactive wizard that collects stable control wiring, validates it, writes `local.yaml` atomically, and runs the existing idempotent init flow.

#### Scenario: Fresh control checkout
- **WHEN** a user runs `specrunway wizard` in a directory without `local.yaml` and supplies Store, repository, remote-identity, and agent answers
- **THEN** the wizard writes a valid wiring-only control configuration, initializes the Store and Specify workspace, and reports the planned change or the configuration-only result.

#### Scenario: Existing configuration
- **WHEN** a valid `local.yaml` already exists and the user runs the wizard without `--reconfigure`
- **THEN** the wizard preserves the file and proceeds to the request phase.

#### Scenario: Change-specific decisions deferred
- **WHEN** an operator does not yet know a monorepo test command, a repository dependency, or whether a combined check exists
- **THEN** the configuration phase does not ask for or invent those values.

#### Scenario: Control checkout is inside Git
- **WHEN** the control directory is itself a Git checkout or sits inside one
- **THEN** the wizard proposes a Store path outside that checkout and rejects a nested Store path with a corrective hint.

#### Scenario: Invalid repository input
- **WHEN** a supplied repository path is missing, is not a Git checkout, or has an unusable remote identity
- **THEN** the wizard fails with a stable error before writing configuration or planning artifacts.

#### Scenario: Overwrite refusal
- **WHEN** a generated request or manifest already exists and the operator declines replacement
- **THEN** the wizard leaves the existing files unchanged and does not plan.

### Requirement: Guided change request

The wizard SHALL derive change id, participating repositories, execution order, dependencies, test profiles, optional integration, request sections, task text, and routing from a short description plus bounded follow-up answers, and SHALL hand the artifacts to the existing plan command.

#### Scenario: Request generation
- **WHEN** an operator selects participating repositories and supplies task text
- **THEN** the wizard writes a structured request and manifest, assigns stable task ids in the selected order, and invokes plan without starting implementation.

#### Scenario: Independent repositories
- **WHEN** the operator leaves a repository with no dependency answer
- **THEN** the manifest records no dependency for it instead of assuming the previous repository.

#### Scenario: Monorepo test command
- **WHEN** a participating repository needs a module-specific test command
- **THEN** the wizard records that command as a change-scoped test profile and the manifest references it.

#### Scenario: No combined check
- **WHEN** the operator states that the change has no combined integration check
- **THEN** the wizard writes a manifest without `integration_profile` and does not create a placeholder command or receipt.

#### Scenario: Repeat use
- **WHEN** the operator runs the wizard again for a different change
- **THEN** the existing configuration is reused and a new request is created without re-running configuration prompts.

#### Scenario: No task text
- **WHEN** any participating repository receives no task text
- **THEN** the wizard refuses to write a manifest that lacks task routing.

#### Scenario: JSON mode
- **WHEN** `--json` is requested
- **THEN** interactive prompts use stderr and stdout contains only the final `specrunway/v1` envelope.

### Requirement: Configured default routing

When `plan` receives a request without an explicit manifest, it SHALL derive routing from the repositories and profiles declared in the control configuration.

#### Scenario: Real repository names
- **WHEN** a control checkout declares repositories other than the fixture names and runs plan without `--manifest`
- **THEN** the generated manifest uses those declared repository ids and order.

#### Scenario: Unknown task mapping
- **WHEN** the request task labels cannot be routed to the declared repositories
- **THEN** plan fails with the existing routing error instead of producing a fixture-name manifest.
