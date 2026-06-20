#!/usr/bin/env python3
"""
CVE数据库更新脚本
支持从多个数据源获取CVE信息并更新到数据库

使用方法:
    uv run update-cve
    uv run python -m api.tasks.update_cve

数据源:
    - github
    - exploit-db
"""

import asyncio
import os
import sys
from datetime import datetime

from loguru import logger
import polars as pl
import psycopg
from psycopg import sql

from api.services.postgres_store import app_schema, ensure_app_tables, postgres_dsn
from api.tasks.cve_sources import DATA_SOURCES

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

async def update_cve_database(
    increment_data: list[dict[str, str]],
    deleted_data: list[dict[str, str]],
) -> tuple[int, int]:
    """
    更新 PostgreSQL 数据库：
    - 插入新增数据（ON CONFLICT DO NOTHING）
    - 删除远程已移除的数据（DELETE）
    返回 (新增条数, 删除条数)
    """
    ensure_app_tables()
    new_count = 0
    del_count = 0
    batch_size = 500
    async with await psycopg.AsyncConnection.connect(postgres_dsn()) as conn:
        try:
            async with conn.cursor() as cursor:
                cves_table = sql.Identifier(app_schema(), "cves")
                insert_sql = sql.SQL(
                    """
                    INSERT INTO {}
                        (cve_id, description, github_url, source, create_time)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (cve_id, github_url) DO NOTHING
                    """
                ).format(cves_table)
                for i in range(0, len(increment_data), batch_size):
                    batch = increment_data[i : i + batch_size]
                    create_time = datetime.now()
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
                        new_count += max(cursor.rowcount or 0, 0)

                delete_sql = sql.SQL(
                    "DELETE FROM {} WHERE cve_id = %s AND github_url = %s"
                ).format(cves_table)
                for i in range(0, len(deleted_data), batch_size):
                    batch = deleted_data[i : i + batch_size]
                    params = [
                        (item.get("cve_id"), item.get("github_url"))
                        for item in batch
                    ]
                    if params:
                        await cursor.executemany(delete_sql, params)
                        del_count += max(cursor.rowcount or 0, 0)

                await cursor.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(cves_table)
                )
                result = await cursor.fetchone()
                total_count = int(result[0]) if result else 0
            await conn.commit()
        except Exception as e:
            await conn.rollback()
            logger.exception("同步过程中出错，已回滚: {}", e)
            raise

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

    # 2. 获取远程数据（现在直接得到 DataFrame）
    new_raw_data = await source.fetch_data()
    df_remote = source.parse_data(new_raw_data)

    # 添加 source 列（Polars 原生操作，非常快）
    if not df_remote.is_empty():
        df_remote = df_remote.with_columns(pl.lit(source_name).alias("source"))

    # 3. 读取本地缓存（直接得到 DataFrame）
    local_cache_path = source.get_local_cache_path()
    df_local = pl.DataFrame()
    if os.path.exists(local_cache_path):
        logger.info(f"从本地缓存加载数据: {local_cache_path}")
        try:
            df_local = pl.read_csv(local_cache_path)
            logger.info(f"从本地缓存加载了 {df_local.height} 条记录")
        except Exception as e:
            logger.warning(f"加载本地缓存失败: {e}，按全量更新处理")
    else:
        logger.info(f"本地缓存文件不存在: {local_cache_path}，按全量更新处理")

    # 4. 对比（DataFrame in -> DataFrame out）
    df_inc, df_del = source.compare_with_local(df_remote, df_local)

    # 5. 更新本地缓存（直接写入 DataFrame）
    if not df_inc.is_empty() or not df_del.is_empty():
        os.makedirs(os.path.dirname(local_cache_path), exist_ok=True)
        df_remote.write_csv(local_cache_path)
        logger.info(f"已更新本地缓存: {local_cache_path}")

        if remote_commit:
            os.makedirs(os.path.dirname(local_commit_path), exist_ok=True)
            with open(local_commit_path, "w") as f:
                f.write(remote_commit)

        # 仅在返回给数据库更新函数时转换为 list[dict]
        return df_inc.to_dicts(), df_del.to_dicts()
    else:
        if remote_commit:
            os.makedirs(os.path.dirname(local_commit_path), exist_ok=True)
            with open(local_commit_path, "w") as f:
                f.write(remote_commit)
        logger.info("未检测到数据变化，跳过数据库更新")
        return [], []


async def main() -> tuple[int, int]:
    """主函数"""
    try:
        start_time = datetime.now()
        logger.info(f"CVE 更新开始: {start_time}")

        need_add_data, need_del_data = [], []
        task = [get_add_del_data(source_name) for source_name in DATA_SOURCES.keys()]
        results = await asyncio.gather(*task)

        for add_data, del_data in results:
            need_add_data.extend(add_data)
            need_del_data.extend(del_data)

        add_count, del_count = await update_cve_database(need_add_data, need_del_data)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info(
            f"CVE 更新完成: 新增={add_count}, 删除={del_count}, 耗时={duration:.2f}秒"
        )
        return (add_count, del_count)

    except Exception as e:
        logger.exception(f"CVE 更新失败: {e}")
        return (0, 0)


def run() -> None:
    """Console script entrypoint."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
