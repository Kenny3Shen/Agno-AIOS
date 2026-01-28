import os
import aiomysql
from dotenv import load_dotenv

load_dotenv(override=True)

DB_CONFIG = {
    "host": os.getenv("MYSQL_TEST_HOST"),
    "port": int(os.getenv("MYSQL_TEST_PORT", 3306)),
    "user": os.getenv("MYSQL_TEST_USER"),
    "password": os.getenv("MYSQL_TEST_PASSWORD"),
    "db": os.getenv("MYSQL_TEST_DATABASE"),
    "charset": "utf8mb4",
    "autocommit": True,
}

_pool: aiomysql.Pool | None = None


async def get_db_pool() -> aiomysql.Pool:
    global _pool
    if _pool is None:
        _pool = await aiomysql.create_pool(**DB_CONFIG)
    return _pool


async def close_db_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None
