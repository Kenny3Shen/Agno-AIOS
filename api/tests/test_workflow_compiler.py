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


def test_validate_requires_explicit_node_id():
    with pytest.raises(WorkflowDefinitionError, match=r"steps\[0\]\.id is required"):
        validate_and_normalize_definition(
            {
                "steps": [
                    {
                        "type": "step",
                        "executor": agent_executor("security-operations"),
                    }
                ]
            }
        )


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


def test_validate_requires_explicit_executor_kind():
    with pytest.raises(
        WorkflowDefinitionError,
        match=r"steps\[0\]\.executor\.kind is required",
    ):
        validate_and_normalize_definition(
            {
                "steps": [
                    {
                        "id": "step-1",
                        "type": "step",
                        "executor": {"ref": "security-operations"},
                    }
                ]
            }
        )


def test_validate_requires_explicit_node_type():
    with pytest.raises(WorkflowDefinitionError, match=r"steps\[0\]\.type is required"):
        validate_and_normalize_definition(
            {
                "steps": [
                    {
                        "id": "step-1",
                        "executor": agent_executor("security-operations"),
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
                            "executor": agent_executor("security-operations"),
                            "name": "CVE",
                        },
                        {
                            "id": "asset",
                            "type": "step",
                            "executor": agent_executor("safe-fallback"),
                            "name": "Asset",
                        },
                    ],
                },
                {
                    "id": "branch",
                    "type": "condition",
                    "name": "Branch",
                    "evaluator": {"cel": 'input.contains("critical")'},
                    "steps": [
                        {
                            "id": "contain",
                            "type": "step",
                            "executor": agent_executor("security-operations"),
                        }
                    ],
                    "else": [
                        {
                            "id": "report",
                            "type": "step",
                            "executor": agent_executor("safe-fallback"),
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
                            "executor": agent_executor("safe-fallback"),
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
                        "steps": [
                            {
                                "id": "a",
                                "type": "step",
                                "executor": agent_executor("security-operations"),
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
                                "executor": agent_executor("security-operations"),
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
                                "executor": agent_executor("security-operations"),
                            },
                            {
                                "id": "same",
                                "type": "step",
                                "executor": agent_executor("safe-fallback"),
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
                        "type": "unknown_widget",
                        "executor": agent_executor("security-operations"),
                    }
                ]
            }
        )


def test_validate_step_requires_confirmation():
    normalized = validate_and_normalize_definition(
        {
            "steps": [
                {
                    "id": "gate",
                    "type": "step",
                    "name": "Gate",
                    "executor": agent_executor("security-operations"),
                    "requires_confirmation": True,
                    "confirmation_message": "Proceed?",
                }
            ]
        }
    )
    assert normalized["steps"][0]["requires_confirmation"] is True
    assert normalized["steps"][0]["confirmation_message"] == "Proceed?"


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


def test_validate_router():
    normalized = validate_and_normalize_definition(
        {
            "name": "route",
            "steps": [
                {
                    "id": "r1",
                    "type": "router",
                    "name": "Route",
                    "selector": {"cel": 'input.contains("x") ? "path_a" : "path_b"'},
                    "choices": [
                        {
                            "id": "c1",
                            "name": "path_a",
                            "steps": [
                                {
                                    "id": "a",
                                    "type": "step",
                                    "executor": agent_executor("security-operations"),
                                }
                            ],
                        },
                        {
                            "id": "c2",
                            "name": "path_b",
                            "steps": [
                                {
                                    "id": "b",
                                    "type": "step",
                                    "executor": agent_executor("safe-fallback"),
                                }
                            ],
                        },
                    ],
                }
            ],
        }
    )
    assert normalized["steps"][0]["type"] == "router"
    assert len(normalized["steps"][0]["choices"]) == 2


def test_validate_router_requires_explicit_choice_id():
    with pytest.raises(
        WorkflowDefinitionError,
        match=r"steps\[0\]\.choices\[0\]\.id is required",
    ):
        validate_and_normalize_definition(
            {
                "steps": [
                    {
                        "id": "router",
                        "type": "router",
                        "selector": {"cel": 'input.contains("x") ? "path_a" : "path_b"'},
                        "choices": [
                            {
                                "name": "path_a",
                                "steps": [
                                    {
                                        "id": "a",
                                        "type": "step",
                                        "executor": agent_executor("security-operations"),
                                    }
                                ],
                            },
                            {
                                "id": "path_b",
                                "name": "path_b",
                                "steps": [
                                    {
                                        "id": "b",
                                        "type": "step",
                                        "executor": agent_executor("safe-fallback"),
                                    }
                                ],
                            },
                        ],
                    }
                ]
            }
        )


def test_validate_step_user_input_and_output_review():
    normalized = validate_and_normalize_definition(
        {
            "steps": [
                {
                    "id": "u",
                    "type": "step",
                    "executor": agent_executor("security-operations"),
                    "requires_user_input": True,
                    "user_input_message": "Provide IOC",
                    "requires_output_review": True,
                    "output_review_message": "Review report",
                }
            ]
        }
    )
    step = normalized["steps"][0]
    assert step["requires_user_input"] is True
    assert step["requires_output_review"] is True


def test_validate_workflow_ref():
    normalized = validate_and_normalize_definition(
        {
            "steps": [
                {
                    "id": "sub",
                    "type": "workflow_ref",
                    "name": "Child",
                    "workflow_id": "wf-other",
                }
            ]
        }
    )
    assert normalized["steps"][0]["workflow_id"] == "wf-other"


def test_step_skills_normalized_unique():
    normalized = validate_and_normalize_definition(
        {
            "name": "with-skills",
            "steps": [
                {
                    "id": "s1",
                    "type": "step",
                    "executor": agent_executor("security-operations"),
                    "skills": [" playbook-skill ", "cve-intel-skill", "playbook-skill", ""],
                }
            ],
        }
    )
    assert normalized["steps"][0]["skills"] == ["playbook-skill", "cve-intel-skill"]


def test_step_without_skills_omits_field():
    normalized = validate_and_normalize_definition(
        {
            "steps": [
                {
                    "id": "s1",
                    "type": "step",
                    "executor": agent_executor("safe-fallback"),
                }
            ],
        }
    )
    assert "skills" not in normalized["steps"][0]


def test_collect_workflow_skill_names_nested():
    from api.services.workflow_compiler import collect_workflow_skill_names

    names = collect_workflow_skill_names(
        {
            "steps": [
                {"type": "step", "skills": ["a"]},
                {
                    "type": "condition",
                    "steps": [{"type": "step", "skills": ["b", "a"]}],
                    "else": [{"type": "step", "skills": ["c"]}],
                },
            ]
        }
    )
    assert names == ["a", "b", "c"]



def test_user_input_schema_normalized():
    normalized = validate_and_normalize_definition(
        {
            "steps": [
                {
                    "id": "u",
                    "type": "step",
                    "executor": agent_executor("security-operations"),
                    "requires_user_input": True,
                    "user_input_schema": [
                        {"name": "severity", "type": "integer", "description": "1-5"},
                        {"key": "ack", "field_type": "boolean", "required": False},
                    ],
                }
            ]
        }
    )
    assert normalized["steps"][0]["user_input_schema"] == [
        {"name": "severity", "field_type": "number", "required": True, "description": "1-5"},
        {"name": "ack", "field_type": "bool", "required": False},
    ]


def test_user_input_schema_rejects_duplicate_names():
    with pytest.raises(WorkflowDefinitionError, match="duplicate field name"):
        validate_and_normalize_definition(
            {
                "steps": [
                    {
                        "id": "u",
                        "type": "step",
                        "executor": agent_executor("security-operations"),
                        "requires_user_input": True,
                        "user_input_schema": [
                            {"name": "x", "field_type": "str"},
                            {"name": "x", "field_type": "str"},
                        ],
                    }
                ]
            }
        )


def test_forbid_self_workflow_ref_at_normalize():
    with pytest.raises(WorkflowDefinitionError, match="cannot reference the current workflow"):
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


def test_forbid_self_workflow_ref_nested_condition():
    with pytest.raises(WorkflowDefinitionError, match="cannot reference the current workflow"):
        validate_and_normalize_definition(
            {
                "name": "nested-self",
                "steps": [
                    {
                        "id": "branch",
                        "type": "condition",
                        "evaluator": {"cel": "true"},
                        "steps": [
                            {
                                "id": "nest",
                                "type": "workflow_ref",
                                "workflow_id": "wf-x",
                            }
                        ],
                        "else": [
                            {
                                "id": "leaf",
                                "type": "step",
                                "executor": agent_executor("safe-fallback"),
                            }
                        ],
                    }
                ],
            },
            forbid_self_workflow_id="wf-x",
        )


def test_other_workflow_ref_allowed_with_forbid_id():
    normalized = validate_and_normalize_definition(
        {
            "name": "ok",
            "steps": [
                {
                    "id": "nest",
                    "type": "workflow_ref",
                    "workflow_id": "other-wf",
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
    assert normalized["steps"][0]["workflow_id"] == "other-wf"


def test_normalize_step_uses_executor_display_name_when_name_empty_or_ref():
    out = validate_and_normalize_definition(
        {
            "name": "wf",
            "description": "",
            "steps": [
                {
                    "id": "s1",
                    "type": "step",
                    "name": "",
                    "executor": agent_executor("security-operations"),
                },
                {
                    "id": "s2",
                    "type": "step",
                    "name": "security-operations",
                    "executor": agent_executor("security-operations"),
                },
                {
                    "id": "s3",
                    "type": "step",
                    "name": "自定义研判",
                    "executor": agent_executor("safe-fallback"),
                },
            ],
        }
    )
    steps = out["steps"]
    assert steps[0]["name"] == "安全运营助手"
    assert steps[1]["name"] == "安全运营助手"
    assert steps[2]["name"] == "自定义研判"
