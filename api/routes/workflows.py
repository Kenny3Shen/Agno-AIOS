from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from api.auth.claims import actor_id
from api.auth.models import User
from api.auth.scopes import require_scope
from api.services.audit_service import audit_request_context, record_audit_event_async
from api.services.workflow_compiler import WorkflowDefinitionError
from api.services.workflow_run_runtime import stream_workflow_run
from api.services.workflow_service import (
    create_workflow_for_actor,
    delete_workflow_for_actor,
    executor_catalog,
    get_workflow_for_actor,
    list_versions_for_actor,
    list_workflows_for_actor,
    restore_version_for_actor,
    update_workflow_for_actor,
    verify_webhook_secret,
)
from api.persistence import workflows as workflow_store

router = APIRouter(prefix="/api/workflows", tags=["Workflows"])


class WorkflowWriteRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    definition: dict[str, Any] = Field(default_factory=dict)
    enabled: bool | None = None
    triggers: dict[str, Any] | None = None


class WorkflowRunRequest(BaseModel):
    input: str = Field(..., min_length=1)
    session_id: str | None = None
    model_id: str | None = None


@router.get("/executors")
async def list_executors(user: User = Depends(require_scope("workflows:read"))):
    return {"data": executor_catalog()}


@router.get("")
async def list_workflows(
    user_id: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_scope("workflows:read")),
):
    return await list_workflows_for_actor(
        user, user_id=user_id, page=page, limit=limit
    )


@router.post("")
async def create_workflow(
    body: WorkflowWriteRequest,
    request: Request,
    user: User = Depends(require_scope("workflows:write")),
):
    try:
        row = await create_workflow_for_actor(
            user,
            name=body.name,
            description=body.description,
            definition=body.definition,
            triggers=body.triggers,
        )
    except WorkflowDefinitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    ctx = audit_request_context(request)
    await record_audit_event_async(
        actor=user,
        action="workflow.create",
        resource_type="workflow",
        resource_id=row["id"],
        status="success",
        metadata={"name": row.get("name") or ""},
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return row


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    user: User = Depends(require_scope("workflows:read")),
):
    row = await get_workflow_for_actor(user, workflow_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return row


@router.patch("/{workflow_id}")
async def patch_workflow(
    workflow_id: str,
    body: WorkflowWriteRequest,
    request: Request,
    user: User = Depends(require_scope("workflows:write")),
):
    try:
        row = await update_workflow_for_actor(
            user,
            workflow_id,
            name=body.name,
            description=body.description,
            definition=body.definition if body.definition else None,
            enabled=body.enabled,
            triggers=body.triggers,
        )
    except WorkflowDefinitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    ctx = audit_request_context(request)
    await record_audit_event_async(
        actor=user,
        action="workflow.update",
        resource_type="workflow",
        resource_id=workflow_id,
        status="success",
        metadata={"version": row.get("version")},
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return row


@router.delete("/{workflow_id}")
async def remove_workflow(
    workflow_id: str,
    request: Request,
    user: User = Depends(require_scope("workflows:write")),
):
    deleted = await delete_workflow_for_actor(user, workflow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")
    ctx = audit_request_context(request)
    await record_audit_event_async(
        actor=user,
        action="workflow.delete",
        resource_type="workflow",
        resource_id=workflow_id,
        status="success",
        metadata={},
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return {"success": True}



@router.get("/{workflow_id}/versions")
async def list_workflow_versions(
    workflow_id: str,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_scope("workflows:read")),
):
    payload = await list_versions_for_actor(
        user, workflow_id, page=page, limit=limit
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return payload


@router.post("/{workflow_id}/versions/{version}/restore")
async def restore_workflow_version(
    workflow_id: str,
    version: int,
    request: Request,
    user: User = Depends(require_scope("workflows:write")),
):
    row = await restore_version_for_actor(user, workflow_id, version)
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow or version not found")
    ctx = audit_request_context(request)
    await record_audit_event_async(
        actor=user,
        action="workflow.version.restore",
        resource_type="workflow",
        resource_id=workflow_id,
        status="success",
        metadata={"version": version, "new_version": row.get("version")},
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return row


@router.post("/{workflow_id}/hooks/webhook")
async def webhook_trigger_workflow(
    workflow_id: str,
    request: Request,
    secret: str | None = Query(default=None),
    body: WorkflowRunRequest | None = None,
):
    """Public webhook trigger when enabled; auth via shared secret query/header."""
    row = await workflow_store.get_workflow(workflow_id)
    if row is None or not row.get("enabled", True):
        raise HTTPException(status_code=404, detail="Workflow not found")
    header_secret = request.headers.get("x-workflow-secret")
    if not verify_webhook_secret(row, secret or header_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    definition = row.get("definition")
    if not isinstance(definition, dict):
        raise HTTPException(status_code=422, detail="Workflow definition is invalid")
    input_text = (body.input if body else "") or "webhook trigger"
    session_id = str(uuid4())
    run_id = str(uuid4())
    owner = str(row.get("owner_user_id") or "system")

    async def event_generator():
        try:
            async for event in stream_workflow_run(
                workflow_id=workflow_id,
                definition=definition,
                input_text=input_text,
                user_id=owner,
                session_id=session_id,
                model_id=body.model_id if body else None,
                run_id=run_id,
            ):
                yield {
                    "event": event.event,
                    "data": json.dumps(event.data, ensure_ascii=False),
                }
        except Exception as exc:
            logger.exception("webhook workflow failed: {}", workflow_id)
            yield {
                "event": "workflow.failed",
                "data": json.dumps(
                    {
                        "workflow_id": workflow_id,
                        "run_id": run_id,
                        "message": f"{type(exc).__name__}: {exc}",
                    },
                    ensure_ascii=False,
                ),
            }

    return EventSourceResponse(event_generator())


@router.post("/{workflow_id}/runs")
async def run_workflow(
    workflow_id: str,
    body: WorkflowRunRequest,
    request: Request,
    user: User = Depends(require_scope("workflows:write")),
):
    row = await get_workflow_for_actor(user, workflow_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if not row.get("enabled", True):
        raise HTTPException(status_code=409, detail="Workflow is disabled")
    definition = row.get("definition")
    if not isinstance(definition, dict):
        raise HTTPException(status_code=422, detail="Workflow definition is invalid")

    session_id = (body.session_id or "").strip() or str(uuid4())
    run_id = str(uuid4())
    ctx = audit_request_context(request)

    async def event_generator():
        terminal = "success"
        try:
            async for event in stream_workflow_run(
                workflow_id=workflow_id,
                definition=definition,
                input_text=body.input,
                user_id=actor_id(user),
                session_id=session_id,
                model_id=body.model_id,
                run_id=run_id,
            ):
                if event.event in {"workflow.failed", "workflow.cancelled"}:
                    terminal = "error" if event.event == "workflow.failed" else "cancelled"
                elif event.event == "workflow.paused":
                    terminal = "paused"
                yield {
                    "event": event.event,
                    "data": json.dumps(event.data, ensure_ascii=False),
                }
        except Exception as exc:
            terminal = "error"
            logger.exception("workflow SSE failed: {}", workflow_id)
            yield {
                "event": "workflow.failed",
                "data": json.dumps(
                    {
                        "workflow_id": workflow_id,
                        "run_id": run_id,
                        "session_id": session_id,
                        "code": "WORKFLOW_STREAM_ERROR",
                        "message": f"{type(exc).__name__}: {exc}",
                    },
                    ensure_ascii=False,
                ),
            }
        finally:
            await record_audit_event_async(
                actor=user,
                action="workflow.run",
                resource_type="workflow",
                resource_id=run_id,
                status=terminal,
                metadata={
                    "workflow_id": workflow_id,
                    "session_id": session_id,
                    "model_id": body.model_id or "",
                },
                ip_address=ctx["ip_address"] if ctx else "",
                user_agent=ctx["user_agent"] if ctx else "",
            )

    return EventSourceResponse(event_generator())
