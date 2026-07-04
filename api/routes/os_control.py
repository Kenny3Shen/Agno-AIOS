from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from pydantic import BaseModel, Field

from api.auth.models import User
from api.auth.permissions import actor_id, has_permission
from api.auth.users import current_active_user
from api.services.os_control_service import create_schedule_job, get_control_payload

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
    target_kind: str = Field("workflow", pattern="^(workflow|agent_skill)$")
    target_id: str = Field(..., min_length=1)
    schedule_type: str = Field("interval", pattern="^(cron|interval|once)$")
    cron: str = ""
    interval_seconds: int | None = Field(default=3600, ge=60)
    run_at: str | None = None
    max_runs: int | None = Field(default=None, ge=1)
    enabled: bool = True
    skill_name: str = ""
    agent_id: str = ""
    input: dict[str, object] = Field(default_factory=dict)


class ScheduleCreateResponse(BaseModel):
    id: str
    status: str
    enabled: bool
    celery_task_id: str | None = None


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
    body: ScheduleCreateRequest,
    user: User = Depends(require_scheduler_write_permission),
):
    try:
        row = create_schedule_job(
            name=body.name,
            target_kind=body.target_kind,
            target_id=body.target_id,
            schedule_type=body.schedule_type,
            cron=body.cron,
            interval_seconds=body.interval_seconds,
            run_at=body.run_at,
            max_runs=body.max_runs,
            enabled=body.enabled,
            skill_name=body.skill_name,
            agent_id=body.agent_id,
            input_payload=body.input,
            created_by=actor_id(user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"创建 Scheduler 任务失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    celery_task_id = None
    if body.enabled:
        try:
            from api.tasks.scheduler import run_scheduled_job

            task = run_scheduled_job.apply_async(args=[str(row.get("id"))])
            celery_task_id = task.id
        except Exception as exc:
            logger.warning(f"Scheduler Celery dispatch skipped: {exc}")

    return ScheduleCreateResponse(
        id=str(row.get("id")),
        status="enabled" if row.get("enabled") else "disabled",
        enabled=bool(row.get("enabled")),
        celery_task_id=celery_task_id,
    )
