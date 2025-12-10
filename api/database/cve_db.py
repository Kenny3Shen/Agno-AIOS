import os
import aiomysql
from datetime import datetime
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
            sql = "SELECT id, cve_id, github_url, create_time FROM cves WHERE cve_id LIKE %s ORDER BY id DESC LIMIT %s OFFSET %s"
            await cursor.execute(sql, (f"%{cve_id_query}%", size, offset))
            result = await cursor.fetchall()
            return result, total

async def update_cve_database(
    increment_data: list[dict[str, str]],
    deleted_data: list[dict[str, str]],
) -> tuple[int, int]:
    """
    异步更新 MySQL 数据库：
    - 插入新增数据（INSERT IGNORE）
    - 删除远程已移除的数据（DELETE）
    返回 (新增条数, 删除条数)
    """

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
                # 1. 创建表
                await cursor.execute("""
                CREATE TABLE IF NOT EXISTS cves (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    cve_id VARCHAR(255) NOT NULL,
                    description TEXT,
                    github_url VARCHAR(255),
                    create_time DATETIME,
                    UNIQUE KEY unique_cve_url (cve_id, github_url)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                """)

                new_count = 0
                del_count = 0

                # 开启事务
                await conn.begin()

                try:
                    # 2. 插入新增数据（批量执行）
                    insert_sql = """
                            INSERT IGNORE INTO cves (cve_id, description, github_url, create_time)
                            VALUES (%s, %s, %s, %s)
                            """
                    batch_size = 500
                    for i in range(0, len(increment_data), batch_size):
                        batch = increment_data[i : i + batch_size]
                        create_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        params = [
                            (
                                item.get("cve_id"),
                                item.get("description", ""),
                                item.get("github_url", ""),
                                create_time,
                            )
                            for item in batch
                        ]
                        if params:
                            await cursor.executemany(insert_sql, params)
                            # cursor.rowcount should report number of inserted rows for the batch
                            inserted = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
                            new_count += inserted

                    # 3. 删除远程已移除的数据（批量执行）
                    delete_sql = "DELETE FROM cves WHERE cve_id = %s AND github_url = %s"
                    batch_size = 500
                    for i in range(0, len(deleted_data), batch_size):
                        batch = deleted_data[i : i + batch_size]
                        params = [(item.get("cve_id"), item.get("github_url")) for item in batch]
                        if params:
                            await cursor.executemany(delete_sql, params)
                            deleted = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
                            del_count += deleted

                    await conn.commit()
                except Exception as e:
                    await conn.rollback()
                    logger.exception("同步过程中出错，已回滚: {}", e)
                    raise

                await cursor.execute("SELECT count(*) FROM cves")
                result = await cursor.fetchone()
                total_count = result[0]

                logger.info(
                    "同步完成。新增: {} 条，删除: {} 条，数据库总记录: {} 条。",
                    new_count,
                    del_count,
                    total_count,
                )
                return new_count, del_count