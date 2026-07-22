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
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from anyio import Path as AsyncPath
from anyio import to_thread
from loguru import logger
import polars as pl

from api.config import get_settings
from api.persistence.cves import (
    count_cve_rows,
    delete_cve_rows,
    find_missing_cve_source_keys,
    insert_new_cve_rows,
)
from api.services.cve_source_settings_service import get_enabled_cve_source_names
from api.tasks.cve_sources import (
    DATA_SOURCES,
    load_cve_source_config,
    normalize_cve_dataframe,
)

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
    upsert_data: list[dict[str, Any]]
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

    async def __aexit__(self, _exc_type, _exc, _tb) -> None:
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
    if environ.get("TAIS_CVE_UPDATE_LOCK_HELD") == "1":
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
        logger.info("本地缓存文件不存在: {}，按全量更新处理", path)
        return pl.DataFrame()
    logger.info("从本地缓存加载数据: {}", path)
    try:
        df_local = await to_thread.run_sync(pl.read_csv, path)
    except Exception as e:
        logger.warning("加载本地缓存失败: {}，按全量更新处理", e)
        return pl.DataFrame()
    logger.info("从本地缓存加载了 {} 条记录", df_local.height)
    return df_local


def _parse_source_data(source: Any, raw_data: Any, source_name: str) -> pl.DataFrame:
    parsed_data = source.parse_data(raw_data)
    # Built-in sources return a fully normalized frame. Keep the fallback
    # normalization for third-party/test sources, but avoid a second complete
    # materialization on the high-volume production feeds.
    df_remote = (
        parsed_data
        if getattr(source, "returns_normalized_dataframe", False)
        else normalize_cve_dataframe(parsed_data)
    )
    if not df_remote.is_empty():
        df_remote = df_remote.with_columns(pl.lit(source_name).alias("source"))
    return df_remote


_CVE_IDENTITY_COLUMNS = ("cve_id", "github_url")


def _source_identity(row: Mapping[str, Any]) -> tuple[str, str, str] | None:
    cve_id = str(row.get("cve_id") or "").strip().upper()
    github_url = str(row.get("github_url") or "").strip()
    source = str(row.get("source") or "").strip()
    if not cve_id or not github_url or not source:
        return None
    return cve_id, github_url, source


def _description_updates(
    df_remote: pl.DataFrame,
    df_local: pl.DataFrame,
) -> pl.DataFrame:
    """Return same-identity rows whose description changed upstream."""
    if df_remote.is_empty() or df_local.is_empty():
        return df_remote.head(0)
    if not set(_CVE_IDENTITY_COLUMNS).issubset(df_remote.columns) or not set(
        _CVE_IDENTITY_COLUMNS
    ).issubset(df_local.columns):
        return df_remote.head(0)

    matching_local = df_local.select(_CVE_IDENTITY_COLUMNS).unique()
    if "description" not in df_local.columns or "description" not in df_remote.columns:
        # A legacy cache without descriptions needs one full description refresh.
        return df_remote.join(
            matching_local,
            on=list(_CVE_IDENTITY_COLUMNS),
            how="inner",
        )

    local_descriptions = df_local.select(
        *[pl.col(column) for column in _CVE_IDENTITY_COLUMNS],
        pl.col("description")
        .fill_null("")
        .cast(pl.String)
        .alias("_local_description"),
    ).unique(subset=list(_CVE_IDENTITY_COLUMNS), keep="first")
    return (
        df_remote.join(
            local_descriptions,
            on=list(_CVE_IDENTITY_COLUMNS),
            how="inner",
        )
        .filter(
            pl.col("description").fill_null("").cast(pl.String)
            != pl.col("_local_description")
        )
        .select(df_remote.columns)
    )


async def _write_csv(path: str, dataframe: pl.DataFrame) -> None:
    await AsyncPath(Path(path).parent).mkdir(parents=True, exist_ok=True)
    await to_thread.run_sync(dataframe.write_csv, path)


async def _commit_source_state(delta: CVESourceDelta) -> None:
    if delta.should_update_cache:
        await _write_csv(delta.local_cache_path, delta.remote_dataframe)
        logger.info("已更新本地缓存: {}", delta.local_cache_path)
    if delta.should_update_commit and delta.remote_commit:
        await _write_text(delta.local_commit_path, delta.remote_commit)


async def update_cve_database(
    upsert_data: list[dict[str, Any]],
    deleted_data: list[dict[str, Any]],
) -> tuple[int, int]:
    """
    更新 PostgreSQL 数据库：
    - 写入新增或描述已更新的数据（按来源 ownership upsert）
    - 仅删除报告移除它的来源成员（DELETE）
    返回 (写入条数, 删除条数)
    """
    new_count = 0
    del_count = 0
    batch_size = 500
    try:
        for i in range(0, len(upsert_data), batch_size):
            new_count += await insert_new_cve_rows(upsert_data[i : i + batch_size])
        for i in range(0, len(deleted_data), batch_size):
            del_count += await delete_cve_rows(deleted_data[i : i + batch_size])
        total_count = await count_cve_rows()
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.exception("同步过程中出错: {}", e)
        raise

    logger.info(
        "同步完成。写入/刷新: {} 条，删除: {} 条，数据库总记录: {} 条。",
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

    logger.info("开始从数据源更新CVE: {}", source_name)

    # 1. 获取远程 commit 并比较本地commit，如果相同则跳过
    remote_commit = None
    try:
        remote_commit = await source.get_remote_commit()
        logger.info("数据源 {} 远程 commit: {}", source_name, remote_commit)
    except Exception as e:
        logger.warning("无法获取数据源 {} 的远程 commit: {}，继续拉取数据", source_name, e)

    local_cache_path = source.get_local_cache_path()
    local_commit_path = getattr(source, "commit_cache", None) or (
        local_cache_path + ".commit"
    )

    local_commit = None
    if remote_commit:
        local_commit = await _read_text_if_exists(local_commit_path)

    if remote_commit and local_commit == remote_commit:
        # A legacy database had a two-column uniqueness key and could only
        # retain one source for an identical reference. Reconcile this source's
        # cached snapshot even when its remote commit has not changed, so the
        # ownership migration is backfilled without forcing a full re-fetch.
        cached_snapshot = normalize_cve_dataframe(
            await _read_csv_if_exists(local_cache_path)
        )
        if not cached_snapshot.is_empty():
            cached_snapshot = cached_snapshot.with_columns(
                pl.lit(source_name).alias("source")
            )
            cached_rows = cached_snapshot.to_dicts()
            missing_keys = await find_missing_cve_source_keys(cached_rows)
            backfill_rows = [
                row
                for row in cached_rows
                if _source_identity(row) in missing_keys
            ]
            if backfill_rows:
                logger.info(
                    "数据源 {} commit 未变化，补齐 {} 条缺失 source ownership",
                    source_name,
                    len(backfill_rows),
                )
            else:
                logger.info("数据源 {} 无变化，跳过拉取", source_name)
            return CVESourceDelta(
                source_name=source_name,
                upsert_data=backfill_rows,
                deleted_data=[],
                local_cache_path=local_cache_path,
                remote_dataframe=pl.DataFrame(),
                remote_commit=remote_commit,
                local_commit_path=local_commit_path,
                should_update_cache=False,
                should_update_commit=False,
            )
        logger.warning(
            "数据源 {} commit 未变化但本地快照不可用，重新拉取以避免遗漏 ownership",
            source_name,
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
    df_local = normalize_cve_dataframe(await _read_csv_if_exists(local_cache_path))
    # A cache belongs to exactly one source.  Old cache files predate the
    # source column; overwrite any stale value so deletes have safe ownership.
    if not df_local.is_empty():
        df_local = df_local.with_columns(pl.lit(source_name).alias("source"))

    # 4. 对比（DataFrame in -> DataFrame out）
    df_inc, df_del = await to_thread.run_sync(
        source.compare_with_local,
        df_remote,
        df_local,
    )
    df_updated = _description_updates(df_remote, df_local)
    upsert_frames = [frame for frame in (df_inc, df_updated) if not frame.is_empty()]
    if upsert_frames:
        df_upsert = pl.concat(upsert_frames, how="vertical_relaxed").unique(
            subset=["cve_id", "github_url", "source"], keep="first"
        )
    else:
        df_upsert = df_remote.head(0)

    upsert_data = df_upsert.to_dicts()
    upsert_keys = {
        identity
        for row in upsert_data
        if (identity := _source_identity(row)) is not None
    }
    # A source can change one unrelated row after the ownership migration. In
    # that case, stable rows in the same remote snapshot still need a one-time
    # source-membership backfill too.
    stable_remote_rows = [
        row
        for row in df_remote.to_dicts()
        if (identity := _source_identity(row)) is not None and identity not in upsert_keys
    ]
    missing_keys = await find_missing_cve_source_keys(stable_remote_rows)
    if missing_keys:
        backfill_rows = [
            row
            for row in stable_remote_rows
            if _source_identity(row) in missing_keys
        ]
        logger.info(
            "数据源 {} 补齐 {} 条缺失 source ownership",
            source_name,
            len(backfill_rows),
        )
        upsert_data.extend(backfill_rows)

    has_changes = bool(upsert_data) or not df_del.is_empty()
    if not has_changes:
        logger.info("未检测到数据变化，跳过数据库更新")
    return CVESourceDelta(
        source_name=source_name,
        upsert_data=upsert_data,
        deleted_data=df_del.to_dicts(),
        local_cache_path=local_cache_path,
        remote_dataframe=df_remote,
        remote_commit=remote_commit,
        local_commit_path=local_commit_path,
        should_update_cache=has_changes,
        should_update_commit=bool(remote_commit),
    )


ProgressCallback = Callable[[Mapping[str, Any]], Awaitable[None] | None]


async def _emit_progress(
    on_progress: ProgressCallback | None,
    *,
    stage: str,
    status: str = "running",
    message: str = "",
    **extra: Any,
) -> None:
    if on_progress is None:
        return
    payload: dict[str, Any] = {
        "stage": stage,
        "status": status,
        "message": message,
        **extra,
    }
    result = on_progress(payload)
    if asyncio.iscoroutine(result):
        await result


async def main(
    *,
    on_progress: ProgressCallback | None = None,
) -> tuple[int, int]:
    """Run CVE database update; optionally stream stage progress events."""
    settings = get_settings()
    try:
        await _configure_file_logging_async()
        start_time = datetime.now()
        logger.info("CVE 更新开始: {}", start_time)
        await _emit_progress(
            on_progress,
            stage="start",
            message="CVE 更新开始",
        )

        async with _cve_update_lock(settings.cve_update_lock_path):
            need_upsert_data: list[dict[str, Any]] = []
            need_del_data: list[dict[str, Any]] = []
            source_config = await load_cve_source_config()
            configured_source_names = list(DATA_SOURCES.keys())
            source_names = await get_enabled_cve_source_names(configured_source_names)
            disabled_source_names = [
                source_name
                for source_name in configured_source_names
                if source_name not in source_names
            ]
            if disabled_source_names:
                logger.info("已跳过禁用的 CVE 数据源: {}", disabled_source_names)
            deltas: list[CVESourceDelta] = []

            for index, source_name in enumerate(source_names, start=1):
                await _emit_progress(
                    on_progress,
                    stage="source",
                    message=f"拉取数据源 {source_name}",
                    source=source_name,
                    source_index=index,
                    source_total=len(source_names),
                )
                delta = await get_add_del_data(source_name, source_config)
                deltas.append(delta)
                await _emit_progress(
                    on_progress,
                    stage="source",
                    status="completed",
                    message=(
                        f"{source_name}: 写入/刷新 {len(delta.upsert_data)} "
                        f"/-{len(delta.deleted_data)}"
                    ),
                    source=source_name,
                    source_index=index,
                    source_total=len(source_names),
                    add_count=len(delta.upsert_data),
                    del_count=len(delta.deleted_data),
                )

            for delta in deltas:
                need_upsert_data.extend(delta.upsert_data)
                need_del_data.extend(delta.deleted_data)

            await _emit_progress(
                on_progress,
                stage="database",
                message=(
                    f"写入数据库（新增或刷新 {len(need_upsert_data)}，"
                    f"删除 {len(need_del_data)}）"
                ),
                pending_add=len(need_upsert_data),
                pending_del=len(need_del_data),
            )
            add_count, del_count = await update_cve_database(
                need_upsert_data,
                need_del_data,
            )

            await _emit_progress(
                on_progress,
                stage="cache",
                message="提交本地缓存与 commit 标记",
            )
            for delta in deltas:
                await _commit_source_state(delta)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info(
            "CVE 更新完成: 写入/刷新={}, 删除={}, 耗时={:.2f}秒",
            add_count,
            del_count,
            duration,
        )
        await _emit_progress(
            on_progress,
            stage="done",
            status="completed",
            message="CVE 更新完成",
            add_count=add_count,
            del_count=del_count,
            duration_seconds=round(duration, 2),
        )
        return (add_count, del_count)

    except Exception as e:
        logger.exception("CVE 更新失败: {}", e)
        await _emit_progress(
            on_progress,
            stage="done",
            status="failed",
            message=str(e),
            error=str(e),
        )
        raise


def run() -> None:
    """Console script entrypoint."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
