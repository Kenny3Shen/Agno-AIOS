from __future__ import annotations

from fastapi import APIRouter
from httpx_oauth.clients.github import GitHubOAuth2
from httpx_oauth.clients.google import GoogleOAuth2
from httpx_oauth.clients.microsoft import MicrosoftGraphOAuth2

from api.auth.schemas import UserCreate, UserRead, UserUpdate
from api.auth.users import auth_backend, fastapi_users
from api.config import get_settings

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
async def list_oauth_providers() -> dict[str, list[str]]:
    return {"providers": enabled_oauth_providers}
