from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import Depends
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.auth.models import AuthBase, OAuthAccount, User
from api.config import get_settings

settings = get_settings()
auth_engine = create_async_engine(settings.postgres_sqlalchemy_url, pool_pre_ping=True)
async_session_maker = async_sessionmaker(auth_engine, expire_on_commit=False)


async def create_auth_tables() -> None:
    async with auth_engine.begin() as conn:
        await conn.run_sync(AuthBase.metadata.create_all)


async def close_auth_engine() -> None:
    await auth_engine.dispose()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def get_user_db(
    session: AsyncSession = Depends(get_async_session),
) -> AsyncGenerator[SQLAlchemyUserDatabase[User, UUID], None]:
    yield SQLAlchemyUserDatabase(session, User, OAuthAccount)
