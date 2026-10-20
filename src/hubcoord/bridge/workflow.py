"""Deterministic workflow generation for an execution.

The generated YAML only wires trusted steps: hub steps delegate business rules
to the coordinator, and native gates pause for operator approval receipts.
"""

from __future__ import annotations

import yaml


def workflow_id_for(execution_id: str) -> str:
    return f"run-{execution_id[:8]}"


def build_workflow(execution_id: str, change_id: str) -> dict:
    """Ordered two-repository workflow: plan gate, fan-out, review, accept."""
    return {
        "schema_version": "1.0",
        "workflow": {
            "id": workflow_id_for(execution_id),
            "name": f"Hub execution for {change_id}",
            "version": "1.0.0",
        },
        "inputs": {
            "execution": {"type": "string", "required": True},
            "control_root": {"type": "string", "required": True},
            "plan_verdict": {"type": "string", "default": ""},
            "implementation_verdict": {"type": "string", "default": ""},
        },
        "steps": [
            {
                "id": "prepare",
                "type": "hub",
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
                    "type": "hub",
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
                "type": "hub",
                "action": "verify-round",
                "root": "{{ inputs.control_root }}",
                "execution": "{{ inputs.execution }}",
                "round": 1,
            },
            {
                "id": "accept-tasks",
                "type": "hub",
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
                "type": "hub",
                "action": "complete",
                "root": "{{ inputs.control_root }}",
                "execution": "{{ inputs.execution }}",
            },
        ],
    }


def build_workflow_yaml(execution_id: str, change_id: str) -> str:
    return yaml.safe_dump(
        build_workflow(execution_id, change_id),
        sort_keys=False,
        default_flow_style=False,
    )


__all__ = ["build_workflow", "build_workflow_yaml", "workflow_id_for"]
