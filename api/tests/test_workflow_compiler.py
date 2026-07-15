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


def test_validate_parallel_condition_loop():
    normalized = validate_and_normalize_definition(
        {
            "name": "nested",
            "steps": [
                {
                    "id": "fanout",
                    "type": "parallel",
                    "name": "Fan-out",
                    "steps": [
                        {
                            "id": "cve",
                            "type": "step",
                            "executor": {"ref": "security-operations"},
                            "name": "CVE",
                        },
                        {
                            "id": "asset",
                            "type": "step",
                            "executor": {"ref": "safe-fallback"},
                            "name": "Asset",
                        },
                    ],
                },
                {
                    "id": "branch",
                    "type": "condition",
                    "name": "Branch",
                    "evaluator": {"cel": 'input.contains("critical")'},
                    "then": [
                        {
                            "id": "contain",
                            "type": "step",
                            "executor": {"ref": "security-operations"},
                        }
                    ],
                    "else": [
                        {
                            "id": "report",
                            "type": "step",
                            "executor": {"ref": "safe-fallback"},
                        }
                    ],
                },
                {
                    "id": "retry",
                    "type": "loop",
                    "name": "Retry",
                    "max_iterations": 2,
                    "end_condition": {"cel": "current_iteration >= 1"},
                    "steps": [
                        {
                            "id": "probe",
                            "type": "step",
                            "executor": {"ref": "safe-fallback"},
                        }
                    ],
                },
            ],
        }
    )
    assert normalized["steps"][0]["type"] == "parallel"
    assert len(normalized["steps"][0]["steps"]) == 2
    assert normalized["steps"][1]["evaluator"] == {"cel": 'input.contains("critical")'}
    assert normalized["steps"][2]["max_iterations"] == 2
    assert normalized["steps"][2]["end_condition"] == {"cel": "current_iteration >= 1"}


def test_validate_rejects_invalid_cel():
    with pytest.raises(WorkflowDefinitionError, match="invalid CEL"):
        validate_and_normalize_definition(
            {
                "steps": [
                    {
                        "id": "branch",
                        "type": "condition",
                        "evaluator": {"cel": "input.!!!!"},
                        "then": [
                            {
                                "id": "a",
                                "type": "step",
                                "executor": {"ref": "security-operations"},
                            }
                        ],
                    }
                ]
            }
        )


def test_validate_rejects_parallel_with_one_child():
    with pytest.raises(WorkflowDefinitionError, match="at least 2"):
        validate_and_normalize_definition(
            {
                "steps": [
                    {
                        "id": "fanout",
                        "type": "parallel",
                        "steps": [
                            {
                                "id": "only",
                                "type": "step",
                                "executor": {"ref": "security-operations"},
                            }
                        ],
                    }
                ]
            }
        )


def test_validate_rejects_duplicate_ids_across_tree():
    with pytest.raises(WorkflowDefinitionError, match="duplicate node id"):
        validate_and_normalize_definition(
            {
                "steps": [
                    {
                        "id": "fanout",
                        "type": "parallel",
                        "steps": [
                            {
                                "id": "same",
                                "type": "step",
                                "executor": {"ref": "security-operations"},
                            },
                            {
                                "id": "same",
                                "type": "step",
                                "executor": {"ref": "safe-fallback"},
                            },
                        ],
                    }
                ]
            }
        )


def test_validate_rejects_unknown_type():
    with pytest.raises(WorkflowDefinitionError, match="not supported"):
        validate_and_normalize_definition(
            {
                "steps": [
                    {
                        "id": "r",
                        "type": "router",
                        "executor": {"ref": "security-operations"},
                    }
                ]
            }
        )
