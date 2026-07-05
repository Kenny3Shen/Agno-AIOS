from typing import Any

from psycopg_pool import AsyncConnectionPool

from api.services.postgres_store import (
    close_postgres_pool,
    ensure_app_tables_async,
    get_postgres_pool,
)


async def get_db_pool() -> AsyncConnectionPool[Any]:
    await ensure_app_tables_async()
    return await get_postgres_pool()


async def close_db_pool() -> None:
    await close_postgres_pool()
