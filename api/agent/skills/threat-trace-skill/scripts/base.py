#!/home/shenss/python/fastapi/.venv/bin/python3
"""检索威胁情报"""

import aiomysql
import os

db_config = {
    "host": os.getenv("MYSQL_HOST"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "db": os.getenv("MYSQL_DATABASE"),
    "charset": "utf8mb4",
    "autocommit": True,
}

pool: aiomysql.Pool | None = None


async def _get_pool() -> aiomysql.Pool:
    global pool
    if pool is None:
        pool = await aiomysql.create_pool(**db_config)
    return pool


async def _close_pool():
    global pool
    if pool:
        pool.close()
        await pool.wait_closed()
        pool = None
