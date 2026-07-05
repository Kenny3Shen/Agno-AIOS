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
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
import fcntl
from os import environ
from pathlib import Path
from typing import Any

from anyio import Path as AsyncPath
from anyio import to_thread
from loguru import logger
import polars as pl

from api.config import get_settings
from api.persistence.cves import count_cve_rows, delete_cve_rows, insert_new_cve_rows
from api.tasks.cve_sources import DATA_SOURCES, load_cve_source_config

_FILE_LOGGING_CONFIGURED = False


class CVEUpdateError(RuntimeError):
    """Base error for CVE update failures."""


class CVEUpdateAlreadyRunningError(CVEUpdateError):
    """Raised when another CVE update holds the task lock."""


class CVEDataSourceEmptyError(CVEUpdateError):
    """Raised when a data source fetch succeeds but parses to zero rows."""


@dataclass(slots=True)
class CVESourceDelta:
    source_name: str
    increment_data: list[dict[str, Any]]
    deleted_data: list[dict[str, Any]]
    local_cache_path: str
    remote_dataframe: pl.DataFrame
    remote_commit: str | None
    local_commit_path: str
    should_update_cache: bool
    should_update_commit: bool


class CVEUpdateFileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None

    async def __aenter__(self) -> "CVEUpdateFileLock":
        await to_thread.run_sync(self._acquire)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await to_thread.run_sync(self._release)

    def _acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("w", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise CVEUpdateAlreadyRunningError("CVE update is already running") from exc
        handle.write(f"{datetime.now().isoformat()}\n")
        handle.flush()
        self._handle = handle

    def _release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self._handle = None


@asynccontextmanager
async def _cve_update_lock(path: Path):
    if environ.get("AGNO_CVE_UPDATE_LOCK_HELD") == "1":
        yield
        return
    async with CVEUpdateFileLock(path):
        yield


def _configure_file_logging_once() -> None:
    global _FILE_LOGGING_CONFIGURED
    if _FILE_LOGGING_CONFIGURED:
        return
    settings = get_settings()
    log_dir = settings.log_dir
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "update_cve.log",
        level=settings.log_level,
        rotation="10 MB",
        retention="10 days",
    )
    _FILE_LOGGING_CONFIGURED = True


async def _configure_file_logging_async() -> None:
    await to_thread.run_sync(_configure_file_logging_once)


async def _read_text_if_exists(path: str) -> str | None:
    async_path = AsyncPath(path)
    if not await async_path.exists():
        return None
    return (await async_path.read_text(encoding="utf-8")).strip()


async def _write_text(path: str, value: str) -> None:
    async_path = AsyncPath(path)
    await async_path.parent.mkdir(parents=True, exist_ok=True)
    await async_path.write_text(value, encoding="utf-8")


async def _read_csv_if_exists(path: str) -> pl.DataFrame:
    async_path = AsyncPath(path)
    if not await async_path.exists():
        logger.info(f"本地缓存文件不存在: {path}，按全量更新处理")
        return pl.DataFrame()
    logger.info(f"从本地缓存加载数据: {path}")
    try:
        df_local = await to_thread.run_sync(pl.read_csv, path)
    except Exception as e:
        logger.warning(f"加载本地缓存失败: {e}，按全量更新处理")
        return pl.DataFrame()
    logger.info(f"从本地缓存加载了 {df_local.height} 条记录")
    return df_local


def _parse_source_data(source: Any, raw_data: Any, source_name: str) -> pl.DataFrame:
    df_remote = source.parse_data(raw_data)
    if not df_remote.is_empty():
        df_remote = df_remote.with_columns(pl.lit(source_name).alias("source"))
    return df_remote


async def _write_csv(path: str, dataframe: pl.DataFrame) -> None:
    await AsyncPath(Path(path).parent).mkdir(parents=True, exist_ok=True)
    await to_thread.run_sync(dataframe.write_csv, path)


async def _commit_source_state(delta: CVESourceDelta) -> None:
    if delta.should_update_cache:
        await _write_csv(delta.local_cache_path, delta.remote_dataframe)
        logger.info(f"已更新本地缓存: {delta.local_cache_path}")
    if delta.should_update_commit and delta.remote_commit:
        await _write_text(delta.local_commit_path, delta.remote_commit)


async def update_cve_database(
    increment_data: list[dict[str, Any]],
    deleted_data: list[dict[str, Any]],
) -> tuple[int, int]:
    """
    更新 PostgreSQL 数据库：
    - 插入新增数据（ON CONFLICT DO NOTHING）
    - 删除远程已移除的数据（DELETE）
    返回 (新增条数, 删除条数)
    """
    new_count = 0
    del_count = 0
    batch_size = 500
    try:
        for i in range(0, len(increment_data), batch_size):
            new_count += await insert_new_cve_rows(increment_data[i : i + batch_size])
        for i in range(0, len(deleted_data), batch_size):
            del_count += await delete_cve_rows(deleted_data[i : i + batch_size])
        total_count = await count_cve_rows()
    except Exception as e:
        logger.exception("同步过程中出错: {}", e)
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
    source_config: dict[str, Any] | None = None,
) -> CVESourceDelta:
    """从指定数据源获取新增和删除的CVE数据

    Args:
        source_name: 数据源名称

    Returns:
        CVESourceDelta，包含新增/删除数据和等待 DB 成功后提交的本地状态。
    """
    # 获取数据源
    source_class = DATA_SOURCES[source_name]
    source = source_class(source_config)

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
    if remote_commit:
        local_commit = await _read_text_if_exists(local_commit_path)

    if remote_commit and local_commit == remote_commit:
        logger.info(f"数据源 {source_name} 无变化，跳过拉取")
        return CVESourceDelta(
            source_name=source_name,
            increment_data=[],
            deleted_data=[],
            local_cache_path=source.get_local_cache_path(),
            remote_dataframe=pl.DataFrame(),
            remote_commit=remote_commit,
            local_commit_path=local_commit_path,
            should_update_cache=False,
            should_update_commit=False,
        )

    # 2. 获取远程数据（现在直接得到 DataFrame）
    new_raw_data = await source.fetch_data()
    df_remote = await to_thread.run_sync(
        _parse_source_data,
        source,
        new_raw_data,
        source_name,
    )
    if df_remote.is_empty():
        raise CVEDataSourceEmptyError(
            f"数据源 {source_name} parsed no CVE rows; refusing to delete local cache"
        )

    # 3. 读取本地缓存（直接得到 DataFrame）
    local_cache_path = source.get_local_cache_path()
    df_local = await _read_csv_if_exists(local_cache_path)

    # 4. 对比（DataFrame in -> DataFrame out）
    df_inc, df_del = await to_thread.run_sync(
        source.compare_with_local,
        df_remote,
        df_local,
    )

    has_changes = not df_inc.is_empty() or not df_del.is_empty()
    if not has_changes:
        logger.info("未检测到数据变化，跳过数据库更新")
    return CVESourceDelta(
        source_name=source_name,
        increment_data=df_inc.to_dicts(),
        deleted_data=df_del.to_dicts(),
        local_cache_path=local_cache_path,
        remote_dataframe=df_remote,
        remote_commit=remote_commit,
        local_commit_path=local_commit_path,
        should_update_cache=has_changes,
        should_update_commit=bool(remote_commit),
    )


async def main() -> tuple[int, int]:
    """主函数"""
    settings = get_settings()
    try:
        await _configure_file_logging_async()
        start_time = datetime.now()
        logger.info(f"CVE 更新开始: {start_time}")

        async with _cve_update_lock(settings.cve_update_lock_path):
            need_add_data, need_del_data = [], []
            source_config = await load_cve_source_config()
            task = [
                get_add_del_data(source_name, source_config)
                for source_name in DATA_SOURCES.keys()
            ]
            deltas = await asyncio.gather(*task)

            for delta in deltas:
                need_add_data.extend(delta.increment_data)
                need_del_data.extend(delta.deleted_data)

            add_count, del_count = await update_cve_database(need_add_data, need_del_data)
            for delta in deltas:
                await _commit_source_state(delta)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info(
            f"CVE 更新完成: 新增={add_count}, 删除={del_count}, 耗时={duration:.2f}秒"
        )
        return (add_count, del_count)

    except Exception as e:
        logger.exception(f"CVE 更新失败: {e}")
        raise


def run() -> None:
    """Console script entrypoint."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
