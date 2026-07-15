"""Compile workbench workflow definitions into Agno Workflow instances (PR1: linear steps)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from agno.agent import Agent
from agno.workflow import Step, Workflow
from agno.workflow.workflow import WorkflowSteps

from api.services.model_factory import build_agno_model
from api.services.model_config_service import get_model_for_run
from api.services.postgres_store import get_async_agno_postgres_db

# Built-in executor registry for PR1. Nested/team executors arrive in later PRs.
BUILTIN_AGENT_REFS: dict[str, dict[str, str]] = {
    "security-operations": {
        "id": "security-operations",
        "name": "安全防御助手",
        "role": "安全防御运营助手",
        "description": "线性工作流步骤使用的安全运营 Agent（无 MCP，降低编排复杂度）。",
    },
    "safe-fallback": {
        "id": "safe-fallback",
        "name": "无工具安全助手",
        "role": "安全分析助手",
        "description": "无工具模式下的轻量步骤执行器。",
    },
}


class WorkflowDefinitionError(ValueError):
    """Raised when a workflow definition cannot be compiled."""


@dataclass(frozen=True)
class LinearStepSpec:
    id: str
    name: str
    executor_ref: str
    instructions: str


@dataclass(frozen=True)
class LinearWorkflowSpec:
    name: str
    description: str
    steps: list[LinearStepSpec]


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


def validate_and_normalize_definition(raw: object) -> dict[str, Any]:
    """Validate PR1 linear DSL and return a normalized definition dict."""
    if not isinstance(raw, dict):
        raise WorkflowDefinitionError("definition must be an object")
    name = str(raw.get("name") or "").strip() or "Untitled workflow"
    description = str(raw.get("description") or "").strip()
    steps_raw = raw.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise WorkflowDefinitionError("definition.steps must be a non-empty array")
    if len(steps_raw) > 20:
        raise WorkflowDefinitionError("definition.steps supports at most 20 steps in PR1")

    steps: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(steps_raw):
        if not isinstance(item, dict):
            raise WorkflowDefinitionError(f"steps[{index}] must be an object")
        step_type = str(item.get("type") or "step").strip().lower()
        if step_type != "step":
            raise WorkflowDefinitionError(
                f"steps[{index}].type={step_type!r} is not supported in PR1 (linear steps only)"
            )
        step_id = str(item.get("id") or f"step-{index + 1}").strip()
        if not step_id:
            raise WorkflowDefinitionError(f"steps[{index}].id is required")
        if step_id in seen_ids:
            raise WorkflowDefinitionError(f"duplicate step id: {step_id}")
        seen_ids.add(step_id)
        raw_executor = item.get("executor")
        executor: dict[str, Any] = (
            {str(key): value for key, value in raw_executor.items()}
            if isinstance(raw_executor, dict)
            else {}
        )
        kind = str(executor.get("kind") or item.get("kind") or "agent").strip().lower()
        if kind != "agent":
            raise WorkflowDefinitionError(
                f"steps[{index}] executor.kind={kind!r} is not supported in PR1"
            )
        ref = str(
            executor.get("ref")
            or item.get("targetId")
            or item.get("target_id")
            or item.get("executor_id")
            or ""
        ).strip()
        if not ref:
            raise WorkflowDefinitionError(f"steps[{index}] executor.ref is required")
        if ref not in BUILTIN_AGENT_REFS:
            raise WorkflowDefinitionError(
                f"steps[{index}] unknown executor.ref={ref!r}; "
                f"allowed: {', '.join(sorted(BUILTIN_AGENT_REFS))}"
            )
        display_name = str(item.get("name") or ref).strip() or ref
        instructions = str(item.get("instructions") or "").strip()
        steps.append(
            {
                "id": step_id,
                "type": "step",
                "name": display_name,
                "executor": {"kind": "agent", "ref": ref},
                "instructions": instructions,
            }
        )
    return {"name": name, "description": description, "steps": steps}


def parse_linear_spec(definition: dict[str, Any]) -> LinearWorkflowSpec:
    normalized = validate_and_normalize_definition(definition)
    return LinearWorkflowSpec(
        name=str(normalized["name"]),
        description=str(normalized["description"]),
        steps=[
            LinearStepSpec(
                id=str(step["id"]),
                name=str(step["name"]),
                executor_ref=str(step["executor"]["ref"]),
                instructions=str(step.get("instructions") or ""),
            )
            for step in normalized["steps"]
        ],
    )


async def _build_agent(
    *,
    ref: str,
    step_name: str,
    instructions: str,
    model_id: str | None,
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
    return Agent(
        id=meta["id"],
        name=meta["name"],
        role=meta["role"],
        description=meta["description"],
        instructions=instruction_parts,
        model=model,
        db=get_async_agno_postgres_db(),
        markdown=True,
        # Keep PR1 steps tool-free for predictable linear execution.
        tools=[],
    )


async def compile_workflow(
    definition: dict[str, Any],
    *,
    workflow_id: str | None = None,
    model_id: str | None = None,
) -> Workflow:
    """Build an Agno Workflow from a validated linear definition."""
    spec = parse_linear_spec(definition)
    steps: list[Step] = []
    for step in spec.steps:
        agent = await _build_agent(
            ref=step.executor_ref,
            step_name=step.name,
            instructions=step.instructions,
            model_id=model_id,
        )
        steps.append(
            Step(
                name=step.name,
                step_id=step.id,
                description=step.instructions or step.name,
                agent=agent,
            )
        )
    return Workflow(
        id=workflow_id,
        name=spec.name,
        description=spec.description,
        steps=cast(WorkflowSteps, steps),
        db=get_async_agno_postgres_db(),
        stream=True,
        stream_events=True,
        # PR1: surface step lifecycle without dumping full executor token streams.
        stream_executor_events=False,
    )
