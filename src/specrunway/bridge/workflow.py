"""Deterministic workflow generation for an execution.

The generated YAML only wires trusted steps: specrunway steps delegate business rules
to the coordinator, and native gates pause for operator approval receipts.
"""

from __future__ import annotations

import yaml


def workflow_id_for(execution_id: str) -> str:
    return f"run-{execution_id[:8]}"


def build_workflow(
    execution_id: str, change_id: str, has_integration: bool = True
) -> dict:
    """Ordered two-repository workflow: plan gate, fan-out, review, accept."""
    steps = [
        {
            "id": "prepare",
            "type": "specrunway",
            "action": "prepare",
            "root": "{{ inputs.control_root }}",
            "execution": "{{ inputs.execution }}",
        },
        {
            "id": "plan-gate",
            "type": "gate",
            "message": "Confirm the recorded plan review receipt binds the frozen plan.",
            "options": ["approve", "reject"],
            "on_reject": "abort",
            "verdict_input": "plan_verdict",
        },
        {
            "id": "implement",
            "type": "fan-out",
            "items": "{{ steps.prepare.output.data.repos }}",
            "max_concurrency": 1,
            "step": {
                "id": "repo",
                "type": "specrunway",
                "action": "run-repo",
                "repo": "{{ item }}",
                "root": "{{ inputs.control_root }}",
                "execution": "{{ inputs.execution }}",
            },
        },
        {
            "id": "collect",
            "type": "fan-in",
            "wait_for": ["implement"],
        },
        {
            "id": "verify-round",
            "type": "specrunway",
            "action": "verify-round",
            "root": "{{ inputs.control_root }}",
            "execution": "{{ inputs.execution }}",
            "round": 1,
        },
        {
            "id": "repair-round",
            "type": "specrunway",
            "action": "repair-round",
            "root": "{{ inputs.control_root }}",
            "execution": "{{ inputs.execution }}",
        },
        {
            "id": "accept-tasks",
            "type": "specrunway",
            "action": "accept-tasks",
            "root": "{{ inputs.control_root }}",
            "execution": "{{ inputs.execution }}",
        },
        {
            "id": "implementation-gate",
            "type": "gate",
            "message": "Review the accepted implementation evidence.",
            "options": ["approve", "reject"],
            "on_reject": "abort",
            "verdict_input": "implementation_verdict",
        },
        {
            "id": "complete",
            "type": "specrunway",
            "action": "complete",
            "root": "{{ inputs.control_root }}",
            "execution": "{{ inputs.execution }}",
        },
    ]
    if has_integration:
        accept_index = next(
            index for index, step in enumerate(steps) if step["id"] == "accept-tasks"
        )
        steps.insert(
            accept_index,
            {
                "id": "integration-round",
                "type": "specrunway",
                "action": "integration-round",
                "root": "{{ inputs.control_root }}",
                "execution": "{{ inputs.execution }}",
            },
        )
    return {
        "schema_version": "1.0",
        "workflow": {
            "id": workflow_id_for(execution_id),
            "name": f"SpecRunway execution for {change_id}",
            "version": "1.0.0",
        },
        "inputs": {
            "execution": {"type": "string", "required": True},
            "control_root": {"type": "string", "required": True},
            "plan_verdict": {"type": "string", "default": ""},
            "implementation_verdict": {"type": "string", "default": ""},
        },
        "steps": steps,
    }


def build_workflow_yaml(
    execution_id: str, change_id: str, has_integration: bool = True
) -> str:
    return yaml.safe_dump(
        build_workflow(execution_id, change_id, has_integration=has_integration),
        sort_keys=False,
        default_flow_style=False,
    )


__all__ = ["build_workflow", "build_workflow_yaml", "workflow_id_for"]
