from api.services.workflow_definition_migration import canonicalize_workflow_definition
from uuid import UUID


def test_canonicalize_workflow_definition_rewrites_nested_legacy_keys() -> None:
    legacy = {
        "name": "Legacy workflow",
        "steps": [
            {
                "id": "triage",
                "type": "step",
                "kind": "agent",
                "targetId": "security-operations",
            },
            {
                "id": "branch",
                "type": "condition",
                "evaluator": {"cel": "true"},
                "then_steps": [
                    {
                        "id": "retry",
                        "type": "loop",
                        "maxIterations": 4,
                        "endCondition": {"cel": "current_iteration >= 1"},
                        "steps": [
                            {
                                "id": "retry-step",
                                "type": "step",
                                "target_id": "safe-fallback",
                            }
                        ],
                    }
                ],
                "else_steps": [
                    {
                        "id": "nested",
                        "type": "workflow_ref",
                        "workflowId": "workflow-2",
                    }
                ],
            },
        ],
    }

    migrated = canonicalize_workflow_definition(legacy)

    assert migrated is not None
    step = migrated["steps"][0]
    assert step["executor"] == {"kind": "agent", "ref": "security-operations"}
    assert "targetId" not in step
    assert "kind" not in step

    condition = migrated["steps"][1]
    assert "then_steps" not in condition
    assert "else_steps" not in condition
    assert "then" not in condition
    loop = condition["steps"][0]
    assert loop["max_iterations"] == 4
    assert loop["end_condition"] == {"cel": "current_iteration >= 1"}
    assert "maxIterations" not in loop
    assert "endCondition" not in loop
    assert loop["steps"][0]["executor"] == {"kind": "agent", "ref": "safe-fallback"}
    assert condition["else"][0]["workflow_id"] == "workflow-2"
    assert "workflowId" not in condition["else"][0]

    assert canonicalize_workflow_definition(migrated) == migrated


def test_canonicalize_workflow_definition_prefers_current_condition_steps() -> None:
    definition = {
        "steps": [
            {
                "id": "step",
                "type": "step",
                "executor": {"kind": "agent", "ref": "safe-fallback"},
                "targetId": "security-operations",
            },
            {
                "id": "condition",
                "type": "condition",
                "evaluator": {"cel": "true"},
                "steps": [{"id": "current", "type": "step", "targetId": "safe-fallback"}],
                "then": [{"id": "old", "type": "step", "targetId": "security-operations"}],
                "then_steps": [{"id": "ignored", "type": "step", "targetId": "security-operations"}],
                "else": [],
            },
        ]
    }

    migrated = canonicalize_workflow_definition(definition)

    assert migrated is not None
    assert migrated["steps"][0]["executor"] == {"kind": "agent", "ref": "safe-fallback"}
    assert migrated["steps"][1]["steps"][0]["id"] == "current"
    assert "then" not in migrated["steps"][1]
    assert "then_steps" not in migrated["steps"][1]


def test_canonicalize_workflow_definition_ignores_non_objects() -> None:
    assert canonicalize_workflow_definition(None) is None
    assert canonicalize_workflow_definition([]) is None


def test_canonicalize_workflow_definition_backfills_missing_ids_stably() -> None:
    definition = {
        "steps": [
            {
                "id": "fanout",
                "type": "parallel",
                "steps": [{"type": "step", "executor": {"ref": "security-operations"}}],
            },
            {
                "type": "router",
                "choices": [
                    {
                        "id": "",
                        "name": "path_a",
                        "steps": [{"type": "step", "executor": {"ref": "security-operations"}}],
                    },
                    {
                        "name": "path_b",
                        "steps": [{"type": "step", "executor": {"ref": "safe-fallback"}}],
                    },
                ],
            },
        ]
    }

    migrated = canonicalize_workflow_definition(definition)

    assert migrated is not None
    assert migrated["steps"][0]["id"] == "fanout"
    assert migrated["steps"][0]["steps"][0]["type"] == "step"
    generated_ids = [
        migrated["steps"][0]["steps"][0]["id"],
        migrated["steps"][1]["id"],
        migrated["steps"][1]["choices"][0]["id"],
        migrated["steps"][1]["choices"][0]["steps"][0]["id"],
        migrated["steps"][1]["choices"][1]["id"],
        migrated["steps"][1]["choices"][1]["steps"][0]["id"],
    ]
    assert len(set(generated_ids)) == len(generated_ids)
    for generated_id in generated_ids:
        UUID(generated_id)
    assert canonicalize_workflow_definition(migrated) == migrated


def test_canonicalize_workflow_definition_adds_empty_condition_else_branch() -> None:
    migrated = canonicalize_workflow_definition(
        {
            "steps": [
                {
                    "id": "condition",
                    "type": "condition",
                    "evaluator": {"cel": "true"},
                    "steps": [
                        {
                            "id": "then",
                            "type": "step",
                            "executor": {"ref": "security-operations"},
                        }
                    ],
                }
            ]
        }
    )

    assert migrated is not None
    assert migrated["steps"][0]["else"] == []
