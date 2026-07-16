"""Stream Agno Workflow runs as workbench SSE events (HITL + control flow)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from inspect import isawaitable
from types import SimpleNamespace
from typing import Any, AsyncIterator, cast
from uuid import uuid4

from agno.run.workflow import WorkflowRunEvent
from loguru import logger

from api.services.chat_run_events import event_value
from api.services.postgres_store import get_async_agno_postgres_db
from api.services.workflow_compiler import (
    collect_workflow_skill_names,
    compile_workflow,
)
from api.services.skill_service import resolve_enabled_skill_dirs
from api.services.audit_service import record_audit_event_async
from api.services.notification_service import notify_workflow_hitl_pending
from api.persistence import workflows as workflow_store


@dataclass(frozen=True)
class WorkflowRunEventOut:
    event: str
    data: dict[str, Any]


def _preview(value: Any, limit: int = 2000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = str(value)
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _step_index(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, tuple) and value:
        first = value[0]
        return int(first) if isinstance(first, int) else None
    return None


def _base_payload(
    *,
    workflow_id: str,
    run_id: str,
    session_id: str,
    event: Any,
) -> dict[str, Any]:
    step_name = event_value(event, "step_name")
    step_id = event_value(event, "step_id")
    parent = event_value(event, "parent_step_id")
    return {
        "workflow_id": workflow_id,
        "run_id": run_id,
        "session_id": session_id,
        "step_id": str(step_id or "") or None,
        "step_name": str(step_name or "") or None,
        "step_index": _step_index(event_value(event, "step_index")),
        "nested_depth": event_value(event, "nested_depth"),
        "parent_step_id": str(parent or "") or None if parent is not None else None,
    }



def _extract_user_input_schema(event: Any) -> list[Any] | None:
    """Best-effort pull of user_input_schema from pause event / requirements."""
    direct = event_value(event, "user_input_schema")
    if isinstance(direct, list) and direct:
        return list(direct)
    requirements = event_value(event, "step_requirements") or event_value(
        event, "requirements"
    )
    if isinstance(requirements, list):
        for item in requirements:
            if isinstance(item, dict):
                schema = item.get("user_input_schema") or item.get("schema")
                if isinstance(schema, list) and schema:
                    return list(schema)
            else:
                schema = getattr(item, "user_input_schema", None)
                if isinstance(schema, list) and schema:
                    return list(schema)
    return None


async def _create_workflow_step_approval(
    *,
    workflow_id: str,
    run_id: str,
    session_id: str,
    user_id: str,
    event: Any,
    model_id: str | None,
) -> str | None:
    """Persist a pending Approvals row for step HITL pauses."""
    step_name = str(
        event_value(event, "paused_step_name")
        or event_value(event, "step_name")
        or "step"
    )
    step_id = str(event_value(event, "step_id") or "") or None
    pause_kind = str(event_value(event, "pause_kind") or "confirmation").lower()
    if "user_input" in pause_kind or "input" in pause_kind:
        pause_type = "user_input"
        approval_type = "user_input"
    elif "output" in pause_kind or "review" in pause_kind:
        pause_type = "output_review"
        approval_type = "output_review"
    else:
        pause_type = "confirmation"
        approval_type = "confirmation"
    message = str(event_value(event, "content") or "") or f"Workflow step HITL: {step_name}"
    schema = event_value(event, "user_input_schema")
    if not isinstance(schema, list) or not schema:
        schema = _extract_user_input_schema(event)
    output_seed = (
        event_value(event, "output")
        or event_value(event, "content")
        or event_value(event, "previous_step_content")
        or event_value(event, "step_output")
    )
    approval_id = str(uuid4())
    now = int(__import__("time").time())
    payload = {
        "id": approval_id,
        "run_id": run_id,
        "session_id": session_id,
        "status": "pending",
        "source_type": "workflow",
        "approval_type": approval_type,
        "pause_type": pause_type,
        "tool_name": f"workflow.step:{step_name}",
        "tool_args": {
            "step_id": step_id,
            "step_name": step_name,
            "message": message,
            "pause_type": pause_type,
            "output": output_seed,
            "user_input_schema": schema,
            "workflow_id": workflow_id,
        },
        "workflow_id": workflow_id,
        "user_id": user_id,
        "source_name": step_name,
        "context": {
            "model_id": model_id,
            "pause_kind": event_value(event, "pause_kind"),
            "pause_type": pause_type,
        },
        "requirements": event_value(event, "step_requirements"),
        "run_status": "PAUSED",
        "created_at": now,
        "updated_at": now,
    }
    try:
        await get_async_agno_postgres_db().create_approval(payload)
    except Exception:
        logger.exception(
            "Failed to create workflow step approval for run {}", run_id
        )
        return None
    try:
        await notify_workflow_hitl_pending(
            approval_id=approval_id,
            workflow_id=workflow_id,
            step_name=step_name,
            submitter_user_id=user_id,
            run_id=run_id,
            session_id=session_id,
            pause_type=pause_type,
        )
    except Exception:
        logger.debug("workflow HITL notify failed for approval {}", approval_id)
    return approval_id


def is_workflow_step_approval(approval: dict[str, Any]) -> bool:
    return (
        str(approval.get("source_type") or "") == "workflow"
        and bool(str(approval.get("workflow_id") or ""))
        and bool(str(approval.get("run_id") or ""))
        and bool(str(approval.get("session_id") or ""))
    )


async def resume_workflow_run(approval_id: str) -> str:
    """Continue a paused workflow after Approvals resolve (background-friendly)."""
    db = get_async_agno_postgres_db()
    approval = await db.get_approval(approval_id)
    if not isinstance(approval, dict):
        raise ValueError(f"Approval {approval_id} not found")
    if not is_workflow_step_approval(approval):
        raise ValueError("Approval is not a workflow step confirmation")
    status = str(approval.get("status") or "")
    if status not in {"approved", "rejected"}:
        raise ValueError("Approval must be resolved before resuming workflow")

    workflow_id = str(approval["workflow_id"])
    run_id = str(approval["run_id"])
    session_id = str(approval["session_id"])
    context = approval.get("context") if isinstance(approval.get("context"), dict) else {}
    model_id = context.get("model_id") if isinstance(context, dict) else None
    model_id_str = str(model_id) if model_id else None

    row = await workflow_store.get_workflow(workflow_id)
    if row is None:
        raise ValueError(f"Workflow {workflow_id} not found")
    definition = row.get("definition")
    if not isinstance(definition, dict):
        raise ValueError("Workflow definition is invalid")

    workflow = await compile_workflow(
        definition,
        workflow_id=workflow_id,
        model_id=model_id_str,
    )
    run_response = await workflow.aget_run_output(run_id=run_id, session_id=session_id)
    if run_response is None:
        raise ValueError(f"Paused run {run_id} not found in session {session_id}")

    requirements = list(getattr(run_response, "step_requirements", None) or [])
    resolution_raw = approval.get("resolution_data")
    resolution: dict[str, Any] = (
        {str(k): v for k, v in resolution_raw.items()}
        if isinstance(resolution_raw, dict)
        else {}
    )
    pause_type = str(
        (approval.get("context") or {}).get("pause_type")
        if isinstance(approval.get("context"), dict)
        else approval.get("pause_type")
        or "confirmation"
    )
    if requirements:
        active = requirements[-1]
        if status == "rejected":
            note = resolution.get("note")
            if hasattr(active, "reject"):
                active.reject(str(note) if note else None)
            else:
                active.confirmed = False
        elif pause_type == "user_input":
            user_input = resolution.get("user_input")
            if isinstance(user_input, dict) and hasattr(active, "set_user_input"):
                active.set_user_input(user_input)
            elif hasattr(active, "confirm"):
                active.confirm()
            else:
                active.confirmed = True
        elif pause_type == "output_review":
            edited = resolution.get("edited_output")
            if edited is not None and hasattr(active, "edit"):
                active.edit(edited)
            elif hasattr(active, "confirm"):
                active.confirm()
            else:
                active.confirmed = True
        else:
            if hasattr(active, "confirm"):
                active.confirm()
            else:
                active.confirmed = True

    try:
        await db.update_approval(approval_id, run_status="RUNNING")
    except Exception:
        logger.debug("Could not mark workflow approval {} as RUNNING", approval_id)

    stream: Any = workflow.acontinue_run(
        run_response,
        stream=True,
        stream_events=True,
    )
    try:
        async for _event in stream:
            pass
        try:
            await db.update_approval(approval_id, run_status="COMPLETED")
        except Exception:
            logger.exception(
                "Could not mark workflow approval {} as COMPLETED", approval_id
            )
        return "COMPLETED"
    except Exception:
        logger.exception("Workflow continue failed for approval {}", approval_id)
        try:
            await db.update_approval(approval_id, run_status="ERROR")
        except Exception:
            logger.exception(
                "Could not mark workflow approval {} as ERROR", approval_id
            )
        raise


def schedule_workflow_resume(approval_id: str) -> None:
    """Fire-and-forget continue after Approvals resolve."""

    async def _job() -> None:
        try:
            await resume_workflow_run(approval_id)
        except Exception:
            logger.exception("Background workflow resume failed: {}", approval_id)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_job())
    except RuntimeError:
        asyncio.run(_job())


async def stream_workflow_run(
    *,
    workflow_id: str,
    definition: dict[str, Any],
    input_text: str,
    user_id: str,
    session_id: str | None = None,
    model_id: str | None = None,
    run_id: str | None = None,
) -> AsyncIterator[WorkflowRunEventOut]:
    """Compile definition and stream workflow lifecycle events."""
    active_run_id = (run_id or "").strip() or str(uuid4())
    active_session_id = (session_id or "").strip() or str(uuid4())
    bound_skill_names = collect_workflow_skill_names(definition)
    loaded_skill_dirs = resolve_enabled_skill_dirs(bound_skill_names)
    loaded_skill_names = [
        path.name for path in loaded_skill_dirs
    ]
    workflow = await compile_workflow(
        definition,
        workflow_id=workflow_id,
        model_id=model_id,
    )

    if bound_skill_names:
        try:
            await record_audit_event_async(
                actor=SimpleNamespace(
                    id=user_id or "system",
                    email="",
                    role="user",
                    is_superuser=False,
                ),
                action="skill.load",
                resource_type="workflow",
                resource_id=workflow_id,
                status="success",
                metadata={
                    "workflow_id": workflow_id,
                    "run_id": active_run_id,
                    "session_id": active_session_id,
                    "skill_names": bound_skill_names,
                    "loaded_skill_names": loaded_skill_names,
                    "source": "workflow_run",
                },
            )
        except Exception:
            logger.debug("skill.load audit failed for workflow {}", workflow_id)

    yield WorkflowRunEventOut(
        "workflow.started",
        {
            "workflow_id": workflow_id,
            "run_id": active_run_id,
            "session_id": active_session_id,
            "name": getattr(workflow, "name", None) or definition.get("name") or "",
            "skills": bound_skill_names,
            "loaded_skills": loaded_skill_names,
        },
    )

    try:
        stream_result = workflow.arun(
            input=input_text,
            user_id=user_id,
            session_id=active_session_id,
            run_id=active_run_id,
            stream=True,
            stream_events=True,
        )
        # Agno Workflow.arun is overloaded: stream=True -> AsyncIterator; the
        # untyped implementation still types as a union, so normalize here.
        if isawaitable(stream_result):
            stream_result = await stream_result
        stream = cast(AsyncIterator[Any], stream_result)
        async for event in stream:
            event_name = str(event_value(event, "event", "") or "")
            run_id_value = str(event_value(event, "run_id", active_run_id) or active_run_id)
            session_value = str(
                event_value(event, "session_id", active_session_id) or active_session_id
            )
            base = _base_payload(
                workflow_id=workflow_id,
                run_id=run_id_value,
                session_id=session_value,
                event=event,
            )

            if event_name == WorkflowRunEvent.workflow_started.value:
                yield WorkflowRunEventOut(
                    "workflow.started",
                    {
                        "workflow_id": workflow_id,
                        "run_id": run_id_value,
                        "session_id": session_value,
                        "name": str(event_value(event, "workflow_name", "") or ""),
                    },
                )
            elif event_name == WorkflowRunEvent.step_started.value:
                yield WorkflowRunEventOut("step.started", base)
            elif event_name == WorkflowRunEvent.step_completed.value:
                yield WorkflowRunEventOut(
                    "step.completed",
                    {**base, "content": _preview(event_value(event, "content"))},
                )
            elif event_name == WorkflowRunEvent.step_error.value:
                yield WorkflowRunEventOut(
                    "step.error",
                    {
                        **base,
                        "message": str(
                            event_value(event, "error", "step failed") or "step failed"
                        ),
                    },
                )
            elif event_name == WorkflowRunEvent.parallel_execution_started.value:
                yield WorkflowRunEventOut(
                    "parallel.started",
                    {
                        **base,
                        "parallel_step_count": event_value(event, "parallel_step_count"),
                    },
                )
            elif event_name == WorkflowRunEvent.parallel_execution_completed.value:
                yield WorkflowRunEventOut(
                    "parallel.completed",
                    {
                        **base,
                        "parallel_step_count": event_value(event, "parallel_step_count"),
                    },
                )
            elif event_name == WorkflowRunEvent.condition_execution_started.value:
                yield WorkflowRunEventOut(
                    "condition.started",
                    {
                        **base,
                        "condition_result": event_value(event, "condition_result"),
                    },
                )
            elif event_name == WorkflowRunEvent.condition_execution_completed.value:
                yield WorkflowRunEventOut(
                    "condition.completed",
                    {
                        **base,
                        "condition_result": event_value(event, "condition_result"),
                        "branch": event_value(event, "branch"),
                    },
                )
            elif event_name == WorkflowRunEvent.loop_execution_started.value:
                yield WorkflowRunEventOut(
                    "loop.started",
                    {
                        **base,
                        "max_iterations": event_value(event, "max_iterations"),
                    },
                )
            elif event_name == WorkflowRunEvent.loop_execution_completed.value:
                yield WorkflowRunEventOut(
                    "loop.completed",
                    {
                        **base,
                        "total_iterations": event_value(event, "total_iterations"),
                        "max_iterations": event_value(event, "max_iterations"),
                    },
                )
            elif event_name == WorkflowRunEvent.loop_iteration_started.value:
                yield WorkflowRunEventOut(
                    "loop.iteration.started",
                    {
                        **base,
                        "iteration": event_value(event, "iteration"),
                        "max_iterations": event_value(event, "max_iterations"),
                    },
                )
            elif event_name == WorkflowRunEvent.loop_iteration_completed.value:
                yield WorkflowRunEventOut(
                    "loop.iteration.completed",
                    {
                        **base,
                        "iteration": event_value(event, "iteration"),
                        "max_iterations": event_value(event, "max_iterations"),
                        "should_continue": event_value(event, "should_continue"),
                    },
                )
            
            elif event_name == WorkflowRunEvent.router_execution_started.value:
                yield WorkflowRunEventOut(
                    "router.started",
                    {
                        **base,
                        "selected": event_value(event, "selected_steps")
                        or event_value(event, "selected"),
                    },
                )
            elif event_name == WorkflowRunEvent.router_execution_completed.value:
                yield WorkflowRunEventOut(
                    "router.completed",
                    {
                        **base,
                        "selected": event_value(event, "selected_steps")
                        or event_value(event, "selected"),
                    },
                )
            elif event_name == WorkflowRunEvent.router_paused.value:
                approval_id = await _create_workflow_step_approval(
                    workflow_id=workflow_id,
                    run_id=run_id_value,
                    session_id=session_value,
                    user_id=user_id,
                    event=event,
                    model_id=model_id,
                )
                yield WorkflowRunEventOut(
                    "workflow.paused",
                    {
                        "workflow_id": workflow_id,
                        "run_id": run_id_value,
                        "session_id": session_value,
                        "step_id": str(event_value(event, "step_id") or "") or None,
                        "step_name": str(event_value(event, "step_name", "") or "") or None,
                        "pause_type": "confirmation",
                        "approval_id": approval_id,
                        "message": "Router paused for HITL selection — resolve in Approvals",
                    },
                )
                return

            elif event_name == WorkflowRunEvent.workflow_completed.value:
                yield WorkflowRunEventOut(
                    "workflow.completed",
                    {
                        "workflow_id": workflow_id,
                        "run_id": run_id_value,
                        "session_id": session_value,
                        "content": _preview(event_value(event, "content")),
                    },
                )
            elif event_name == WorkflowRunEvent.workflow_error.value:
                yield WorkflowRunEventOut(
                    "workflow.failed",
                    {
                        "workflow_id": workflow_id,
                        "run_id": run_id_value,
                        "session_id": session_value,
                        "code": "WORKFLOW_ERROR",
                        "message": str(
                            event_value(event, "error", "workflow failed") or "workflow failed"
                        ),
                    },
                )
            elif event_name == WorkflowRunEvent.workflow_cancelled.value:
                yield WorkflowRunEventOut(
                    "workflow.cancelled",
                    {
                        "workflow_id": workflow_id,
                        "run_id": run_id_value,
                        "session_id": session_value,
                        "reason": str(event_value(event, "reason", "cancelled") or "cancelled"),
                    },
                )
            elif event_name == WorkflowRunEvent.workflow_paused.value:
                approval_id = await _create_workflow_step_approval(
                    workflow_id=workflow_id,
                    run_id=run_id_value,
                    session_id=session_value,
                    user_id=user_id,
                    event=event,
                    model_id=model_id,
                )
                yield WorkflowRunEventOut(
                    "workflow.paused",
                    {
                        "workflow_id": workflow_id,
                        "run_id": run_id_value,
                        "session_id": session_value,
                        "step_id": str(event_value(event, "step_id") or "") or None,
                        "step_name": str(
                            event_value(event, "paused_step_name", "")
                            or event_value(event, "step_name", "")
                            or ""
                        )
                        or None,
                        "pause_type": str(
                            event_value(event, "pause_kind") or "confirmation"
                        ),
                        "approval_id": approval_id,
                        "message": "Workflow paused for step HITL — resolve in Approvals",
                    },
                )
                return
    except Exception as exc:
        logger.exception("Workflow run failed: {}", workflow_id)
        yield WorkflowRunEventOut(
            "workflow.failed",
            {
                "workflow_id": workflow_id,
                "run_id": active_run_id,
                "session_id": active_session_id,
                "code": "WORKFLOW_RUN_ERROR",
                "message": f"{type(exc).__name__}: {exc}",
            },
        )
