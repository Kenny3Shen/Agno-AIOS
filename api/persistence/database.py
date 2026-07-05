from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from api.config import get_settings


def _async_sqlalchemy_url() -> str:
    return get_settings().postgres_async_sqlalchemy_url


@lru_cache(maxsize=1)
def get_async_control_plane_engine() -> AsyncEngine:
    return create_async_engine(_async_sqlalchemy_url(), pool_pre_ping=True)


async def dispose_async_control_plane_engine() -> None:
    await get_async_control_plane_engine().dispose()
    get_async_control_plane_engine.cache_clear()
