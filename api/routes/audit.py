from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from api.auth.models import User
from api.auth.scopes import require_scope
from api.services.audit_service import list_audit_events_async

router = APIRouter(prefix="/api/audit", tags=["Audit"])


@router.get("/logs")
async def list_audit_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    actor_user_id: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    status: str | None = None,
    user: User = Depends(require_scope("audit:read")),
) -> dict[str, Any]:
    try:
        items, total = await list_audit_events_async(
            page=page,
            limit=limit,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            status=status,
        )
        return {"items": items, "total": total, "page": page, "limit": limit}
    except Exception as exc:
        logger.error("获取审计日志失败: {}", exc)
        raise HTTPException(status_code=500, detail="获取审计日志失败") from exc
