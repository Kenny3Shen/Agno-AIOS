from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from api.auth.models import User
from api.auth.scopes import require_scope
from api.services.os_evaluation_control import get_evaluation_payload

router = APIRouter(prefix="/api/os", tags=["AgentOS Evaluation Control"])


@router.get("/evaluation")
async def get_os_evaluation(
    user: User = Depends(require_scope("evals:read")),
):
    try:
        return await get_evaluation_payload(actor=user)
    except Exception as exc:
        logger.error(f"获取 Agno 评测控制面失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to load evaluation") from exc
