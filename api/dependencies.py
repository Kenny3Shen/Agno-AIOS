import asyncio
from typing import Any

import httpx
from fastapi import HTTPException, Request
from psycopg_pool import AsyncConnectionPool


def get_pool(request: Request) -> AsyncConnectionPool[Any]:
    """Return the PostgreSQL pool stored on app.state.

    This is placed in a separate module to avoid circular imports between
    `api.main` and route modules that depend on it.
    """
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(503, "数据库连接未初始化，请稍后重试。")
    return pool


def get_asset_client(request: Request) -> httpx.AsyncClient:
    """Return the httpx AsyncClient for asset API stored on app.state.

    This is placed in a separate module to avoid circular imports between
    `api.main` and route modules that depend on it.
    """
    client = getattr(request.app.state, "asset_client", None)
    if client is None:
        raise HTTPException(503, "资产客户端未初始化，请稍后重试。")
    return client


def get_asset_lock(request: Request) -> asyncio.Lock:
    """Return the asyncio.Lock used to serialize token refresh for the asset client."""
    lock = getattr(request.app.state, "asset_lock", None)
    if lock is None:
        raise HTTPException(503, "资产锁未初始化，请稍后重试。")
    return lock
