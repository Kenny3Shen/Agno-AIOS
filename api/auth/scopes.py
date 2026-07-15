from __future__ import annotations

from collections.abc import Callable
from fastapi import Depends, HTTPException, status

from api.auth.claims import has_scope
from api.auth.models import User
from api.auth.users import current_active_user

__all__ = ["require_scope", "require_any_scope"]


def require_scope(scope: str) -> Callable[..., User]:
    def dependency(user: User = Depends(current_active_user)) -> User:
        if not has_scope(user, scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足",
            )
        return user

    return dependency


def require_any_scope(*scopes: str) -> Callable[..., User]:
    """Accept if the actor has any of the listed scopes (admin still wins via has_scope)."""

    clean = [s for s in scopes if s]
    if not clean:
        raise ValueError("require_any_scope needs at least one scope")

    def dependency(user: User = Depends(current_active_user)) -> User:
        if any(has_scope(user, scope) for scope in clean):
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足",
        )

    return dependency
