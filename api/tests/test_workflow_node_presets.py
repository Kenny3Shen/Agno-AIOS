from api.services.workflow_node_presets import (
    list_builtin_node_presets,
    normalize_custom_step_definition,
)
from api.services.workflow_templates import list_workflow_templates


def _workflow_skill_names(value: object) -> set[str]:
    if isinstance(value, dict):
        names: set[str] = set()
        skills = value.get("skills")
        if isinstance(skills, list):
            names.update(item for item in skills if isinstance(item, str))
        for child in value.values():
            names.update(_workflow_skill_names(child))
        return names
    if isinstance(value, list):
        return set().union(*(_workflow_skill_names(item) for item in value))
    return set()


def test_builtin_presets_use_product_executors() -> None:
    presets = list_builtin_node_presets()
    assert len(presets) >= 4
    refs = {
        item["definition"]["executor"]["ref"]
        for item in presets
    }
    assert "security-operations" in refs
    assert "safe-fallback" in refs


def test_builtin_templates_reference_only_available_builtin_skills() -> None:
    names = _workflow_skill_names(list_workflow_templates())
    assert names <= {
        "cve-intel-skill",
        "hitl-containment-skill",
        "ip-blacklist-skill",
    }


def test_normalize_strips_skills_for_non_skill_executors() -> None:
    payload = normalize_custom_step_definition(
        {
            "type": "step",
            "name": "分析",
            "executor": {"kind": "agent", "ref": "data-analysis"},
            "instructions": "分析 CSV",
            "skills": ["cve-intel-skill"],
            "requires_confirmation": True,
        }
    )
    assert payload["executor"]["ref"] == "data-analysis"
    assert payload["skills"] == []
    assert payload["requires_confirmation"] is False


def test_normalize_keeps_hitl_for_security_ops() -> None:
    payload = normalize_custom_step_definition(
        {
            "type": "step",
            "executor": {"kind": "agent", "ref": "security-operations"},
            "skills": ["hitl-containment-skill"],
            "requires_confirmation": True,
            "confirmation_message": "确认？",
        }
    )
    assert payload["skills"] == ["hitl-containment-skill"]
    assert payload["requires_confirmation"] is True
    assert payload["confirmation_message"] == "确认？"


def test_normalize_rejects_unknown_executor() -> None:
    try:
        normalize_custom_step_definition(
            {
                "type": "step",
                "executor": {"kind": "agent", "ref": "not-a-real-agent"},
                "instructions": "x",
            }
        )
    except ValueError as exc:
        assert "unknown executor.ref" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown executor")


def test_normalize_validates_user_input_schema() -> None:
    payload = normalize_custom_step_definition(
        {
            "type": "step",
            "executor": {"kind": "agent", "ref": "security-operations"},
            "requires_user_input": True,
            "user_input_schema": [
                {"name": "reason", "field_type": "text", "required": True},
                {"name": "count", "type": "integer", "required": False},
            ],
        }
    )
    assert payload["user_input_schema"] == [
        {"name": "reason", "field_type": "text", "required": True},
        {"name": "count", "field_type": "number", "required": False},
    ]

    try:
        normalize_custom_step_definition(
            {
                "type": "step",
                "executor": {"kind": "agent", "ref": "security-operations"},
                "user_input_schema": [{"field_type": "str"}],
            }
        )
    except ValueError as exc:
        assert "name is required" in str(exc)
    else:
        raise AssertionError("expected ValueError for invalid schema")
