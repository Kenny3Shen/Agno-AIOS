import os
import aiomysql
from loguru import logger

DB_CONFIG = {
    "host": os.getenv("MYSQL_TEST_HOST", "localhost"),
    "user": os.getenv("MYSQL_TEST_USER", "root"),
    "password": os.getenv("MYSQL_TEST_PASSWORD", ""),
    "db": os.getenv("MYSQL_TEST_DATABASE", "cve_db"),
    "port": int(os.getenv("MYSQL_TEST_PORT", 3306)),
    "charset": "utf8mb4",
    "autocommit": True,
}

pool: aiomysql.Pool | None = None


async def init_pool():
    global pool
    try:
        pool = await aiomysql.create_pool(**DB_CONFIG)
        logger.info("数据库连接池已创建")
    except Exception as e:
        logger.error(f"创建数据库连接池失败: {e}")
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
        logger.info("数据库连接池已关闭")


async def search_cves_by_id(
    cve_id_query: str, page: int = 1, size: int = 10, source: str | None = None
) -> tuple[list[dict], int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # 构建查询条件
            count_sql = "SELECT COUNT(*) as count FROM cves WHERE cve_id LIKE %s"
            sql = "SELECT * FROM cves WHERE cve_id LIKE %s"
            params = [f"%{cve_id_query}%"]
            
            if source is not None:
                count_sql += " AND source = %s"
                sql += " AND source = %s"
                params.append(source)
            
            sql += " ORDER BY id DESC LIMIT %s OFFSET %s"
            params.extend([size, (page - 1) * size])
            
            await cursor.execute(count_sql, params[:-2])  # count 不需要 LIMIT 参数
            count_result = await cursor.fetchone()
            total = count_result["count"] if count_result else 0

            await cursor.execute(sql, params)
            result = await cursor.fetchall()
            return result, total


async def search_cves_by_description(
    keyword_query: str, page: int = 1, size: int = 10, source: str | None = None
) -> tuple[list[dict], int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # 构建查询条件
            count_sql = "SELECT COUNT(*) as count FROM cves WHERE description LIKE %s"
            sql = "SELECT * FROM cves WHERE description LIKE %s"
            params = [f"%{keyword_query}%"]
            
            if source is not None:
                count_sql += " AND source = %s"
                sql += " AND source = %s"
                params.append(source)
            
            sql += " ORDER BY id DESC LIMIT %s OFFSET %s"
            params.extend([size, (page - 1) * size])
            
            await cursor.execute(count_sql, params[:-2])  # count 不需要 LIMIT 参数
            count_result = await cursor.fetchone()
            total = count_result["count"] if count_result else 0

            await cursor.execute(sql, params)
            result = await cursor.fetchall()
            return result, total
