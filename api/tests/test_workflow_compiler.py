"""Critical workflow compiler validation gates for Studio definitions."""

from __future__ import annotations

import pytest

from api.services.workflow_compiler import (
    WorkflowDefinitionError,
    validate_and_normalize_definition,
)


def agent_executor(executor_ref: str) -> dict[str, str]:
    return {"kind": "agent", "ref": executor_ref}


def test_validate_rejects_empty_steps():
    with pytest.raises(WorkflowDefinitionError, match="non-empty"):
        validate_and_normalize_definition({"name": "x", "steps": []})


def test_validate_rejects_non_object_definition():
    with pytest.raises(WorkflowDefinitionError, match="definition must be an object"):
        validate_and_normalize_definition([])  # type: ignore[arg-type]


def test_validate_rejects_unknown_executor():
    with pytest.raises(WorkflowDefinitionError, match="unknown executor"):
        validate_and_normalize_definition(
            {
                "steps": [
                    {
                        "id": "1",
                        "type": "step",
                        "executor": agent_executor("not-real"),
                    }
                ]
            }
        )


def test_validate_rejects_confirmation_inside_parallel():
    with pytest.raises(WorkflowDefinitionError, match="forbidden inside Parallel"):
        validate_and_normalize_definition(
            {
                "steps": [
                    {
                        "id": "fanout",
                        "type": "parallel",
                        "steps": [
                            {
                                "id": "a",
                                "type": "step",
                                "executor": agent_executor("security-operations"),
                                "requires_confirmation": True,
                            },
                            {
                                "id": "b",
                                "type": "step",
                                "executor": agent_executor("safe-fallback"),
                            },
                        ],
                    }
                ]
            }
        )


def test_forbid_self_workflow_ref_at_normalize():
    with pytest.raises(
        WorkflowDefinitionError, match="cannot reference the current workflow"
    ):
        validate_and_normalize_definition(
            {
                "name": "self",
                "steps": [
                    {
                        "id": "nest",
                        "type": "workflow_ref",
                        "workflow_id": "wf-self",
                    },
                    {
                        "id": "leaf",
                        "type": "step",
                        "executor": agent_executor("safe-fallback"),
                    },
                ],
            },
            forbid_self_workflow_id="wf-self",
        )


def test_validate_accepts_minimal_linear_workflow():
    normalized = validate_and_normalize_definition(
        {
            "name": "linear",
            "description": "minimal happy path",
            "steps": [
                {
                    "id": "triage",
                    "type": "step",
                    "name": "Triage",
                    "executor": agent_executor("security-operations"),
                },
                {
                    "id": "report",
                    "type": "step",
                    "executor": agent_executor("safe-fallback"),
                },
            ],
        }
    )
    assert normalized["name"] == "linear"
    assert len(normalized["steps"]) == 2
    assert normalized["steps"][0]["type"] == "step"
    assert normalized["steps"][0]["executor"]["ref"] == "security-operations"
    assert normalized["steps"][1]["id"] == "report"
