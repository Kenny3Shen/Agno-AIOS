from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

from fastapi import Depends
from fastapi_users.password import PasswordHelper
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from loguru import logger

from api.auth.models import OAuthAccount, User
from api.config import Settings, get_settings

settings = get_settings()
auth_engine = create_async_engine(settings.postgres_async_sqlalchemy_url, pool_pre_ping=True)
async_session_maker = async_sessionmaker(auth_engine, expire_on_commit=False)


async def create_auth_tables() -> None:
    """Legacy compatibility check; schema creation belongs to Alembic.

    Keeping the function protects callers from silently reintroducing runtime
    DDL while deployments transition to the explicit migration command.
    """
    from api.persistence.migrations import ensure_control_plane_schema_current

    await ensure_control_plane_schema_current()


async def bootstrap_admin_user(app_settings: Settings | None = None) -> None:
    active_settings = app_settings or settings
    admin_email = active_settings.bootstrap_admin_email.strip().lower()
    admin_password = active_settings.bootstrap_admin_password.get_secret_value()

    if not admin_email and not admin_password:
        return
    if not admin_email or not admin_password:
        raise ValueError(
            "TAIS_BOOTSTRAP_ADMIN_EMAIL and TAIS_BOOTSTRAP_ADMIN_PASSWORD must be set together."
        )
    if len(admin_password) < 8:
        raise ValueError("TAIS_BOOTSTRAP_ADMIN_PASSWORD must contain at least 8 characters.")

    password_hash = PasswordHelper().hash(admin_password)
    async with auth_engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO "user" (
                    id,
                    email,
                    hashed_password,
                    is_active,
                    is_superuser,
                    is_verified,
                    role,
                    auth_version
                )
                VALUES (
                    :id,
                    :email,
                    :hashed_password,
                    true,
                    true,
                    true,
                    'admin',
                    1
                )
                ON CONFLICT (email) DO UPDATE
                SET hashed_password = EXCLUDED.hashed_password,
                    is_active = true,
                    is_superuser = true,
                    is_verified = true,
                    role = 'admin',
                    auth_version = CASE
                        WHEN "user".hashed_password IS DISTINCT FROM EXCLUDED.hashed_password
                            OR "user".role IS DISTINCT FROM 'admin'
                            OR "user".is_superuser IS DISTINCT FROM true
                            OR "user".is_active IS DISTINCT FROM true
                        THEN "user".auth_version + 1
                        ELSE "user".auth_version
                    END
                """
            ),
            {
                "id": uuid4(),
                "email": admin_email,
                "hashed_password": password_hash,
            },
        )
    logger.info("Bootstrap admin ensured: {}", admin_email)


async def close_auth_engine() -> None:
    await auth_engine.dispose()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase[User, UUID], None]:
    yield SQLAlchemyUserDatabase(session, User, OAuthAccount)


async def get_active_user_by_id(user_id: str) -> User | None:
    """Resolve a current account for MCP token verification."""
    try:
        parsed = UUID(user_id)
    except (TypeError, ValueError):
        return None
    async with async_session_maker() as session:
        user = await session.get(User, parsed)
        if user is None or not bool(user.is_active):
            return None
        return user
