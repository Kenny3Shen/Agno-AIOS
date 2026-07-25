from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Request, Response
import jwt
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, exceptions
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users.jwt import decode_jwt, generate_jwt
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from loguru import logger

from api.auth.claims import scope_claims
from api.auth.database import get_user_db
from api.auth.models import User
from api.auth.token_version import (
    AUTH_VERSION_CLAIM,
    authorization_version,
    next_authorization_version,
    token_authorization_version,
)
from api.config import get_settings
from api.services.audit_service import audit_request_context, record_audit_event_async

settings = get_settings()


class UserManager(UUIDIDMixin, BaseUserManager[User, UUID]):
    reset_password_token_secret = settings.auth_reset_password_secret
    verification_token_secret = settings.auth_verification_secret

    async def validate_password(self, password: str, user: User | None = None) -> None:
        if len(password) < 8:
            raise exceptions.InvalidPasswordException("密码长度至少需要 8 位。")

    async def update(
        self,
        user_update,
        user: User,
        safe: bool = False,
        request: Request | None = None,
    ) -> User:
        """Update profile data and revoke tokens after a password change.

        Product-role and superuser changes deliberately do not flow through the
        generic FastAPI Users endpoint.  They use the audited admin lifecycle
        endpoint instead.
        """
        update_dict = (
            user_update.create_update_dict()
            if safe
            else user_update.create_update_dict_superuser()
        )
        forbidden = {"role", "is_superuser", "is_active", "auth_version"}
        if forbidden.intersection(update_dict):
            raise ValueError("Access state must be changed through the admin role endpoint.")
        if update_dict.get("password") is not None:
            update_dict["auth_version"] = next_authorization_version(
                getattr(user, "auth_version", 1)
            )
        updated = await self._update(user, update_dict)
        await self.on_after_update(updated, update_dict, request)
        return updated

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
    async def read_token(
        self,
        token: str | None,
        user_manager: BaseUserManager[User, UUID],
    ) -> User | None:
        if token is None:
            return None

        try:
            data = decode_jwt(
                token,
                self.decode_key,
                self.token_audience,
                algorithms=[self.algorithm],
            )
            user_id = data.get("sub")
            token_version = token_authorization_version(data.get(AUTH_VERSION_CLAIM))
            if user_id is None or token_version is None:
                return None
        except jwt.PyJWTError:
            return None

        try:
            user = await user_manager.get(user_manager.parse_id(user_id))
        except (exceptions.UserNotExists, exceptions.InvalidID):
            return None
        if authorization_version(getattr(user, "auth_version", 1)) != token_version:
            return None
        return user

    async def write_token(self, user: User) -> str:
        claims = scope_claims(user)
        data = {
            "sub": str(user.id),
            "aud": self.token_audience,
            "role": claims.role,
            "scopes": claims.scopes,
            AUTH_VERSION_CLAIM: authorization_version(getattr(user, "auth_version", 1)),
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
