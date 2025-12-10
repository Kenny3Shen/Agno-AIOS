import os
import aiomysql
from loguru import logger

# Database Configuration
DB_CONFIG = {
    "host": os.getenv("MYSQL_TEST_HOST", "localhost"),
    "user": os.getenv("MYSQL_TEST_USER", "root"),
    "password": os.getenv("MYSQL_TEST_PASSWORD", ""),
    "db": os.getenv("MYSQL_TEST_DATABASE", "cve_db"),
    "port": 3306,
    "charset": "utf8mb4",
    "autocommit": True,
}

pool: aiomysql.Pool | None = None


async def init_pool():
    global pool
    try:
        pool = await aiomysql.create_pool(**DB_CONFIG)
        logger.info("Database connection pool created")
    except Exception as e:
        logger.error(f"Failed to create database pool: {e}")
        raise


async def get_pool():
    global pool
    if pool is None:
        await init_pool()
    return pool


async def close_pool():
    global pool
    if pool:
        pool.close()
        await pool.wait_closed()
        logger.info("Database connection pool closed")


async def search_cves_by_id_paginated(
    cve_id_query: str, page: int = 1, size: int = 10
) -> tuple[list[dict], int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # Get total count
            count_sql = "SELECT COUNT(*) as count FROM cves WHERE cve_id LIKE %s"
            await cursor.execute(count_sql, (f"%{cve_id_query}%",))
            count_result = await cursor.fetchone()
            total = count_result["count"] if count_result else 0

            # Get paginated results
            offset = (page - 1) * size
            sql = "SELECT id, cve_id, github_url, description, create_time FROM cves WHERE cve_id LIKE %s ORDER BY id DESC LIMIT %s OFFSET %s"
            await cursor.execute(sql, (f"%{cve_id_query}%", size, offset))
            result = await cursor.fetchall()
            return result, total

async def search_cves_by_description_paginated(
    keyword_query: str, page: int = 1, size: int = 10
) -> tuple[list[dict], int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # Get total count
            count_sql = "SELECT COUNT(*) as count FROM cves WHERE description LIKE %s"
            await cursor.execute(count_sql, (f"%{keyword_query}%",))
            count_result = await cursor.fetchone()
            total = count_result["count"] if count_result else 0

            # Get paginated results
            offset = (page - 1) * size
            sql = "SELECT id, cve_id, github_url, description, create_time FROM cves WHERE description LIKE %s ORDER BY id DESC LIMIT %s OFFSET %s"
            await cursor.execute(sql, (f"%{keyword_query}%", size, offset))
            result = await cursor.fetchall()
            return result, total