from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger

from api.auth.models import User
from api.auth.permissions import has_permission
from api.auth.users import current_active_user
from api.services.os_control_service import get_control_payload

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
