from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from api.auth.models import User
from api.auth.scopes import require_scope
from api.services.os_knowledge_control import get_knowledge_payload

router = APIRouter(prefix="/api/os", tags=["AgentOS Knowledge Control"])


@router.get("/knowledge")
async def get_os_knowledge(
    user: User = Depends(require_scope("knowledge:read")),
):
    try:
        return await get_knowledge_payload(actor=user)
    except Exception as exc:
        logger.error(f"获取 Agno 知识库控制面失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to load knowledge") from exc
