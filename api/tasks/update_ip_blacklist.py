"""Update IP blacklist threat-intel database from configured feeds."""

from __future__ import annotations

import fcntl
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import polars as pl
from anyio import Path as AsyncPath
from loguru import logger

from api.config import get_settings
from api.persistence.ip_blacklist import (
    delete_ip_blacklist_missing_for_source,
    ensure_ip_blacklist_table,
    upsert_ip_blacklist_rows,
)
from api.tasks.ip_blacklist_sources import (
    build_sources,
    load_ip_blacklist_source_config,
)

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


class IpBlacklistUpdateAlreadyRunningError(RuntimeError):
    """Another update process holds the lock file."""


async def _emit(progress: ProgressCallback | None, payload: dict[str, Any]) -> None:
    if progress is None:
        return
    result = progress(payload)
    if result is not None:
        await result


async def _write_cache(path: str, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    await AsyncPath(target).write_text(content, encoding="utf-8")


async def update_ip_blacklist(
    *,
    progress: ProgressCallback | None = None,
) -> tuple[int, int]:
    """Fetch feeds, upsert indicators, prune removed entries for each source.

    Returns ``(upserted_count, deleted_count)`` across all sources.
    """
    settings = get_settings()
    lock_path = Path(settings.ip_blacklist_update_lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(lock_path, "a+", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock_file.close()
        raise IpBlacklistUpdateAlreadyRunningError(
            "IP 黑名单更新已在进行中"
        ) from exc

    try:
        await ensure_ip_blacklist_table()
        config = await load_ip_blacklist_source_config()
        sources = build_sources(config)
        if not sources:
            logger.warning("未配置任何 IP 黑名单源")
            await _emit(
                progress,
                {"stage": "done", "status": "completed", "add_count": 0, "del_count": 0},
            )
            return 0, 0

        await _emit(
            progress,
            {
                "stage": "start",
                "status": "running",
                "source_total": len(sources),
                "message": "开始更新 IP 黑名单",
            },
        )

        total_upsert = 0
        total_delete = 0
        for index, source in enumerate(sources, start=1):
            source_id = getattr(source, "source_id", source.__class__.__name__)
            await _emit(
                progress,
                {
                    "stage": "source",
                    "status": "running",
                    "source": source_id,
                    "source_index": index,
                    "source_total": len(sources),
                    "message": f"拉取 {source_id}",
                },
            )
            try:
                raw = await source.fetch_data()
                await _write_cache(source.get_local_cache_path(), raw)
                frame = source.parse_data(raw)
                if not isinstance(frame, pl.DataFrame) or frame.is_empty():
                    logger.warning("源 {} 无有效指标", source_id)
                    continue
                rows = frame.to_dicts()
                upserted = await upsert_ip_blacklist_rows(rows)
                indicators = [str(row.get("indicator") or "") for row in rows]
                deleted = await delete_ip_blacklist_missing_for_source(
                    source=source_id,
                    keep_indicators=indicators,
                )
                total_upsert += upserted
                total_delete += deleted
                await _emit(
                    progress,
                    {
                        "stage": "source",
                        "status": "completed",
                        "source": source_id,
                        "source_index": index,
                        "source_total": len(sources),
                        "add_count": upserted,
                        "del_count": deleted,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("更新 IP 黑名单源 {} 失败: {}", source_id, exc)
                await _emit(
                    progress,
                    {
                        "stage": "source",
                        "status": "failed",
                        "source": source_id,
                        "source_index": index,
                        "source_total": len(sources),
                        "error": str(exc),
                    },
                )
                raise

        await _emit(
            progress,
            {
                "stage": "done",
                "status": "completed",
                "add_count": total_upsert,
                "del_count": total_delete,
                "message": "IP 黑名单更新完成",
            },
        )
        logger.info(
            "IP 黑名单更新完成 upsert={} delete={}",
            total_upsert,
            total_delete,
        )
        return total_upsert, total_delete
    finally:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            lock_file.close()


async def main() -> tuple[int, int]:
    return await update_ip_blacklist()
