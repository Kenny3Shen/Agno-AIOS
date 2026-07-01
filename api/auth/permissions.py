from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from fastapi import Depends, HTTPException, status

from api.auth.models import User
from api.auth.users import current_active_user

Role = Literal["admin", "user", "guest"]

ROLE_PERMISSIONS: dict[Role, set[str]] = {
    "admin": {"*"},
    "user": {
        "session:read:own",
        "session:write:own",
        "trace:read:own",
        "knowledge:read",
        "mcp:read",
        "skill:read",
        "settings:read",
    },
    "guest": {
        "session:read:own",
        "trace:read:own",
        "knowledge:read",
    },
}


def actor_id(user: User | Any) -> str:
    return str(getattr(user, "id", "") or "")


def actor_role(user: User | Any) -> Role:
    if bool(getattr(user, "is_superuser", False)):
        return "admin"
    role = str(getattr(user, "role", "user") or "user").lower()
    if role == "admin":
        return "admin"
    if role == "guest":
        return "guest"
    return "user"


def has_permission(user: User | Any, permission: str) -> bool:
    permissions = ROLE_PERMISSIONS[actor_role(user)]
    return "*" in permissions or permission in permissions


def require_permission(permission: str) -> Callable[..., Awaitable[User]]:
    async def dependency(user: User = Depends(current_active_user)) -> User:
        if not has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足",
            )
        return user

    return dependency


def assert_owned_resource(
    actor: User | Any,
    *,
    owner_user_id: str | None,
    resource_name: str,
) -> None:
    if actor_role(actor) == "admin":
        return
    if owner_user_id and str(owner_user_id) == actor_id(actor):
        return
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource_name} 不存在",
    )
