from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Request, Response
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, exceptions
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users.jwt import generate_jwt
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from loguru import logger

from api.auth.claims import permission_claims
from api.auth.database import get_user_db
from api.auth.models import User
from api.config import get_settings
from api.services.audit_service import audit_request_context, record_audit_event_async

settings = get_settings()


class UserManager(UUIDIDMixin, BaseUserManager[User, UUID]):
    reset_password_token_secret = settings.auth_reset_password_secret
    verification_token_secret = settings.auth_verification_secret

    async def validate_password(self, password: str, user: User | None = None) -> None:
        if len(password) < 8:
            raise exceptions.InvalidPasswordException("密码长度至少需要 8 位。")

    async def on_after_register(self, user: User, request: Request | None = None) -> None:
        logger.info("用户注册完成: {}", user.email)

    async def on_after_login(
        self,
        user: User,
        request: Request | None = None,
        response: Response | None = None,
    ) -> None:
        logger.info("用户登录成功: {}", user.email)
        await record_audit_event_async(
            user,
            action="auth.login",
            resource_type="auth",
            **audit_request_context(request),
        )


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase[User, UUID] = Depends(get_user_db),
):
    yield UserManager(user_db)


bearer_transport = BearerTransport(tokenUrl="/api/auth/jwt/login")


class ScopedJWTStrategy(JWTStrategy[User, UUID]):
    async def write_token(self, user: User) -> str:
        claims = permission_claims(user)
        data = {
            "sub": str(user.id),
            "aud": self.token_audience,
            "role": claims.role,
            "scopes": claims.scopes,
        }
        return generate_jwt(
            data,
            self.encode_key,
            self.lifetime_seconds,
            algorithm=self.algorithm,
        )


def get_jwt_strategy() -> ScopedJWTStrategy:
    return ScopedJWTStrategy(
        secret=settings.auth_jwt_secret,
        lifetime_seconds=settings.auth_token_lifetime_seconds,
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, UUID](get_user_manager, [auth_backend])
current_active_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
