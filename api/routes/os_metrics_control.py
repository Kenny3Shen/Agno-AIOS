from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from api.auth.models import User
from api.auth.scopes import require_scope
from api.services.os_metrics_control import get_metrics_payload

router = APIRouter(prefix="/api/os", tags=["AgentOS Metrics Control"])


@router.get("/metrics")
async def get_os_metrics(
    user: User = Depends(require_scope("metrics:read")),
):
    try:
        return await get_metrics_payload(actor=user)
    except Exception as exc:
        logger.error(f"获取 Agno 指标控制面失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to load metrics") from exc
