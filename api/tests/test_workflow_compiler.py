import pytest

from api.services.workflow_compiler import (
    WorkflowDefinitionError,
    list_executor_options,
    validate_and_normalize_definition,
)


def test_executor_catalog_includes_builtin_agents():
    refs = {item["ref"] for item in list_executor_options()}
    assert "security-operations" in refs
    assert "safe-fallback" in refs


def test_validate_linear_definition_normalizes_legacy_fields():
    normalized = validate_and_normalize_definition(
        {
            "name": "IR",
            "description": "triage then report",
            "steps": [
                {
                    "id": "triage",
                    "kind": "agent",
                    "targetId": "security-operations",
                    "name": "Triage",
                    "instructions": "classify",
                }
            ],
        }
    )
    assert normalized["steps"][0]["executor"] == {
        "kind": "agent",
        "ref": "security-operations",
    }
    assert normalized["steps"][0]["type"] == "step"


def test_validate_rejects_empty_steps():
    with pytest.raises(WorkflowDefinitionError, match="non-empty"):
        validate_and_normalize_definition({"name": "x", "steps": []})


def test_validate_rejects_unknown_executor():
    with pytest.raises(WorkflowDefinitionError, match="unknown executor"):
        validate_and_normalize_definition(
            {
                "steps": [
                    {
                        "id": "1",
                        "executor": {"kind": "agent", "ref": "not-real"},
                    }
                ]
            }
        )


def test_validate_rejects_non_linear_types():
    with pytest.raises(WorkflowDefinitionError, match="not supported in PR1"):
        validate_and_normalize_definition(
            {"steps": [{"id": "1", "type": "parallel", "executor": {"ref": "security-operations"}}]}
        )
