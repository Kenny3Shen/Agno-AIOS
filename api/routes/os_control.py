from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, Field

from api.auth.claims import actor_id, has_permission
from api.auth.permissions import require_permission
from api.auth.models import User
from api.auth.users import current_active_user
from api.services.approval_control_service import (
    ApprovalListParams,
    ApprovalResolveConflictError,
    get_approval_record,
    list_approvals_payload,
    resolve_approval_record,
)
from api.services.os_control_service import (
    MemoryMutationNotFound,
    delete_memory_record,
    get_control_payload,
    update_memory_record,
)
from api.services.postgres_store import get_async_agno_postgres_db
from api.services.scheduler_service import (
    create_schedule,
    delete_schedule,
    get_schedule,
    list_schedule_runs,
    schedule_run_to_dict,
    set_schedule_enabled,
    update_schedule,
)
from api.services.security_policy import (
    PolicyAuditEvent,
    record_policy_event,
    require_control_module_access,
)

router = APIRouter(prefix="/api/os", tags=["AgentOS Control Plane"])


class ScheduleCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    target_type: str = Field("workflow", pattern="^(agent|team|workflow)$")
    target_id: str = Field(..., min_length=1)
    cron_expr: str = Field(..., min_length=1)
    description: str = ""
    payload: dict[str, object] = Field(default_factory=dict)
    timezone: str = "UTC"
    timeout_seconds: int = Field(default=3600, ge=1, le=86400)
    max_retries: int = Field(default=0, ge=0, le=10)
    retry_delay_seconds: int = Field(default=60, ge=1, le=3600)
    enabled: bool = True


class ScheduleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    target_type: str | None = Field(default=None, pattern="^(agent|team|workflow)$")
    target_id: str | None = Field(default=None, min_length=1)
    cron_expr: str | None = Field(default=None, min_length=1)
    description: str | None = None
    payload: dict[str, object] | None = None
    timezone: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=86400)
    max_retries: int | None = Field(default=None, ge=0, le=10)
    retry_delay_seconds: int | None = Field(default=None, ge=1, le=3600)


class ScheduleCreateResponse(BaseModel):
    id: str
    name: str = ""
    enabled: bool
    endpoint: str = ""
    cron_expr: str = ""
    timezone: str = "UTC"


class ApprovalResolveRequest(BaseModel):
    status: Literal["approved", "rejected"]
    resolution_data: dict[str, object] | None = None


class MemoryUpdateRequest(BaseModel):
    user_id: str | None = None
    memory: str = Field(..., min_length=1)
    topics: list[str] = Field(default_factory=list)


def require_os_module_permission(
    module: str,
    user: User = Depends(current_active_user),
) -> User:
    require_control_module_access(module, user)
    return user


def require_memory_write_permission(
    user: User = Depends(current_active_user),
) -> User:
    require_control_module_access("memory", user)
    if not has_permission(user, "memory:write:own"):
        raise HTTPException(status_code=403, detail="权限不足")
    return user


def _resolver_id(user: User) -> str:
    return str(getattr(user, "email", "") or actor_id(user) or "system")


@router.get("/approvals")
async def list_os_approvals(
    status: str | None = None,
    source_type: str | None = None,
    approval_type: str | None = None,
    pause_type: str | None = None,
    agent_id: str | None = None,
    team_id: str | None = None,
    workflow_id: str | None = None,
    user_id: str | None = None,
    schedule_id: str | None = None,
    run_id: str | None = None,
    page: int = 1,
    limit: int = 50,
    user: User = Depends(require_permission("admin:read")),
):
    try:
        return await list_approvals_payload(
            params=ApprovalListParams(
                status=status,
                source_type=source_type,
                approval_type=approval_type,
                pause_type=pause_type,
                agent_id=agent_id,
                team_id=team_id,
                workflow_id=workflow_id,
                user_id=user_id,
                schedule_id=schedule_id,
                run_id=run_id,
                page=page,
                limit=limit,
            ),
            actor=user,
        )
    except Exception as exc:
        logger.error(f"获取 Agno 审批列表失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to load approvals") from exc


@router.get("/approvals/{approval_id}")
async def get_os_approval(
    approval_id: str,
    user: User = Depends(require_permission("admin:read")),
):
    try:
        approval = await get_approval_record(approval_id)
    except Exception as exc:
        logger.error(f"获取 Agno 审批详情失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to load approval") from exc
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return approval


@router.post("/approvals/{approval_id}/resolve")
async def resolve_os_approval(
    approval_id: str,
    body: ApprovalResolveRequest,
    request: Request,
    user: User = Depends(require_permission("admin:read")),
):
    try:
        approval = await resolve_approval_record(
            approval_id,
            status=body.status,
            resolved_by=_resolver_id(user),
            resolution_data=body.resolution_data,
        )
    except ApprovalResolveConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"处理 Agno 审批失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to resolve approval") from exc
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    await record_policy_event(
        user,
        PolicyAuditEvent(
            action=f"approvals.{body.status}",
            resource_type="approval",
            resource_id=approval_id,
            metadata={
                "status": body.status,
                "run_id": approval.get("run_id"),
                "session_id": approval.get("session_id"),
                "source_type": approval.get("source_type"),
            },
        ),
        request,
    )
    return approval


@router.delete("/memory/{memory_id}")
async def delete_os_memory(
    memory_id: str,
    request: Request,
    user_id: str | None = None,
    user: User = Depends(require_memory_write_permission),
):
    try:
        result = await delete_memory_record(user, memory_id=memory_id, user_id=user_id)
    except MemoryMutationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"删除 Agno memory 失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to delete memory") from exc
    await record_policy_event(
        user,
        PolicyAuditEvent(
            action="memory.delete",
            resource_type="memory",
            resource_id=memory_id,
            metadata={"user_id": result.get("user_id", "")},
        ),
        request,
    )
    return result


@router.patch("/memory/{memory_id}")
async def update_os_memory(
    memory_id: str,
    body: MemoryUpdateRequest,
    request: Request,
    user: User = Depends(require_memory_write_permission),
):
    try:
        result = await update_memory_record(
            user,
            memory_id=memory_id,
            user_id=body.user_id,
            memory=body.memory,
            topics=body.topics,
        )
    except MemoryMutationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"更新 Agno memory 失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to update memory") from exc
    await record_policy_event(
        user,
        PolicyAuditEvent(
            action="memory.update",
            resource_type="memory",
            resource_id=memory_id,
            metadata={
                "user_id": result.get("user_id", ""),
                "topics": len(result.get("topics", [])),
            },
        ),
        request,
    )
    return result


@router.get("/{module}")
async def get_os_control_module(
    module: str,
    user_id: str | None = None,
    topic: str | None = None,
    search: str | None = None,
    page: int = 1,
    limit: int = 50,
    user: User = Depends(require_os_module_permission),
):
    try:
        query: dict[str, Any] | None = None
        if module == "memory":
            query = {
                "user_id": user_id,
                "topic": topic,
                "search": search,
                "page": page,
                "limit": limit,
            }
        return await get_control_payload(module, actor=user, query=query)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unsupported control module: {module}") from exc
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"获取 AgentOS 控制面模块失败: {module}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/scheduler", response_model=ScheduleCreateResponse)
async def create_scheduler_job(
    request: Request,
    body: ScheduleCreateRequest,
    user: User = Depends(require_permission("admin:read")),
):
    try:
        schedule = await create_schedule(
            name=body.name,
            target_type=body.target_type,
            target_id=body.target_id,
            cron_expr=body.cron_expr,
            description=body.description,
            payload=body.payload,
            timezone=body.timezone,
            timeout_seconds=body.timeout_seconds,
            max_retries=body.max_retries,
            retry_delay_seconds=body.retry_delay_seconds,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"创建 Scheduler 任务失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    await record_policy_event(
        user,
        PolicyAuditEvent(
            action="scheduler.create",
            resource_type="schedule",
            resource_id=schedule["id"],
            metadata={"name": schedule["name"], "endpoint": schedule["endpoint"]},
        ),
        request,
    )
    return ScheduleCreateResponse(**schedule)


@router.patch("/scheduler/{schedule_id}")
async def update_scheduler_job(
    schedule_id: str,
    body: ScheduleUpdateRequest,
    request: Request,
    user: User = Depends(require_permission("admin:read")),
):
    try:
        schedule = await update_schedule(schedule_id, **body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"更新 Scheduler 任务失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await record_policy_event(
        user,
        PolicyAuditEvent(
            action="scheduler.update",
            resource_type="schedule",
            resource_id=schedule_id,
            metadata={"updates": body.model_dump(exclude_unset=True)},
        ),
        request,
    )
    return schedule


async def _set_scheduler_job_enabled(
    schedule_id: str,
    enabled: bool,
    request: Request,
    user: User,
) -> dict[str, Any]:
    try:
        schedule = await set_schedule_enabled(schedule_id, enabled)
    except Exception as exc:
        logger.error(f"切换 Scheduler 任务状态失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await record_policy_event(
        user,
        PolicyAuditEvent(
            action="scheduler.enable" if enabled else "scheduler.disable",
            resource_type="schedule",
            resource_id=schedule_id,
            metadata={"enabled": enabled},
        ),
        request,
    )
    return schedule


@router.post("/scheduler/{schedule_id}/enable")
async def enable_scheduler_job(
    schedule_id: str,
    request: Request,
    user: User = Depends(require_permission("admin:read")),
):
    return await _set_scheduler_job_enabled(schedule_id, True, request, user)


@router.post("/scheduler/{schedule_id}/disable")
async def disable_scheduler_job(
    schedule_id: str,
    request: Request,
    user: User = Depends(require_permission("admin:read")),
):
    return await _set_scheduler_job_enabled(schedule_id, False, request, user)


@router.delete("/scheduler/{schedule_id}")
async def delete_scheduler_job(
    schedule_id: str,
    request: Request,
    user: User = Depends(require_permission("admin:read")),
):
    try:
        deleted = await delete_schedule(schedule_id)
    except Exception as exc:
        logger.error(f"删除 Scheduler 任务失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await record_policy_event(
        user,
        PolicyAuditEvent(
            action="scheduler.delete",
            resource_type="schedule",
            resource_id=schedule_id,
        ),
        request,
    )
    return {"id": schedule_id, "deleted": True}


@router.post("/scheduler/{schedule_id}/trigger")
async def trigger_scheduler_job(
    schedule_id: str,
    request: Request,
    user: User = Depends(require_permission("admin:read")),
):
    schedule = await get_schedule(schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if not schedule["enabled"]:
        raise HTTPException(status_code=409, detail="Schedule is disabled")
    executor = getattr(request.app.state, "scheduler_executor", None)
    if executor is None:
        raise HTTPException(status_code=503, detail="Scheduler is not running")
    try:
        run = await executor.execute(schedule, get_async_agno_postgres_db(), release_schedule=False)
    except Exception as exc:
        logger.error(f"触发 Scheduler 任务失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    await record_policy_event(
        user,
        PolicyAuditEvent(
            action="scheduler.trigger",
            resource_type="schedule",
            resource_id=schedule_id,
            metadata={"run_id": run.get("id")},
        ),
        request,
    )
    return schedule_run_to_dict(run)


@router.get("/scheduler/{schedule_id}/runs")
async def get_scheduler_runs(
    schedule_id: str,
    limit: int = 20,
    page: int = 1,
    user: User = Depends(require_permission("admin:read")),
):
    if await get_schedule(schedule_id) is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {
        "items": await list_schedule_runs(schedule_id, limit=limit, page=page),
        "page": page,
        "limit": limit,
    }
