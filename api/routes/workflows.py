from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from api.auth.claims import actor_id
from api.auth.models import User
from api.auth.scopes import require_scope
from api.services.audit_service import (
    audit_request_context,
    list_audit_events_async,
    record_audit_event_async,
)
from api.services.workflow_compiler import WorkflowDefinitionError
from api.services.workflow_run_runtime import stream_workflow_run
from api.services.workflow_templates import list_workflow_templates
from api.services.notification_service import notify_workflow_trigger_failure
from api.services.workflow_service import (
    create_workflow_for_actor,
    delete_workflow_for_actor,
    executor_catalog,
    get_published_definition,
    get_workflow_for_actor,
    list_versions_for_actor,
    list_workflows_for_actor,
    publish_workflow_for_actor,
    restore_version_for_actor,
    update_workflow_for_actor,
    verify_webhook_secret,
)
from api.persistence import workflows as workflow_store
from api.utils.pagination import pagination_meta

router = APIRouter(prefix="/api/workflows", tags=["Workflows"])


class WorkflowWriteRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    definition: dict[str, Any] = Field(default_factory=dict)
    enabled: bool | None = None
    triggers: dict[str, Any] | None = None


class WorkflowRunRequest(BaseModel):
    """Studio run body. Empty input is normalized to a default token server-side."""
    input: str = Field(default="", max_length=100_000)
    session_id: str | None = None
    model_id: str | None = None


@router.get("/executors")
async def list_executors(user: User = Depends(require_scope("workflows:read"))):
    return {"data": executor_catalog()}


@router.get("/templates")
async def list_templates(user: User = Depends(require_scope("workflows:read"))):
    """Built-in security workflow templates."""
    return {"data": list_workflow_templates()}


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


@router.post("/{workflow_id}/publish")
async def publish_workflow(
    workflow_id: str,
    request: Request,
    user: User = Depends(require_scope("workflows:write")),
):
    """Promote current draft definition to the published revision used by webhook/cron."""
    try:
        row = await publish_workflow_for_actor(user, workflow_id)
    except WorkflowDefinitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    ctx = audit_request_context(request)
    await record_audit_event_async(
        actor=user,
        action="workflow.publish",
        resource_type="workflow",
        resource_id=workflow_id,
        status="success",
        metadata={
            "published_version": row.get("published_version"),
            "version": row.get("version"),
        },
        ip_address=ctx["ip_address"] if ctx else "",
        user_agent=ctx["user_agent"] if ctx else "",
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
    definition = get_published_definition(row)
    if definition is None:
        raise HTTPException(
            status_code=409,
            detail="Workflow has no published revision; publish before triggering",
        )
    input_text = (body.input if body else "") or "webhook trigger"
    session_id = str(uuid4())
    run_id = str(uuid4())
    owner = str(row.get("owner_user_id") or "system")
    actor = SimpleNamespace(
        id=owner,
        email="system@workflow-webhook",
        role="system",
        is_superuser=False,
    )
    ctx = audit_request_context(request)

    async def event_generator():
        terminal = "error"
        try:
            await record_audit_event_async(
                actor=actor,
                action="workflow.trigger.webhook",
                resource_type="workflow",
                resource_id=workflow_id,
                status="started",
                metadata={
                    "run_id": run_id,
                    "session_id": session_id,
                    "source": "webhook",
                },
                ip_address=ctx["ip_address"],
                user_agent=ctx["user_agent"],
            )
            async for event in stream_workflow_run(
                workflow_id=workflow_id,
                definition=definition,
                input_text=input_text,
                user_id=owner,
                session_id=session_id,
                model_id=body.model_id if body else None,
                run_id=run_id,
            ):
                if event.event == "workflow.completed":
                    terminal = "success"
                elif event.event == "workflow.paused":
                    terminal = "paused"
                elif event.event == "workflow.cancelled":
                    terminal = "cancelled"
                elif event.event == "workflow.failed":
                    terminal = "error"
                yield {
                    "event": event.event,
                    "data": json.dumps(event.data, ensure_ascii=False),
                }
        except Exception as exc:
            terminal = "error"
            logger.exception("webhook workflow failed: {}", workflow_id)
            yield {
                "event": "workflow.failed",
                "data": json.dumps(
                    {
                        "workflow_id": workflow_id,
                        "run_id": run_id,
                        "session_id": session_id,
                        "code": "WORKFLOW_WEBHOOK_ERROR",
                        "message": f"{type(exc).__name__}: {exc}",
                    },
                    ensure_ascii=False,
                ),
            }
        finally:
            await record_audit_event_async(
                actor=actor,
                action="workflow.trigger.webhook",
                resource_type="workflow",
                resource_id=workflow_id,
                status=terminal,
                metadata={
                    "run_id": run_id,
                    "session_id": session_id,
                    "source": "webhook",
                },
                ip_address=ctx["ip_address"],
                user_agent=ctx["user_agent"],
            )
            if terminal == "error":
                await notify_workflow_trigger_failure(
                    workflow_id=workflow_id,
                    workflow_name=str(row.get("name") or workflow_id),
                    owner_user_id=owner,
                    source="webhook",
                    run_id=run_id,
                    session_id=session_id,
                    error="Webhook workflow run failed",
                )

    return EventSourceResponse(event_generator())


@router.get("/{workflow_id}/triggers/history")
async def list_workflow_trigger_history(
    workflow_id: str,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_scope("workflows:read")),
):
    """Recent cron/webhook trigger audit events for Studio trigger panel."""
    row = await get_workflow_for_actor(user, workflow_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    # Pull a wider window then filter by trigger actions (audit API is exact-match on action).
    window = min(200, max(limit * 5, 50))
    cron_items, _ = await list_audit_events_async(
        page=1,
        limit=window,
        action="workflow.trigger.cron",
        resource_type="workflow",
        resource_id=workflow_id,
    )
    webhook_items, _ = await list_audit_events_async(
        page=1,
        limit=window,
        action="workflow.trigger.webhook",
        resource_type="workflow",
        resource_id=workflow_id,
    )
    merged = [*cron_items, *webhook_items]

    def _sort_key(item: dict[str, Any]) -> tuple:
        created = item.get("created_at")
        # datetime or iso string
        return (str(created or ""), str(item.get("id") or ""))

    merged.sort(key=_sort_key, reverse=True)
    # Prefer terminal statuses over "started" for same run_id
    seen_runs: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in merged:
        meta_raw = item.get("metadata")
        meta: dict[str, Any] = meta_raw if isinstance(meta_raw, dict) else {}
        run_id = str(meta.get("run_id") or item.get("id") or "")
        status = str(item.get("status") or "")
        if status == "started" and run_id in seen_runs:
            continue
        if run_id and status != "started":
            seen_runs.add(run_id)
        # skip pure started if we already have terminal for same run
        if status == "started" and run_id:
            has_terminal = False
            for prior in deduped:
                prior_meta_raw = prior.get("metadata")
                prior_meta = prior_meta_raw if isinstance(prior_meta_raw, dict) else {}
                if str(prior_meta.get("run_id") or "") == run_id and str(
                    prior.get("status") or ""
                ) != "started":
                    has_terminal = True
                    break
            if has_terminal:
                continue
        deduped.append(item)
    total = len(deduped)
    start_idx = (page - 1) * limit
    page_items = deduped[start_idx : start_idx + limit]
    data: list[dict[str, Any]] = []
    for item in page_items:
        meta_raw = item.get("metadata")
        meta = meta_raw if isinstance(meta_raw, dict) else {}
        created = item.get("created_at")
        if hasattr(created, "isoformat"):
            created_at = created.isoformat()
        else:
            created_at = str(created or "")
        action = str(item.get("action") or "")
        source = str(meta.get("source") or "")
        if not source:
            source = "cron" if action.endswith(".cron") else "webhook"
        data.append(
            {
                "id": item.get("id"),
                "action": action,
                "status": item.get("status"),
                "source": source,
                "run_id": str(meta.get("run_id") or ""),
                "session_id": str(meta.get("session_id") or ""),
                "expression": str(meta.get("expression") or ""),
                "created_at": created_at,
            }
        )
    return {
        "data": data,
        "meta": pagination_meta(page=page, limit=limit, total_count=total),
    }


@router.post("/{workflow_id}/runs")
async def run_workflow(
    workflow_id: str,
    body: WorkflowRunRequest,
    request: Request,
    user: User = Depends(require_scope("workflows:run")),
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
    input_text = (body.input or "").strip() or "workflow run"
    ctx = audit_request_context(request)

    async def event_generator():
        terminal = "success"
        try:
            async for event in stream_workflow_run(
                workflow_id=workflow_id,
                definition=definition,
                input_text=input_text,
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
