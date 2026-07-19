"""Canonicalize persisted Workflow definition keys before legacy reader removal."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any
from uuid import NAMESPACE_URL, uuid5


RETIRED_WORKFLOW_SKILL_NAMES = frozenset({"playbook-skill"})


def _copy_mapping(value: Mapping[Any, Any]) -> dict[str, Any]:
    return {str(key): deepcopy(item) for key, item in value.items()}


def _first_non_empty(*values: object) -> object | None:
    for value in values:
        if value is not None and str(value).strip():
            return value
    return None


def _canonical_id(value: object, *, path: str) -> str:
    if isinstance(value, str):
        candidate = value.strip()
    elif isinstance(value, int) and not isinstance(value, bool):
        candidate = str(value)
    else:
        candidate = ""
    return candidate or str(uuid5(NAMESPACE_URL, f"tais:workflow-definition:{path}"))


def _canonicalize_nodes(value: object, *, path: str) -> object:
    if not isinstance(value, list):
        return deepcopy(value)
    return [
        _canonicalize_node(item, path=f"{path}[{index}]")
        for index, item in enumerate(value)
    ]


def _canonicalize_choice(value: object, *, path: str) -> object:
    if not isinstance(value, Mapping):
        return deepcopy(value)
    choice = _copy_mapping(value)
    choice["id"] = _canonical_id(choice.get("id"), path=path)
    if "steps" in choice:
        choice["steps"] = _canonicalize_nodes(choice["steps"], path=f"{path}.steps")
    return choice


def _canonicalize_node(value: object, *, path: str) -> object:
    if not isinstance(value, Mapping):
        return deepcopy(value)
    node = _copy_mapping(value)
    node["id"] = _canonical_id(node.get("id"), path=path)
    node_type = str(node.get("type") or "step").strip().lower()
    node["type"] = node_type

    if node_type == "step":
        raw_skills = node.get("skills")
        if isinstance(raw_skills, list):
            skills = [
                str(skill).strip()
                for skill in raw_skills
                if str(skill).strip() not in RETIRED_WORKFLOW_SKILL_NAMES
            ]
            if skills:
                node["skills"] = skills
            else:
                node.pop("skills", None)
        raw_executor = node.get("executor")
        executor = _copy_mapping(raw_executor) if isinstance(raw_executor, Mapping) else {}
        legacy_ref = _first_non_empty(
            node.get("targetId"),
            node.get("target_id"),
            node.get("executor_id"),
        )
        if _first_non_empty(executor.get("ref")) is None and legacy_ref is not None:
            executor["ref"] = legacy_ref
        legacy_kind = _first_non_empty(node.get("kind"))
        if _first_non_empty(executor.get("kind")) is None and legacy_kind is not None:
            executor["kind"] = legacy_kind
        if _first_non_empty(executor.get("kind")) is None and executor.get("ref") is not None:
            executor["kind"] = "agent"
        if executor:
            node["executor"] = executor
        node.pop("targetId", None)
        node.pop("target_id", None)
        node.pop("executor_id", None)
        node.pop("kind", None)
        return node

    if node_type == "condition":
        then_value = node.get("steps")
        if then_value is None:
            then_value = node.get("then")
        if then_value is None:
            then_value = node.get("then_steps")
        if then_value is not None:
            node["steps"] = _canonicalize_nodes(then_value, path=f"{path}.steps")

        else_value = node.get("else")
        if else_value is None:
            else_value = node.get("else_steps")
        if else_value is not None:
            node["else"] = _canonicalize_nodes(else_value, path=f"{path}.else")
        else:
            node["else"] = []

        node.pop("then_steps", None)
        node.pop("else_steps", None)
        node.pop("then", None)
        return node

    if node_type == "loop":
        if node.get("max_iterations") is None and node.get("maxIterations") is not None:
            node["max_iterations"] = node["maxIterations"]
        if node.get("end_condition") is None and node.get("endCondition") is not None:
            node["end_condition"] = deepcopy(node["endCondition"])
        node.pop("maxIterations", None)
        node.pop("endCondition", None)
        if "steps" in node:
            node["steps"] = _canonicalize_nodes(node["steps"], path=f"{path}.steps")
        return node

    if node_type == "workflow_ref":
        legacy_ref = _first_non_empty(node.get("workflowId"), node.get("ref"))
        if _first_non_empty(node.get("workflow_id")) is None and legacy_ref is not None:
            node["workflow_id"] = legacy_ref
        node.pop("workflowId", None)
        node.pop("ref", None)
        return node

    if node_type == "router":
        choices = node.get("choices")
        if isinstance(choices, list):
            node["choices"] = [
                _canonicalize_choice(choice, path=f"{path}.choices[{index}]")
                for index, choice in enumerate(choices)
            ]
        return node

    if "steps" in node:
        node["steps"] = _canonicalize_nodes(node["steps"], path=f"{path}.steps")
    return node


def canonicalize_workflow_definition(value: object) -> dict[str, Any] | None:
    """Return a compiler-canonical definition, or ``None`` for non-objects."""
    if not isinstance(value, Mapping):
        return None
    definition = _copy_mapping(value)
    if "steps" in definition:
        definition["steps"] = _canonicalize_nodes(definition["steps"], path="steps")
    from api.services.workflow_compiler import (
        WorkflowDefinitionError,
        validate_and_normalize_definition,
    )

    try:
        return validate_and_normalize_definition(definition)
    except WorkflowDefinitionError:
        return definition
