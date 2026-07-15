"""Stream Agno Workflow runs as workbench SSE events (PR1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator
from uuid import uuid4

from agno.run.workflow import WorkflowRunEvent
from loguru import logger

from api.services.chat_run_events import event_value
from api.services.workflow_compiler import compile_workflow


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
    workflow = await compile_workflow(
        definition,
        workflow_id=workflow_id,
        model_id=model_id,
    )

    yield WorkflowRunEventOut(
        "workflow.started",
        {
            "workflow_id": workflow_id,
            "run_id": active_run_id,
            "session_id": active_session_id,
            "name": getattr(workflow, "name", None) or definition.get("name") or "",
        },
    )

    try:
        stream = workflow.arun(
            input=input_text,
            user_id=user_id,
            session_id=active_session_id,
            run_id=active_run_id,
            stream=True,
            stream_events=True,
        )
        # Agno returns AsyncIterator when stream=True
        async for event in stream:  # type: ignore[union-attr]
            event_name = str(event_value(event, "event", "") or "")
            run_id_value = str(event_value(event, "run_id", active_run_id) or active_run_id)
            session_value = str(
                event_value(event, "session_id", active_session_id) or active_session_id
            )
            step_name = event_value(event, "step_name")
            step_id = event_value(event, "step_id")
            step_index = _step_index(event_value(event, "step_index"))

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
                yield WorkflowRunEventOut(
                    "step.started",
                    {
                        "workflow_id": workflow_id,
                        "run_id": run_id_value,
                        "session_id": session_value,
                        "step_id": str(step_id or "") or None,
                        "step_name": str(step_name or "") or None,
                        "step_index": step_index,
                    },
                )
            elif event_name == WorkflowRunEvent.step_completed.value:
                yield WorkflowRunEventOut(
                    "step.completed",
                    {
                        "workflow_id": workflow_id,
                        "run_id": run_id_value,
                        "session_id": session_value,
                        "step_id": str(step_id or "") or None,
                        "step_name": str(step_name or "") or None,
                        "step_index": step_index,
                        "content": _preview(event_value(event, "content")),
                    },
                )
            elif event_name == WorkflowRunEvent.step_error.value:
                yield WorkflowRunEventOut(
                    "step.error",
                    {
                        "workflow_id": workflow_id,
                        "run_id": run_id_value,
                        "session_id": session_value,
                        "step_id": str(step_id or "") or None,
                        "step_name": str(step_name or "") or None,
                        "step_index": step_index,
                        "message": str(event_value(event, "error", "step failed") or "step failed"),
                    },
                )
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
                yield WorkflowRunEventOut(
                    "workflow.paused",
                    {
                        "workflow_id": workflow_id,
                        "run_id": run_id_value,
                        "session_id": session_value,
                        "step_name": str(event_value(event, "paused_step_name", "") or "") or None,
                        "message": "Workflow paused (HITL not fully wired in PR1)",
                    },
                )
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
