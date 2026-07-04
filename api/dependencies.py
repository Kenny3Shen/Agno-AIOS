from typing import Any

from fastapi import HTTPException, Request
from psycopg_pool import AsyncConnectionPool

from api.config import Settings, get_settings


def get_app_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        return get_settings()
    if not isinstance(settings, Settings):
        raise HTTPException(503, "应用配置未正确初始化。")
    return settings


def get_pool(request: Request) -> AsyncConnectionPool[Any]:
    """Return the PostgreSQL pool stored on app.state.

    This is placed in a separate module to avoid circular imports between
    `api.main` and route modules that depend on it.
    """
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(503, "数据库连接未初始化，请稍后重试。")
    return pool
