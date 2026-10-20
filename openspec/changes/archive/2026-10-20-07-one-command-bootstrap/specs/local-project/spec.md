# Spec Delta

## Purpose

Closes the bootstrap gap in the archived local-project baseline so an
installed user can prepare a control checkout without invoking upstream CLIs
directly.

## ADDED Requirements

### Requirement: One-command control bootstrap
The CLI SHALL provide an idempotent `init` command that validates the
machine-only control configuration, registers the Store, initializes the
Specify workspace inside the control checkout, installs the bundled
SpecRunway step, and reports diagnostics.

#### Scenario: Fresh control checkout
- **WHEN** a user with `local.yaml` and pinned upstream tools runs `specrunway init`
- **THEN** the Store is registered, `.specify` exists, and the `specrunway` step is installed without any other upstream command typed by the user.

#### Scenario: Repeated init
- **WHEN** `specrunway init` runs again on an initialized control checkout
- **THEN** it succeeds without regenerating the Specify workspace or duplicating steps.

#### Scenario: Missing configuration
- **WHEN** `local.yaml` is absent or invalid
- **THEN** `init` fails with a stable code and does not write outside the control checkout.

### Requirement: Bundled step package
The installed distribution SHALL include the `specrunway` step shim so step installation works from a wheel without a source checkout.

#### Scenario: Wheel installation
- **WHEN** the wheel is installed in a fresh environment
- **THEN** the step metadata and handler are available as package data and `init` installs them.

### Requirement: Idempotent Store registration
Archive SHALL ensure the configured Store is registered before applying specification deltas.

#### Scenario: Unregistered Store at archive time
- **WHEN** the Store was not registered when the execution finished
- **THEN** archive registers it idempotently and proceeds, or fails with a clear upstream error without losing evidence.
