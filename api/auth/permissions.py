from __future__ import annotations

from collections.abc import Callable
from fastapi import Depends, HTTPException, status

from api.auth.claims import (
    ROLE_PERMISSIONS,
    PermissionClaims,
    Role,
    actor_id,
    actor_role,
    has_permission,
    permission_claims,
    scope_user_id,
)
from api.auth.models import User
from api.auth.ownership import assert_owned_resource
from api.auth.users import current_active_user

__all__ = [
    "ROLE_PERMISSIONS",
    "PermissionClaims",
    "Role",
    "actor_id",
    "actor_role",
    "assert_owned_resource",
    "has_permission",
    "permission_claims",
    "require_permission",
    "scope_user_id",
]


def require_permission(permission: str) -> Callable[..., User]:
    def dependency(user: User = Depends(current_active_user)) -> User:
        if not has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足",
            )
        return user

    return dependency
