from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from api.auth.models import User
from api.auth.permissions import require_permission, scope_user_id
from api.services.tracing_service import list_traces, get_trace_detail


router = APIRouter(prefix="/api", tags=["Tracing"])


def effective_trace_user_filter(actor: Any, requested_user_id: str | None) -> str | None:
    return scope_user_id(actor, requested_user_id, "trace:read:any")


@router.get("/traces")
async def api_list_traces(
    run_id: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    agent_id: str | None = None,
    team_id: str | None = None,
    workflow_id: str | None = None,
    status: str | None = Query(default=None, description="OK / ERROR / UNSET"),
    start_time: str | None = Query(
        default=None, description="ISO8601, e.g. 2026-02-12T00:00:00+08:00"
    ),
    end_time: str | None = Query(
        default=None, description="ISO8601, e.g. 2026-02-12T23:59:59+08:00"
    ),
    limit: int = Query(default=20, ge=1, le=200),
    page: int = Query(default=1, ge=1),
    user: User = Depends(require_permission("trace:read:own")),
):
    """List traces from the tracing database."""
    try:
        effective_user_id = effective_trace_user_filter(user, user_id)
        return await list_traces(
            run_id=run_id,
            session_id=session_id,
            user_id=effective_user_id,
            agent_id=agent_id,
            team_id=team_id,
            workflow_id=workflow_id,
            status=status,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            page=page,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取 traces 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/traces/{trace_id}")
async def api_get_trace(
    trace_id: str,
    user: User = Depends(require_permission("trace:read:own")),
):
    """Get trace detail including spans and a span tree."""
    try:
        data = await get_trace_detail(trace_id, actor=user)
        if not data:
            raise HTTPException(status_code=404, detail="Trace 不存在")
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 trace 详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
