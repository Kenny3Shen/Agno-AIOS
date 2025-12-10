#!/usr/bin/env python3
"""
CVE数据库更新脚本
支持从多个数据源获取CVE信息并更新到数据库

使用方法:
    uv run update_cve.py [--source SOURCE]

数据源:
    - github
    - exploit-db
"""

import aiomysql

import os
import sys
import asyncio
from datetime import datetime

# moved helper classes and HTTP utilities to update_utils
# moved helper classes and HTTP utilities to update_utils
from loguru import logger
import polars as pl
from update_utils import DATA_SOURCES

# 添加api目录到路径以便导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# 配置日志
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)
log_dir = os.getenv("LOG_DIR", "logs")
os.makedirs(log_dir, exist_ok=True)
logger.add(
    os.path.join(log_dir, "update_cve.log"),
    level=LOG_LEVEL,
    rotation="10 MB",
    retention="10 days",
)

DB_CONFIG = {
    "host": os.getenv("MYSQL_TEST_HOST", "localhost"),
    "user": os.getenv("MYSQL_TEST_USER", "root"),
    "password": os.getenv("MYSQL_TEST_PASSWORD", ""),
    "db": os.getenv("MYSQL_TEST_DATABASE", "cve_db"),
    "port": 3306,
    "charset": "utf8mb4",
    "autocommit": True,
}


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

    async with aiomysql.create_pool(**DB_CONFIG) as pool:
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
                            inserted = (
                                cursor.rowcount
                                if cursor.rowcount and cursor.rowcount > 0
                                else 0
                            )
                            new_count += inserted

                    # 3. 删除远程已移除的数据（批量执行）
                    delete_sql = (
                        "DELETE FROM cves WHERE cve_id = %s AND github_url = %s"
                    )
                    batch_size = 500
                    for i in range(0, len(deleted_data), batch_size):
                        batch = deleted_data[i : i + batch_size]
                        params = [
                            (item.get("cve_id"), item.get("github_url"))
                            for item in batch
                        ]
                        if params:
                            await cursor.executemany(delete_sql, params)
                            deleted = (
                                cursor.rowcount
                                if cursor.rowcount and cursor.rowcount > 0
                                else 0
                            )
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


async def update_cve_from_source(source_name: str) -> tuple[int, int]:
    """从指定数据源更新CVE数据库

    Args:
        source_name: 数据源名称

    Returns:
        (新增数量, 删除数量)
    """
    # 获取数据源
    source_class = DATA_SOURCES[source_name]
    source = source_class()

    logger.info(f"Starting CVE update from source: {source_name}")

    # 1. 获取远程数据
    new_raw_data = await source.fetch_data()
    new_parsed_data = source.parse_data(new_raw_data)

    # 2. 读取本地缓存
    local_cache_path = source.get_local_cache_path()
    old_parsed_data = []

    if os.path.exists(local_cache_path):
        logger.info(f"Loading local cache from {local_cache_path}")
        try:
            # 统一使用处理后的CSV格式缓存
            df_cache = pl.read_csv(local_cache_path)
            old_parsed_data = df_cache.to_dicts()
            logger.info(f"Loaded {len(old_parsed_data)} entries from local cache")
        except Exception as e:
            logger.warning(f"Failed to load local cache: {e}, treating as full update")
    else:
        logger.info(
            f"Local cache not found at {local_cache_path}, treating as full update"
        )

    # 3. 使用 polars 进行数据对比，找出新增和删除的CVE
    increment_data, deleted_data = source.compare_with_local(
        new_parsed_data, old_parsed_data
    )

    # 4. 更新数据库
    if increment_data or deleted_data:
        try:
            new_count, del_count = await update_cve_database(
                increment_data, deleted_data
            )

            # 5. 更新本地缓存（统一使用CSV格式保存处理后的数据）
            os.makedirs(os.path.dirname(local_cache_path), exist_ok=True)

            # 将处理后的数据保存为CSV格式
            df_to_cache = pl.DataFrame(new_parsed_data)
            df_to_cache.write_csv(local_cache_path)
            logger.info(f"Updated local cache at {local_cache_path}")

            return new_count, del_count
        except Exception as e:
            logger.exception(f"Failed to update database: {e}")
            raise
    else:
        logger.info("No changes detected, database update skipped")
        return 0, 0


async def main():
    """主函数"""
    try:
        start_time = datetime.now()
        logger.info(f"CVE update started at {start_time}")

        for source_name in DATA_SOURCES.keys():
            new_count, del_count = await update_cve_from_source(source_name)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info(
            f"CVE update completed: added={new_count}, deleted={del_count}, "
            f"duration={duration:.2f}s"
        )

    except Exception as e:
        logger.exception(f"CVE update failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
