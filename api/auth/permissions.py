from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, status

from api.auth.actors import Role, actor_id, actor_role
from api.auth.models import User
from api.auth.users import current_active_user

ROLE_PERMISSIONS: dict[Role, set[str]] = {
    "admin": {"*"},
    "user": {
        "session:read:own",
        "session:write:own",
        "trace:read:own",
        "memory:read:own",
        "memory:write:own",
        "metrics:read:own",
        "collect:write",
        "cve:read",
        "knowledge:read",
        "knowledge:write",
        "mcp:read",
        "skill:read",
        "settings:read",
        "agent_eval:read",
    },
    "guest": {
        "session:read:own",
        "trace:read:own",
        "memory:read:own",
        "metrics:read:own",
        "cve:read",
        "knowledge:read",
    },
}


@dataclass(frozen=True)
class PermissionClaims:
    role: Role
    permissions: list[str]

def has_permission(user: User | Any, permission: str) -> bool:
    permissions = ROLE_PERMISSIONS[actor_role(user)]
    return "*" in permissions or permission in permissions


def permission_claims(user: User | Any) -> PermissionClaims:
    role = actor_role(user)
    permissions = ROLE_PERMISSIONS[role]
    return PermissionClaims(
        role=role,
        permissions=["*"] if "*" in permissions else sorted(permissions),
    )


def scope_user_id(
    actor: User | Any | None,
    requested_user_id: str | None,
    any_permission: str,
) -> str | None:
    requested = (requested_user_id or "").strip() or None
    if actor is not None and has_permission(actor, any_permission):
        return requested
    return actor_id(actor) if actor is not None else ""


def require_permission(permission: str) -> Callable[..., User]:
    def dependency(user: User = Depends(current_active_user)) -> User:
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
