"""Compile workbench workflow definitions into Agno Workflow instances.

Supported steps: step | parallel | condition | loop | router | workflow_ref
+ step HITL (confirmation / user_input / output_review).
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, cast

from agno.agent import Agent
from agno.skills import LocalSkills, Skills
from agno.workflow import Condition, Loop, Parallel, Router, Step, Steps, Workflow
from agno.workflow.cel import CEL_AVAILABLE, validate_cel_expression
from agno.workflow.workflow import WorkflowSteps

from api.services.model_config_service import get_model_for_run
from api.services.model_factory import build_agno_model
from api.services.postgres_store import get_async_agno_postgres_db
from api.services.skill_service import resolve_enabled_skill_dirs

# Built-in executor registry. Nested/team executors arrive in later PRs.
BUILTIN_AGENT_REFS: dict[str, dict[str, str]] = {
    "security-operations": {
        "id": "security-operations",
        "name": "安全防御助手",
        "role": "安全防御运营助手",
        "description": "工作流步骤使用的安全运营 Agent（无 MCP，降低编排复杂度）。",
    },
    "safe-fallback": {
        "id": "safe-fallback",
        "name": "无工具安全助手",
        "role": "安全分析助手",
        "description": "无工具模式下的轻量步骤执行器。",
    },
}

SUPPORTED_NODE_TYPES = frozenset({"step", "parallel", "condition", "loop", "router", "workflow_ref"})
MAX_DEPTH = 5
MAX_TOTAL_NODES = 40
MAX_LEAF_STEPS = 20
MAX_BRANCH_CHILDREN = 10
MAX_LOOP_ITERATIONS = 20
DEFAULT_LOOP_ITERATIONS = 3


class WorkflowDefinitionError(ValueError):
    """Raised when a workflow definition cannot be compiled."""


def list_executor_options() -> list[dict[str, str]]:
    return [
        {
            "ref": ref,
            "kind": "agent",
            "name": meta["name"],
            "description": meta["description"],
        }
        for ref, meta in BUILTIN_AGENT_REFS.items()
    ]


def _path(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else key


def _require_non_empty_id(raw_id: object, path: str, fallback: str) -> str:
    step_id = str(raw_id or fallback).strip()
    if not step_id:
        raise WorkflowDefinitionError(f"{path}.id is required")
    return step_id


def _parse_cel_field(
    raw: object,
    *,
    path: str,
    required: bool,
    field_name: str = "cel",
) -> str | bool | None:
    """Normalize evaluator / end_condition into CEL string, bool, or None."""
    if raw is None:
        if required:
            raise WorkflowDefinitionError(f"{path} is required")
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        expression = raw.strip()
        if not expression:
            if required:
                raise WorkflowDefinitionError(f"{path} must be a non-empty CEL expression")
            return None
        _assert_valid_cel(expression, path)
        return expression
    if isinstance(raw, dict):
        raw_obj: dict[str, Any] = {str(k): v for k, v in raw.items()}
        if "cel" in raw_obj:
            expression = str(raw_obj.get("cel") or "").strip()
            if not expression:
                if required:
                    raise WorkflowDefinitionError(f"{path}.cel must be a non-empty CEL expression")
                return None
            _assert_valid_cel(expression, f"{path}.cel")
            return expression
        value = raw_obj.get("value")
        if isinstance(value, bool):
            return value
        raise WorkflowDefinitionError(
            f"{path} must be a CEL string, bool, or object with {field_name!r}"
        )
    raise WorkflowDefinitionError(f"{path} must be a CEL string, bool, or object")


def _assert_valid_cel(expression: str, path: str) -> None:
    if not CEL_AVAILABLE:
        raise WorkflowDefinitionError(
            f"{path}: CEL expressions require cel-python (pip install cel-python)"
        )
    if not validate_cel_expression(expression):
        raise WorkflowDefinitionError(f"{path}: invalid CEL expression: {expression!r}")


def _reject_advanced_hitl_flags(item: dict[str, Any], path: str) -> None:
    """Step HITL fields are handled on steps; block opaque human_review blobs."""
    if item.get("human_review"):
        raise WorkflowDefinitionError(
            f"{path}.human_review blob is not supported; use requires_confirmation / "
            "requires_user_input / requires_output_review on steps"
        )
    if item.get("requires_iteration_review"):
        raise WorkflowDefinitionError(
            f"{path}.requires_iteration_review is not supported on this node type"
        )


def _normalize_node(
    item: object,
    *,
    path: str,
    index: int,
    depth: int,
    seen_ids: set[str],
    counters: dict[str, int],
    inside_parallel: bool,
) -> dict[str, Any]:
    if depth > MAX_DEPTH:
        raise WorkflowDefinitionError(
            f"{path}: nesting deeper than {MAX_DEPTH} levels is not allowed"
        )
    if not isinstance(item, dict):
        raise WorkflowDefinitionError(f"{path} must be an object")
    item_obj: dict[str, Any] = {str(k): v for k, v in item.items()}
    counters["nodes"] += 1
    if counters["nodes"] > MAX_TOTAL_NODES:
        raise WorkflowDefinitionError(
            f"definition supports at most {MAX_TOTAL_NODES} nodes (including nested)"
        )

    node_type = str(item_obj.get("type") or "step").strip().lower()
    if node_type not in SUPPORTED_NODE_TYPES:
        raise WorkflowDefinitionError(
            f"{path}.type={node_type!r} is not supported; "
            f"allowed: {', '.join(sorted(SUPPORTED_NODE_TYPES))}"
        )

    node_id = _require_non_empty_id(item_obj.get("id"), path, f"{node_type}-{index + 1}")
    if node_id in seen_ids:
        raise WorkflowDefinitionError(f"duplicate node id: {node_id}")
    seen_ids.add(node_id)
    _reject_advanced_hitl_flags(item_obj, path)
    display_name = str(item_obj.get("name") or node_id).strip() or node_id
    for hitl_key in (
        "requires_confirmation",
        "requires_user_input",
        "requires_output_review",
    ):
        if node_type != "step" and item_obj.get(hitl_key):
            raise WorkflowDefinitionError(
                f"{path}: {hitl_key} is only supported on type=step"
            )

    if node_type == "step":
        return _normalize_step(
            item_obj,
            path=path,
            node_id=node_id,
            display_name=display_name,
            inside_parallel=inside_parallel,
        )
    if node_type == "parallel":
        return _normalize_parallel(
            item_obj,
            path=path,
            node_id=node_id,
            display_name=display_name,
            depth=depth,
            seen_ids=seen_ids,
            counters=counters,
        )
    if node_type == "condition":
        return _normalize_condition(
            item_obj,
            path=path,
            node_id=node_id,
            display_name=display_name,
            depth=depth,
            seen_ids=seen_ids,
            counters=counters,
            inside_parallel=inside_parallel,
        )
    if node_type == "loop":
        return _normalize_loop(
            item_obj,
            path=path,
            node_id=node_id,
            display_name=display_name,
            depth=depth,
            seen_ids=seen_ids,
            counters=counters,
            inside_parallel=inside_parallel,
        )
    if node_type == "router":
        return _normalize_router(
            item_obj,
            path=path,
            node_id=node_id,
            display_name=display_name,
            depth=depth,
            seen_ids=seen_ids,
            counters=counters,
            inside_parallel=inside_parallel,
        )
    return _normalize_workflow_ref(
        item_obj,
        path=path,
        node_id=node_id,
        display_name=display_name,
        inside_parallel=inside_parallel,
    )


def _normalize_step(
    item: dict[str, Any],
    *,
    path: str,
    node_id: str,
    display_name: str,
    inside_parallel: bool,
) -> dict[str, Any]:
    raw_executor = item.get("executor")
    executor: dict[str, Any] = (
        {str(key): value for key, value in raw_executor.items()}
        if isinstance(raw_executor, dict)
        else {}
    )
    kind = str(executor.get("kind") or item.get("kind") or "agent").strip().lower()
    if kind != "agent":
        raise WorkflowDefinitionError(f"{path} executor.kind={kind!r} is not supported")
    ref = str(
        executor.get("ref")
        or item.get("targetId")
        or item.get("target_id")
        or item.get("executor_id")
        or ""
    ).strip()
    if not ref:
        raise WorkflowDefinitionError(f"{path} executor.ref is required")
    if ref not in BUILTIN_AGENT_REFS:
        raise WorkflowDefinitionError(
            f"{path} unknown executor.ref={ref!r}; "
            f"allowed: {', '.join(sorted(BUILTIN_AGENT_REFS))}"
        )
    requires_confirmation = bool(item.get("requires_confirmation"))
    requires_user_input = bool(item.get("requires_user_input"))
    requires_output_review = bool(item.get("requires_output_review"))
    confirmation_message = str(item.get("confirmation_message") or "").strip()
    user_input_message = str(item.get("user_input_message") or "").strip()
    output_review_message = str(item.get("output_review_message") or "").strip()
    hitl_any = requires_confirmation or requires_user_input or requires_output_review
    # Agno Parallel cannot pause for executor HITL.
    if inside_parallel and hitl_any:
        raise WorkflowDefinitionError(
            f"{path}: step HITL is forbidden inside Parallel (Agno constraint)"
        )
    instructions = str(item.get("instructions") or "").strip()
    payload: dict[str, Any] = {
        "id": node_id,
        "type": "step",
        "name": display_name,
        "executor": {"kind": "agent", "ref": ref},
        "instructions": instructions,
        "requires_confirmation": requires_confirmation,
        "requires_user_input": requires_user_input,
        "requires_output_review": requires_output_review,
    }
    if confirmation_message:
        payload["confirmation_message"] = confirmation_message
    if user_input_message:
        payload["user_input_message"] = user_input_message
    if output_review_message:
        payload["output_review_message"] = output_review_message
    # optional free-form schema for user_input
    schema = item.get("user_input_schema")
    if isinstance(schema, list) and schema:
        payload["user_input_schema"] = schema
    # optional skill directory names (bound ∩ globally enabled at run time)
    raw_skills = item.get("skills")
    if isinstance(raw_skills, list):
        skills: list[str] = []
        for entry in raw_skills:
            name = str(entry or "").strip()
            if name and name not in skills:
                skills.append(name)
        if skills:
            payload["skills"] = skills
    # optional layout for canvas
    position = item.get("position")
    if isinstance(position, dict):
        payload["position"] = {
            "x": float(position.get("x") or 0),
            "y": float(position.get("y") or 0),
        }
    return payload


def _normalize_children(
    raw_children: object,
    *,
    path: str,
    depth: int,
    seen_ids: set[str],
    counters: dict[str, int],
    inside_parallel: bool,
    allow_empty: bool = False,
) -> list[dict[str, Any]]:
    if raw_children is None:
        if allow_empty:
            return []
        raise WorkflowDefinitionError(f"{path} must be a non-empty array")
    if not isinstance(raw_children, list):
        raise WorkflowDefinitionError(f"{path} must be an array")
    if not raw_children and not allow_empty:
        raise WorkflowDefinitionError(f"{path} must be a non-empty array")
    if len(raw_children) > MAX_BRANCH_CHILDREN:
        raise WorkflowDefinitionError(
            f"{path} supports at most {MAX_BRANCH_CHILDREN} children"
        )
    children: list[dict[str, Any]] = []
    for index, child in enumerate(raw_children):
        children.append(
            _normalize_node(
                child,
                path=f"{path}[{index}]",
                index=index,
                depth=depth + 1,
                seen_ids=seen_ids,
                counters=counters,
                inside_parallel=inside_parallel,
            )
        )
    return children



def _with_position(item: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    position = item.get("position")
    if isinstance(position, dict):
        payload["position"] = {
            "x": float(position.get("x") or 0),
            "y": float(position.get("y") or 0),
        }
    return payload


def _normalize_parallel(
    item: dict[str, Any],
    *,
    path: str,
    node_id: str,
    display_name: str,
    depth: int,
    seen_ids: set[str],
    counters: dict[str, int],
) -> dict[str, Any]:
    children = _normalize_children(
        item.get("steps"),
        path=_path(path, "steps"),
        depth=depth,
        seen_ids=seen_ids,
        counters=counters,
        inside_parallel=True,
    )
    if len(children) < 2:
        raise WorkflowDefinitionError(f"{path}.steps must contain at least 2 branches")
    return _with_position(
        item,
        {
            "id": node_id,
            "type": "parallel",
            "name": display_name,
            "steps": children,
        },
    )


def _normalize_condition(
    item: dict[str, Any],
    *,
    path: str,
    node_id: str,
    display_name: str,
    depth: int,
    seen_ids: set[str],
    counters: dict[str, int],
    inside_parallel: bool,
) -> dict[str, Any]:
    evaluator = _parse_cel_field(
        item.get("evaluator"),
        path=_path(path, "evaluator"),
        required=True,
    )
    then_raw = (
        item.get("then")
        if item.get("then") is not None
        else item.get("then_steps")
        if item.get("then_steps") is not None
        else item.get("steps")
    )
    then_steps = _normalize_children(
        then_raw,
        path=_path(path, "then"),
        depth=depth,
        seen_ids=seen_ids,
        counters=counters,
        inside_parallel=inside_parallel,
    )
    else_raw = item.get("else") if item.get("else") is not None else item.get("else_steps")
    else_steps = _normalize_children(
        else_raw if else_raw is not None else [],
        path=_path(path, "else"),
        depth=depth,
        seen_ids=seen_ids,
        counters=counters,
        inside_parallel=inside_parallel,
        allow_empty=True,
    )
    normalized: dict[str, Any] = {
        "id": node_id,
        "type": "condition",
        "name": display_name,
        "evaluator": (
            {"cel": evaluator} if isinstance(evaluator, str) else {"value": bool(evaluator)}
        ),
        "then": then_steps,
        "else": else_steps,
    }
    return _with_position(item, normalized)


def _normalize_loop(
    item: dict[str, Any],
    *,
    path: str,
    node_id: str,
    display_name: str,
    depth: int,
    seen_ids: set[str],
    counters: dict[str, int],
    inside_parallel: bool,
) -> dict[str, Any]:
    raw_max = item.get("max_iterations", item.get("maxIterations", DEFAULT_LOOP_ITERATIONS))
    try:
        max_iterations = int(raw_max)
    except (TypeError, ValueError) as exc:
        raise WorkflowDefinitionError(f"{path}.max_iterations must be an integer") from exc
    if max_iterations < 1 or max_iterations > MAX_LOOP_ITERATIONS:
        raise WorkflowDefinitionError(
            f"{path}.max_iterations must be between 1 and {MAX_LOOP_ITERATIONS}"
        )
    end_condition = _parse_cel_field(
        item.get("end_condition", item.get("endCondition")),
        path=_path(path, "end_condition"),
        required=False,
    )
    children = _normalize_children(
        item.get("steps"),
        path=_path(path, "steps"),
        depth=depth,
        seen_ids=seen_ids,
        counters=counters,
        inside_parallel=inside_parallel,
    )
    normalized: dict[str, Any] = {
        "id": node_id,
        "type": "loop",
        "name": display_name,
        "max_iterations": max_iterations,
        "steps": children,
    }
    if end_condition is None:
        normalized["end_condition"] = None
    elif isinstance(end_condition, str):
        normalized["end_condition"] = {"cel": end_condition}
    else:
        # bool end_condition is unusual; treat as constant CEL via bool evaluator only for compile
        normalized["end_condition"] = {"value": bool(end_condition)}
    return _with_position(item, normalized)


def validate_and_normalize_definition(raw: object) -> dict[str, Any]:
    """Validate nested workflow DSL and return a normalized definition dict."""
    if not isinstance(raw, dict):
        raise WorkflowDefinitionError("definition must be an object")
    name = str(raw.get("name") or "").strip() or "Untitled workflow"
    description = str(raw.get("description") or "").strip()
    steps_raw = raw.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise WorkflowDefinitionError("definition.steps must be a non-empty array")

    seen_ids: set[str] = set()
    counters = {"nodes": 0, "leaves": 0}
    steps: list[dict[str, Any]] = []
    for index, item in enumerate(steps_raw):
        node = _normalize_node(
            item,
            path=f"steps[{index}]",
            index=index,
            depth=1,
            seen_ids=seen_ids,
            counters=counters,
            inside_parallel=False,
        )
        steps.append(node)

    leaf_count = _count_leaf_steps(steps)
    if leaf_count > MAX_LEAF_STEPS:
        raise WorkflowDefinitionError(
            f"definition supports at most {MAX_LEAF_STEPS} leaf agent steps (got {leaf_count})"
        )
    if leaf_count < 1:
        raise WorkflowDefinitionError("definition must include at least one agent step")
    return {"name": name, "description": description, "steps": steps}



def _normalize_router(
    item: dict[str, Any],
    *,
    path: str,
    node_id: str,
    display_name: str,
    depth: int,
    seen_ids: set[str],
    counters: dict[str, int],
    inside_parallel: bool,
) -> dict[str, Any]:
    selector = _parse_cel_field(
        item.get("selector"),
        path=_path(path, "selector"),
        required=True,
    )
    if not isinstance(selector, str):
        raise WorkflowDefinitionError(f"{path}.selector must be a CEL expression string")
    raw_choices = item.get("choices")
    if not isinstance(raw_choices, list) or len(raw_choices) < 2:
        raise WorkflowDefinitionError(f"{path}.choices must contain at least 2 branches")
    if len(raw_choices) > MAX_BRANCH_CHILDREN:
        raise WorkflowDefinitionError(
            f"{path}.choices supports at most {MAX_BRANCH_CHILDREN} branches"
        )
    choices: list[dict[str, Any]] = []
    choice_names: set[str] = set()
    for index, raw in enumerate(raw_choices):
        if not isinstance(raw, dict):
            raise WorkflowDefinitionError(f"{path}.choices[{index}] must be an object")
        choice_id = _require_non_empty_id(
            raw.get("id"), f"{path}.choices[{index}]", f"choice-{index + 1}"
        )
        if choice_id in seen_ids:
            raise WorkflowDefinitionError(f"duplicate node id: {choice_id}")
        seen_ids.add(choice_id)
        choice_name = str(raw.get("name") or choice_id).strip() or choice_id
        if choice_name in choice_names:
            raise WorkflowDefinitionError(f"{path}: duplicate choice name {choice_name!r}")
        choice_names.add(choice_name)
        raw_steps = raw.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise WorkflowDefinitionError(
                f"{path}.choices[{index}].steps must be a non-empty array"
            )
        children = _normalize_children(
            raw_steps,
            path=f"{path}.choices[{index}].steps",
            depth=depth,
            seen_ids=seen_ids,
            counters=counters,
            inside_parallel=inside_parallel,
        )
        choices.append(
            {
                "id": choice_id,
                "name": choice_name,
                "steps": children,
            }
        )
    return _with_position(
        item,
        {
            "id": node_id,
            "type": "router",
            "name": display_name,
            "selector": {"cel": selector},
            "choices": choices,
        },
    )


def _normalize_workflow_ref(
    item: dict[str, Any],
    *,
    path: str,
    node_id: str,
    display_name: str,
    inside_parallel: bool,
) -> dict[str, Any]:
    if inside_parallel:
        raise WorkflowDefinitionError(
            f"{path}: nested workflow_ref is forbidden inside Parallel"
        )
    ref = str(
        item.get("workflow_id")
        or item.get("workflowId")
        or item.get("ref")
        or ""
    ).strip()
    if not ref:
        raise WorkflowDefinitionError(f"{path}.workflow_id is required")
    return _with_position(
        item,
        {
            "id": node_id,
            "type": "workflow_ref",
            "name": display_name,
            "workflow_id": ref,
        },
    )


def _count_leaf_steps(nodes: list[dict[str, Any]]) -> int:
    total = 0
    for node in nodes:
        node_type = node.get("type")
        if node_type == "step":
            total += 1
        elif node_type == "workflow_ref":
            # nested workflow counts as one leaf unit for budget
            total += 1
        elif node_type == "parallel":
            total += _count_leaf_steps(list(node.get("steps") or []))
        elif node_type == "condition":
            total += _count_leaf_steps(list(node.get("then") or []))
            total += _count_leaf_steps(list(node.get("else") or []))
        elif node_type == "loop":
            total += _count_leaf_steps(list(node.get("steps") or []))
        elif node_type == "router":
            for choice in list(node.get("choices") or []):
                if isinstance(choice, dict):
                    total += _count_leaf_steps(list(choice.get("steps") or []))
    return total


def collect_workflow_skill_names(definition: dict[str, Any] | list[Any] | None) -> list[str]:
    """Unique skill names bound on any step (depth-first)."""
    names: list[str] = []
    seen: set[str] = set()

    def walk(nodes: object) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_type = str(node.get("type") or "step")
            if node_type == "step":
                skills = node.get("skills")
                if isinstance(skills, list):
                    for entry in skills:
                        name = str(entry or "").strip()
                        if name and name not in seen:
                            seen.add(name)
                            names.append(name)
            walk(node.get("steps"))
            walk(node.get("then"))
            walk(node.get("else"))
            walk(node.get("then_steps"))
            walk(node.get("else_steps"))
            choices = node.get("choices")
            if isinstance(choices, list):
                for choice in choices:
                    if isinstance(choice, dict):
                        walk(choice.get("steps"))

    if isinstance(definition, dict):
        walk(definition.get("steps"))
    elif isinstance(definition, list):
        walk(definition)
    return names


def _load_skills_for_names(skill_names: list[str]) -> Skills | None:
    dirs = resolve_enabled_skill_dirs(skill_names)
    if not dirs:
        return None
    return Skills(loaders=[LocalSkills(str(path)) for path in dirs])


async def _build_agent(
    *,
    ref: str,
    step_name: str,
    instructions: str,
    model_id: str | None,
    skill_names: list[str] | None = None,
) -> Agent:
    meta = BUILTIN_AGENT_REFS[ref]
    config = await get_model_for_run(model_id)
    model = build_agno_model(config)
    instruction_parts = [
        meta["description"],
        f"当前工作流步骤：{step_name}",
    ]
    if instructions:
        instruction_parts.append(instructions)
    skills = _load_skills_for_names(list(skill_names or []))
    return Agent(
        id=meta["id"],
        name=meta["name"],
        role=meta["role"],
        description=meta["description"],
        instructions=instruction_parts,
        model=model,
        db=get_async_agno_postgres_db(),
        markdown=True,
        # Steps stay MCP/tool-free; optional Skills bind via DSL skills[].
        tools=[],
        skills=skills,
    )


async def _compile_node(
    node: dict[str, Any],
    *,
    model_id: str | None,
    resolve_nested: "Callable[[str], Awaitable[dict[str, Any]]] | None" = None,
    nesting_stack: set[str] | None = None,
) -> Any:
    node_type = str(node.get("type") or "step")
    name = str(node.get("name") or node.get("id") or node_type)

    if node_type == "step":
        ref = str(node["executor"]["ref"])
        instructions = str(node.get("instructions") or "")
        raw_skills = node.get("skills")
        skill_names = (
            [str(s).strip() for s in raw_skills if str(s).strip()]
            if isinstance(raw_skills, list)
            else []
        )
        agent = await _build_agent(
            ref=ref,
            step_name=name,
            instructions=instructions,
            model_id=model_id,
            skill_names=skill_names,
        )
        return Step(
            name=name,
            step_id=str(node["id"]),
            description=instructions or name,
            agent=agent,
            requires_confirmation=bool(node.get("requires_confirmation")),
            confirmation_message=(
                str(node.get("confirmation_message") or "").strip() or None
            ),
            requires_user_input=bool(node.get("requires_user_input")),
            user_input_message=(
                str(node.get("user_input_message") or "").strip() or None
            ),
            user_input_schema=node.get("user_input_schema")
            if isinstance(node.get("user_input_schema"), list)
            else None,
            requires_output_review=bool(node.get("requires_output_review")),
            output_review_message=(
                str(node.get("output_review_message") or "").strip() or None
            ),
        )

    if node_type == "parallel":
        children = [
            await _compile_node(child, model_id=model_id, resolve_nested=resolve_nested, nesting_stack=nesting_stack)
            for child in list(node.get("steps") or [])
        ]
        return Parallel(*children, name=name)

    if node_type == "condition":
        evaluator_raw = node.get("evaluator")
        if isinstance(evaluator_raw, dict) and "cel" in evaluator_raw:
            evaluator: Any = str(evaluator_raw["cel"])
        elif isinstance(evaluator_raw, dict) and "value" in evaluator_raw:
            evaluator = bool(evaluator_raw["value"])
        elif isinstance(evaluator_raw, (str, bool)):
            evaluator = evaluator_raw
        else:
            raise WorkflowDefinitionError(f"condition {name!r} missing evaluator")
        then_steps = [
            await _compile_node(child, model_id=model_id, resolve_nested=resolve_nested, nesting_stack=nesting_stack)
            for child in list(node.get("then") or [])
        ]
        else_steps = [
            await _compile_node(child, model_id=model_id, resolve_nested=resolve_nested, nesting_stack=nesting_stack)
            for child in list(node.get("else") or [])
        ]
        return Condition(
            name=name,
            evaluator=evaluator,
            steps=then_steps,
            else_steps=else_steps or None,
        )

    if node_type == "loop":
        max_iterations = int(node.get("max_iterations") or DEFAULT_LOOP_ITERATIONS)
        end_raw = node.get("end_condition")
        end_condition: Any = None
        if isinstance(end_raw, dict) and end_raw.get("cel"):
            end_condition = str(end_raw["cel"])
        elif isinstance(end_raw, dict) and "value" in end_raw:
            # Constant bool end: True ends immediately after first iteration check
            constant = bool(end_raw["value"])

            def _const_end(_outputs: list[Any], _value: bool = constant) -> bool:
                return _value

            end_condition = _const_end
        elif isinstance(end_raw, str) and end_raw.strip():
            end_condition = end_raw.strip()
        children = [
            await _compile_node(child, model_id=model_id, resolve_nested=resolve_nested, nesting_stack=nesting_stack)
            for child in list(node.get("steps") or [])
        ]
        return Loop(
            name=name,
            steps=children,
            max_iterations=max_iterations,
            end_condition=end_condition,
        )

    if node_type == "router":
        selector_raw = node.get("selector")
        if isinstance(selector_raw, dict) and selector_raw.get("cel"):
            selector: Any = str(selector_raw["cel"])
        elif isinstance(selector_raw, str):
            selector = selector_raw
        else:
            raise WorkflowDefinitionError(f"router {name!r} missing CEL selector")
        choices: list[Any] = []
        for choice in list(node.get("choices") or []):
            if not isinstance(choice, dict):
                continue
            choice_name = str(choice.get("name") or choice.get("id") or "choice")
            choice_children = [
                await _compile_node(
                    child,
                    model_id=model_id,
                    resolve_nested=resolve_nested,
                    nesting_stack=nesting_stack,
                )
                for child in list(choice.get("steps") or [])
            ]
            if len(choice_children) == 1:
                # Ensure choice has stable name for CEL selector match
                only = choice_children[0]
                if hasattr(only, "name"):
                    only.name = choice_name
                choices.append(only)
            else:
                choices.append(Steps(name=choice_name, steps=choice_children))
        return Router(name=name, choices=choices, selector=selector)

    if node_type == "workflow_ref":
        ref = str(node.get("workflow_id") or "").strip()
        if not ref:
            raise WorkflowDefinitionError(f"workflow_ref {name!r} missing workflow_id")
        if resolve_nested is None:
            raise WorkflowDefinitionError(
                f"workflow_ref {ref!r} cannot be resolved (no loader)"
            )
        stack = nesting_stack or set()
        if ref in stack:
            raise WorkflowDefinitionError(
                f"circular workflow_ref detected involving {ref!r}"
            )
        nested_def = await resolve_nested(ref)
        nested_stack = set(stack)
        nested_stack.add(ref)
        nested_wf = await compile_workflow(
            nested_def,
            workflow_id=ref,
            model_id=model_id,
            resolve_nested=resolve_nested,
            nesting_stack=nested_stack,
        )
        nested_wf.name = name or nested_wf.name
        return nested_wf

    raise WorkflowDefinitionError(f"unsupported node type at compile: {node_type!r}")


async def compile_workflow(
    definition: dict[str, Any],
    *,
    workflow_id: str | None = None,
    model_id: str | None = None,
    resolve_nested: Callable[[str], Awaitable[dict[str, Any]]] | None = None,
    nesting_stack: set[str] | None = None,
) -> Workflow:
    """Build an Agno Workflow from a validated nested definition."""
    normalized = validate_and_normalize_definition(definition)
    stack = set(nesting_stack or ())
    if workflow_id:
        stack.add(workflow_id)

    async def _default_resolve(ref: str) -> dict[str, Any]:
        from api.persistence import workflows as workflow_store

        row = await workflow_store.get_workflow(ref)
        if row is None:
            raise WorkflowDefinitionError(f"nested workflow not found: {ref}")
        definition_raw = row.get("definition")
        if not isinstance(definition_raw, dict):
            raise WorkflowDefinitionError(f"nested workflow {ref} has invalid definition")
        return definition_raw

    loader = resolve_nested or _default_resolve
    compiled_steps = [
        await _compile_node(
            node,
            model_id=model_id,
            resolve_nested=loader,
            nesting_stack=stack,
        )
        for node in normalized["steps"]
    ]
    return Workflow(
        id=workflow_id,
        name=str(normalized["name"]),
        description=str(normalized["description"]),
        steps=cast(WorkflowSteps, compiled_steps),
        db=get_async_agno_postgres_db(),
        stream=True,
        stream_events=True,
        # Surface control-flow lifecycle without dumping full executor token streams.
        stream_executor_events=False,
    )
