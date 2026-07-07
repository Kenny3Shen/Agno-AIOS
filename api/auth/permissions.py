from __future__ import annotations

from collections.abc import Callable
from fastapi import Depends, HTTPException, status

from api.auth.claims import has_permission
from api.auth.models import User
from api.auth.users import current_active_user

__all__ = ["require_permission"]


def require_permission(permission: str) -> Callable[..., User]:
    def dependency(user: User = Depends(current_active_user)) -> User:
        if not has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足",
            )
        return user

    return dependency
