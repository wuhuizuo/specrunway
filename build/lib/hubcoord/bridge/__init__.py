"""Production ``type: hub`` step bridge (L10 task 5.1).

One step package for Specify: ``HubStep`` maps a workflow step configuration
to a typed dispatch of hub coordinator functions. It never mutates private
Specify engine state, never interpolates agent output into a shell command,
and returns the standardized hub/v1 envelope as ``output.data``.
"""

from __future__ import annotations

from specify_cli.workflows.base import (
    StepBase,
    StepContext,
    StepResult,
    StepStatus,
)
from specify_cli.workflows.expressions import evaluate_expression

from .actions import HubActionError, dispatch_action, envelope


class HubStep(StepBase):
    """Specify step type ``hub`` bridging to local coordinator actions."""

    type_key = "hub"

    def execute(self, config: dict, context: StepContext) -> StepResult:
        resolved = {
            key: (
                evaluate_expression(value, context)
                if isinstance(value, str) and "{{" in value
                else value
            )
            for key, value in config.items()
        }
        errors = self._validate_action(resolved)
        if errors:
            raise ValueError("; ".join(errors))
        action = str(resolved.get("action") or "unknown")
        try:
            result = dispatch_action(action, resolved, context)
        except HubActionError as exc:
            return StepResult(status=StepStatus.FAILED, error=exc.message, output=exc.output)
        return StepResult(status=StepStatus.COMPLETED, output=result)

    def validate(self, config: dict) -> list:
        return self._validate_action(config)

    def _validate_action(self, config: dict) -> list:
        errors = super().validate(config)
        if "action" not in config:
            errors.append("Hub step is missing 'action' field.")
        return errors


__all__ = ["HubActionError", "HubStep", "envelope"]
