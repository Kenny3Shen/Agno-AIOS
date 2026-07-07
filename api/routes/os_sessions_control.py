from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from api.auth.models import User
from api.auth.scopes import require_scope
from api.services.os_sessions_control import get_sessions_payload

router = APIRouter(prefix="/api/os", tags=["AgentOS Sessions Control"])


@router.get("/sessions")
async def get_os_sessions(
    user: User = Depends(require_scope("sessions:read")),
):
    try:
        return await get_sessions_payload(actor=user)
    except Exception as exc:
        logger.error(f"获取 Agno 会话控制面失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to load sessions") from exc
