from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from api.auth.models import User
from api.auth.scopes import require_scope
from api.services.audit_service import list_audit_events_async
from api.utils.pagination import pagination_meta

router = APIRouter(prefix="/api/audit", tags=["Audit"])


@router.get("/logs")
async def list_audit_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    actor_user_id: str | None = None,
    actor_email: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    status: str | None = None,
    ip_address: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    user: User = Depends(require_scope("audit:read")),
) -> dict[str, Any]:
    """List audit events with Agno-style ``data`` / ``meta`` pagination."""
    try:
        items, total = await list_audit_events_async(
            page=page,
            limit=limit,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            ip_address=ip_address,
            created_from=created_from,
            created_to=created_to,
        )
        return {
            "data": items,
            "meta": pagination_meta(page=page, limit=limit, total_count=total),
        }
    except Exception as exc:
        logger.error("获取审计日志失败: {}", exc)
        raise HTTPException(status_code=500, detail="获取审计日志失败") from exc
