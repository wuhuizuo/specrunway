"""Hub bridge probe step for L01 compatibility probes.

Exports a StepBase subclass whose ``type_key`` matches ``step.yml``. The class
delegates to functions in ``actions.py`` through a package-relative import so
the probe also proves multi-file package loading inside the Specify runtime.
"""

from __future__ import annotations

from specify_cli.workflows.base import (
    StepBase,
    StepContext,
    StepResult,
    StepStatus,
)
from specify_cli.workflows.expressions import evaluate_expression

from .actions import _FailedAction, dispatch_action, envelope


class HubStep(StepBase):
    """Map a workflow step of type ``hub`` to a typed local action."""

    type_key = "hub"

    def execute(self, config: dict, context: StepContext) -> StepResult:
        real_config = {
            key: (
                evaluate_expression(value, context)
                if isinstance(value, str) and "{{" in value
                else value
            )
            for key, value in config.items()
        }
        errors = super().validate(real_config)
        if errors:
            raise ValueError("; ".join(errors))
        action = str(real_config.get("action") or "unknown")
        try:
            result = dispatch_action(action, real_config, context)
        except _FailedAction as exc:
            return StepResult(
                status=StepStatus.FAILED,
                error=exc.message,
                output=exc.output,
            )
        return StepResult(status=StepStatus.COMPLETED, output=result)

    def validate(self, config: dict) -> list:
        errors = super().validate(config)
        if "action" not in config:
            errors.append("Hub step is missing 'action' field.")
        return errors


__all__ = ["HubStep", "envelope"]
