from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from pydantic import BaseModel, Field

from api.auth.models import User
from api.auth.permissions import has_permission
from api.auth.users import current_active_user
from api.services.audit_service import audit_request_context, record_audit_event
from api.services.os_control_service import get_control_payload
from api.services.postgres_store import get_agno_postgres_db
from api.services.scheduler_service import (
    create_schedule,
    delete_schedule,
    get_schedule,
    list_schedule_runs,
    schedule_run_to_dict,
    set_schedule_enabled,
    update_schedule,
)

router = APIRouter(prefix="/api/os", tags=["AgentOS Control Plane"])

MODULE_PERMISSIONS = {
    "sessions": "session:read:own",
    "studio": "mcp:read",
    "memory": "memory:read:own",
    "metrics": "metrics:read:own",
    "evaluation": "admin:read",
    "approvals": "admin:read",
    "scheduler": "admin:read",
    "knowledge": "knowledge:read",
}


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


async def require_os_module_permission(
    module: str,
    user: User = Depends(current_active_user),
) -> User:
    try:
        permission = MODULE_PERMISSIONS[module]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unsupported control module: {module}") from exc

    if not has_permission(user, permission):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return user


async def require_scheduler_write_permission(
    user: User = Depends(current_active_user),
) -> User:
    if not has_permission(user, "admin:read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return user


@router.get("/{module}")
async def get_os_control_module(
    module: str,
    user: User = Depends(require_os_module_permission),
):
    try:
        return get_control_payload(module, actor=user)
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
    user: User = Depends(require_scheduler_write_permission),
):
    try:
        schedule = create_schedule(
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

    record_audit_event(
        user,
        action="scheduler.create",
        resource_type="schedule",
        resource_id=schedule["id"],
        metadata={"name": schedule["name"], "endpoint": schedule["endpoint"]},
        **audit_request_context(request),
    )
    return ScheduleCreateResponse(**schedule)


@router.patch("/scheduler/{schedule_id}")
async def update_scheduler_job(
    schedule_id: str,
    body: ScheduleUpdateRequest,
    request: Request,
    user: User = Depends(require_scheduler_write_permission),
):
    try:
        schedule = update_schedule(schedule_id, **body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"更新 Scheduler 任务失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    record_audit_event(
        user,
        action="scheduler.update",
        resource_type="schedule",
        resource_id=schedule_id,
        metadata={"updates": body.model_dump(exclude_unset=True)},
        **audit_request_context(request),
    )
    return schedule


async def _set_scheduler_job_enabled(
    schedule_id: str,
    enabled: bool,
    request: Request,
    user: User,
) -> dict[str, Any]:
    try:
        schedule = set_schedule_enabled(schedule_id, enabled)
    except Exception as exc:
        logger.error(f"切换 Scheduler 任务状态失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    record_audit_event(
        user,
        action="scheduler.enable" if enabled else "scheduler.disable",
        resource_type="schedule",
        resource_id=schedule_id,
        metadata={"enabled": enabled},
        **audit_request_context(request),
    )
    return schedule


@router.post("/scheduler/{schedule_id}/enable")
async def enable_scheduler_job(
    schedule_id: str,
    request: Request,
    user: User = Depends(require_scheduler_write_permission),
):
    return await _set_scheduler_job_enabled(schedule_id, True, request, user)


@router.post("/scheduler/{schedule_id}/disable")
async def disable_scheduler_job(
    schedule_id: str,
    request: Request,
    user: User = Depends(require_scheduler_write_permission),
):
    return await _set_scheduler_job_enabled(schedule_id, False, request, user)


@router.delete("/scheduler/{schedule_id}")
async def delete_scheduler_job(
    schedule_id: str,
    request: Request,
    user: User = Depends(require_scheduler_write_permission),
):
    try:
        deleted = delete_schedule(schedule_id)
    except Exception as exc:
        logger.error(f"删除 Scheduler 任务失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Schedule not found")
    record_audit_event(
        user,
        action="scheduler.delete",
        resource_type="schedule",
        resource_id=schedule_id,
        **audit_request_context(request),
    )
    return {"id": schedule_id, "deleted": True}


@router.post("/scheduler/{schedule_id}/trigger")
async def trigger_scheduler_job(
    schedule_id: str,
    request: Request,
    user: User = Depends(require_scheduler_write_permission),
):
    schedule = get_schedule(schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if not schedule["enabled"]:
        raise HTTPException(status_code=409, detail="Schedule is disabled")
    executor = getattr(request.app.state, "scheduler_executor", None)
    if executor is None:
        raise HTTPException(status_code=503, detail="Scheduler is not running")
    try:
        run = await executor.execute(schedule, get_agno_postgres_db(), release_schedule=False)
    except Exception as exc:
        logger.error(f"触发 Scheduler 任务失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    record_audit_event(
        user,
        action="scheduler.trigger",
        resource_type="schedule",
        resource_id=schedule_id,
        metadata={"run_id": run.get("id")},
        **audit_request_context(request),
    )
    return schedule_run_to_dict(run)


@router.get("/scheduler/{schedule_id}/runs")
async def get_scheduler_runs(
    schedule_id: str,
    limit: int = 20,
    page: int = 1,
    user: User = Depends(require_scheduler_write_permission),
):
    if get_schedule(schedule_id) is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {
        "items": list_schedule_runs(schedule_id, limit=limit, page=page),
        "page": page,
        "limit": limit,
    }
