#!/usr/bin/env python3
"""
CVE数据库更新脚本
支持从多个数据源获取CVE信息并更新到数据库

使用方法:
    uv run update_cve.py

数据源:
    - github
    - exploit-db
"""

import aiomysql
import os
import sys
import asyncio
from datetime import datetime
from loguru import logger
import polars as pl
from update_utils import DATA_SOURCES

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
    "port": int(os.getenv("MYSQL_TEST_PORT", 3306)),
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
                        github_url VARCHAR(255) NOT NULL,
                        source VARCHAR(50) NOT NULL,
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
                                INSERT IGNORE INTO cves (cve_id, description, github_url, source, create_time)
                                VALUES (%s, %s, %s, %s, %s)
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
                                item.get("source", ""),
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


async def get_add_del_data(
    source_name: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """从指定数据源获取新增和删除的CVE数据

    Args:
        source_name: 数据源名称

    Returns:
        (新增数据列表, 删除数据列表)
    """
    # 获取数据源
    source_class = DATA_SOURCES[source_name]
    source = source_class()

    logger.info(f"开始从数据源更新CVE: {source_name}")

    # 1. 获取远程 commit 并比较本地commit，如果相同则跳过
    remote_commit = None
    try:
        remote_commit = await source.get_remote_commit()
        logger.info(f"数据源 {source_name} 远程 commit: {remote_commit}")
    except Exception as e:
        logger.warning(f"无法获取数据源 {source_name} 的远程 commit: {e}，继续拉取数据")

    local_commit_path = getattr(source, "commit_cache", None)
    if not local_commit_path:
        local_cache_path = source.get_local_cache_path()
        local_commit_path = local_cache_path + ".commit"

    local_commit = None
    if remote_commit and os.path.exists(local_commit_path):
        with open(local_commit_path, "r") as f:
            local_commit = f.read().strip()

    if remote_commit and local_commit == remote_commit:
        logger.info(f"数据源 {source_name} 无变化，跳过拉取")
        return [], []

    # 2. 获取远程数据
    new_raw_data = await source.fetch_data()
    new_parsed_data = source.parse_data(new_raw_data)

    # 为每条数据添加source字段
    for item in new_parsed_data:
        item["source"] = source_name

    # 2. 读取本地缓存
    local_cache_path = source.get_local_cache_path()
    old_parsed_data = []

    if os.path.exists(local_cache_path):
        logger.info(f"从本地缓存加载数据: {local_cache_path}")
        try:
            df_cache = pl.read_csv(local_cache_path)
            old_parsed_data = df_cache.to_dicts()
            logger.info(f"从本地缓存加载了 {len(old_parsed_data)} 条记录")
        except Exception as e:
            logger.warning(f"加载本地缓存失败: {e}，按全量更新处理")
    else:
        logger.info(f"本地缓存文件不存在: {local_cache_path}，按全量更新处理")

    # 3. 使用 polars 进行数据对比，找出新增和删除的CVE
    increment_data, deleted_data = source.compare_with_local(
        new_parsed_data, old_parsed_data
    )

    # 4. 更新本地缓存
    if increment_data or deleted_data:
        os.makedirs(os.path.dirname(local_cache_path), exist_ok=True)
        df_to_cache = pl.DataFrame(new_parsed_data)
        df_to_cache.write_csv(local_cache_path)
        logger.info(f"已更新本地缓存: {local_cache_path}")

        if remote_commit:
            os.makedirs(os.path.dirname(local_commit_path), exist_ok=True)
            with open(local_commit_path, "w") as f:
                f.write(remote_commit)
        return increment_data, deleted_data
    else:
        if remote_commit:
            os.makedirs(os.path.dirname(local_commit_path), exist_ok=True)
            with open(local_commit_path, "w") as f:
                f.write(remote_commit)
        logger.info("未检测到数据变化，跳过数据库更新")
        return [], []


async def main():
    """主函数"""
    try:
        start_time = datetime.now()
        logger.info(f"CVE 更新开始: {start_time}")

        need_add_data, need_del_data = [], []
        for source_name in DATA_SOURCES.keys():
            increment_data, deleted_data = await get_add_del_data(source_name)
            need_add_data.extend(increment_data)
            need_del_data.extend(deleted_data)

        new_count, del_count = await update_cve_database(need_add_data, need_del_data)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info(
            f"CVE 更新完成: 新增={new_count}, 删除={del_count}, "
            f"耗时={duration:.2f}秒"
        )

    except Exception as e:
        logger.exception(f"CVE 更新失败: {e}")


if __name__ == "__main__":
    asyncio.run(main())
