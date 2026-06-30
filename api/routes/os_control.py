from fastapi import APIRouter, HTTPException
from loguru import logger

from api.services.os_control_service import get_control_payload

router = APIRouter(prefix="/api/os", tags=["AgentOS Control Plane"])


@router.get("/{module}")
async def get_os_control_module(module: str):
    try:
        return get_control_payload(module)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"获取 AgentOS 控制面模块失败: {module}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
