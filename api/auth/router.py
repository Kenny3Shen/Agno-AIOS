from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from httpx_oauth.clients.github import GitHubOAuth2
from httpx_oauth.clients.google import GoogleOAuth2
from httpx_oauth.clients.microsoft import MicrosoftGraphOAuth2
from pydantic import BaseModel
from sqlalchemy import func, select

from api.auth.claims import ADMIN_SCOPE, ROLE_SCOPES, Role, normalize_role
from api.auth.database import async_session_maker
from api.auth.models import User
from api.auth.models import User as AuthUser
from api.auth.schemas import UserCreate, UserRead, UserUpdate
from api.auth.scopes import require_scope
from api.auth.users import auth_backend, current_active_user, fastapi_users
from api.config import get_settings
from api.services.audit_service import audit_request_context, record_audit_event_async
from api.utils.pagination import pagination_meta

router = APIRouter(prefix="/api/auth", tags=["Auth"])
settings = get_settings()

router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/jwt",
)
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
)
router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
)


def _include_oauth_router(
    *,
    provider: str,
    oauth_client,
    redirect_url: str | None,
) -> None:
    router.include_router(
        fastapi_users.get_oauth_router(
            oauth_client,
            auth_backend,
            settings.auth_oauth_state_secret,
            redirect_url=redirect_url,
            associate_by_email=settings.oauth_associate_by_email,
            is_verified_by_default=settings.oauth_is_verified_by_default,
            csrf_token_cookie_secure=settings.auth_cookie_secure,
        ),
        prefix=f"/{provider}",
    )


enabled_oauth_providers: list[str] = []

if settings.github_oauth_client_id and settings.github_oauth_client_secret.get_secret_value():
    _include_oauth_router(
        provider="github",
        oauth_client=GitHubOAuth2(
            settings.github_oauth_client_id,
            settings.github_oauth_client_secret.get_secret_value(),
        ),
        redirect_url=settings.github_oauth_redirect_url,
    )
    enabled_oauth_providers.append("github")

if settings.google_oauth_client_id and settings.google_oauth_client_secret.get_secret_value():
    _include_oauth_router(
        provider="google",
        oauth_client=GoogleOAuth2(
            settings.google_oauth_client_id,
            settings.google_oauth_client_secret.get_secret_value(),
        ),
        redirect_url=settings.google_oauth_redirect_url,
    )
    enabled_oauth_providers.append("google")

if (
    settings.microsoft_oauth_client_id
    and settings.microsoft_oauth_client_secret.get_secret_value()
):
    _include_oauth_router(
        provider="microsoft",
        oauth_client=MicrosoftGraphOAuth2(
            settings.microsoft_oauth_client_id,
            settings.microsoft_oauth_client_secret.get_secret_value(),
            tenant=settings.microsoft_oauth_tenant,
        ),
        redirect_url=settings.microsoft_oauth_redirect_url,
    )
    enabled_oauth_providers.append("microsoft")


@router.get("/oauth/providers")
def list_oauth_providers() -> dict[str, list[str]]:
    return {"providers": enabled_oauth_providers}


@router.post("/logout")
async def audited_logout(
    request: Request,
    user: User = Depends(current_active_user),
) -> dict[str, bool]:
    await record_audit_event_async(
        user,
        action="auth.logout",
        resource_type="auth",
        **audit_request_context(request),
    )
    return {"success": True}


class AdminRoleUpdate(BaseModel):
    role: Role


@router.get("/admin/users", name="users:list")
async def list_users_for_admin(
    page: int = 1,
    limit: int = 50,
    _admin: User = Depends(require_scope(ADMIN_SCOPE)),
):
    """List auth users for role assignment (admin only)."""
    page = max(1, page)
    limit = max(1, min(limit, 100))
    async with async_session_maker() as session:
        total_count = int(
            (await session.execute(select(func.count()).select_from(AuthUser))).scalar_one()
        )
        stmt = (
            select(AuthUser)
            .order_by(AuthUser.email)
            .offset((page - 1) * limit)
            .limit(limit)
        )
        rows = (await session.execute(stmt)).scalars().unique().all()
        data = [UserRead.model_validate(row) for row in rows]
    return {
        "data": data,
        "meta": pagination_meta(page=page, limit=limit, total_count=total_count),
    }


@router.patch("/admin/users/{user_id}/role", name="users:set_role")
async def set_user_role(
    user_id: UUID,
    body: AdminRoleUpdate,
    request: Request,
    admin: User = Depends(require_scope(ADMIN_SCOPE)),
):
    """Assign a product role preset to a user (admin only)."""
    async with async_session_maker() as session:
        row = await session.get(AuthUser, user_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        if row.is_superuser and body.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote a superuser via role preset; clear superuser first.",
            )
        previous = normalize_role(row.role)
        row.role = body.role
        if body.role == "admin":
            row.is_superuser = True
        session.add(row)
        await session.commit()
        await session.refresh(row)
        await record_audit_event_async(
            admin,
            action="auth.role_update",
            resource_type="user",
            resource_id=str(user_id),
            metadata={"from": previous, "to": body.role, "email": row.email},
            **audit_request_context(request),
        )
        return UserRead.model_validate(row)


@router.get("/roles", name="users:role_presets")
async def list_role_presets(_admin: User = Depends(require_scope(ADMIN_SCOPE))):
    """Role preset catalog with scopes for admin UI."""
    order: list[Role] = ["admin", "user"]
    return {
        "data": [{"role": role, "scopes": sorted(ROLE_SCOPES[role])} for role in order]
    }
