# Spec Delta

## Purpose

Keeps local execution state readable and external operations traceable despite concurrent commands or interrupted file writes.

## ADDED Requirements

### Requirement: One active execution
The system SHALL allow only one active execution to mutate a given control and Store checkout.

#### Scenario: Second writer
- **WHEN** another execution attempts to mutate the owned checkout
- **THEN** it is refused while the original ownership record remains.

### Requirement: Atomic state replacement
The system SHALL replace committed JSON state atomically and check the expected revision before updating it.

#### Scenario: Interrupted state write
- **WHEN** the process exits while writing a temporary state file
- **THEN** the previously committed state remains parseable.

### Requirement: Side effect intent
The system SHALL write a stable operation intent before a recoverable external side effect and reconcile an unknown outcome before retrying.

#### Scenario: Effect without receipt
- **WHEN** an effect completes before the receipt is committed
- **THEN** recovery inspects actual external state and does not blindly repeat the effect.
