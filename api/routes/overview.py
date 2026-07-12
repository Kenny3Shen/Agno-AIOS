from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from api.auth.models import User
from api.auth.scopes import require_scope
from api.services.overview_service import get_runtime_overview

router = APIRouter(prefix="/api", tags=["Overview"])


@router.get("/overview")
async def get_overview(
    range_name: Literal["1h", "24h", "7d", "custom"] = Query(default="24h", alias="range"),
    start_time: str | None = Query(
        default=None, description="Custom range start in ISO8601 format with timezone"
    ),
    end_time: str | None = Query(
        default=None, description="Custom range end in ISO8601 format with timezone"
    ),
    timezone: str = Query(default="UTC", min_length=1, max_length=64),
    user: User = Depends(require_scope("traces:read")),
):
    try:
        return await get_runtime_overview(
            user,
            range_name=range_name,
            start_time=start_time,
            end_time=end_time,
            timezone=timezone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("获取运行概览失败: {}", exc)
        raise HTTPException(status_code=500, detail="获取运行概览失败") from exc
