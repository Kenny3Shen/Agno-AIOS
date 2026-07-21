"""Automatic user-memory prune: age cutoff + per-user top-k keep.

Job kind: ``memory_prune`` (durable).

Algorithm (per user):
1. Delete memories whose ``updated_at`` is older than *N* days (Settings).
2. Among remaining rows, score and keep only top-k; delete the rest.

Top-k score (higher is better, no LLM required):
- Recency: newer ``updated_at`` ranks higher
- Content length: short stub memories rank lower (noise)
- Topics: memories with topics get a small boost (more structured)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger

from api.services.chat_settings_service import get_chat_settings
from api.services.page_payloads import row_dict
from api.services.postgres_store import get_async_agno_postgres_db


def _as_utc_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, int | float):
        try:
            # Agno may store epoch seconds or milliseconds.
            ts = float(value)
            if ts > 1e12:
                ts = ts / 1000.0
            return datetime.fromtimestamp(ts, UTC)
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.isdigit():
            return _as_utc_datetime(int(text))
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def memory_top_k_score(
    row: dict[str, Any],
    *,
    now: datetime | None = None,
) -> float:
    """Rank one memory for top-k retention (higher = keep).

    Components are intentionally simple and deterministic so the durable job
    stays free of LLM cost and is easy to unit-test.
    """
    wall = now or datetime.now(UTC)
    updated = _as_utc_datetime(row.get("updated_at")) or _as_utc_datetime(
        row.get("created_at")
    )
    if updated is None:
        recency = 0.0
    else:
        age_days = max(0.0, (wall - updated).total_seconds() / 86_400.0)
        # Exponential-ish decay: ~1.0 when fresh, ~0.37 at ~30d, ~0.05 at ~90d.
        recency = 1.0 / (1.0 + age_days / 30.0)

    memory_text = str(row.get("memory") or "")
    length = len(memory_text.strip())
    # Prefer moderately informative memories; cap so huge dumps do not dominate.
    length_score = min(1.0, length / 280.0) if length else 0.0
    if length < 12:
        length_score *= 0.35

    topics = row.get("topics") or []
    topic_count = len(topics) if isinstance(topics, list) else 0
    topic_boost = min(0.25, 0.05 * topic_count)

    return (recency * 0.7) + (length_score * 0.25) + topic_boost


def select_memory_ids_to_prune(
    rows: list[dict[str, Any]],
    *,
    retention_days: int,
    top_k: int,
    now: datetime | None = None,
) -> list[str]:
    """Return memory_ids that should be deleted for one user."""
    wall = now or datetime.now(UTC)
    cutoff = wall - timedelta(days=max(1, int(retention_days)))
    safe_k = max(1, int(top_k))

    delete_ids: list[str] = []
    survivors: list[dict[str, Any]] = []

    for raw in rows:
        row = dict(raw)
        mid = str(row.get("memory_id") or "").strip()
        if not mid:
            continue
        updated = _as_utc_datetime(row.get("updated_at")) or _as_utc_datetime(
            row.get("created_at")
        )
        if updated is not None and updated < cutoff:
            delete_ids.append(mid)
            continue
        survivors.append(row)

    if len(survivors) <= safe_k:
        return delete_ids

    ranked = sorted(
        survivors,
        key=lambda r: (
            memory_top_k_score(r, now=wall),
            str(r.get("updated_at") or ""),
            str(r.get("memory_id") or ""),
        ),
        reverse=True,
    )
    for row in ranked[safe_k:]:
        mid = str(row.get("memory_id") or "").strip()
        if mid:
            delete_ids.append(mid)
    return delete_ids


async def _list_user_ids_with_memories(db: Any) -> list[str]:
    """Return distinct user_ids that currently own at least one memory."""
    user_ids: list[str] = []
    page = 1
    while page <= 200:
        stats, total = await db.get_user_memory_stats(limit=100, page=page)
        if not stats:
            break
        for row in stats:
            data = row if isinstance(row, dict) else row_dict(row)
            uid = str(data.get("user_id") or "").strip()
            if uid and uid not in user_ids:
                user_ids.append(uid)
        if page * 100 >= int(total or 0):
            break
        page += 1
    return user_ids


async def _fetch_all_memories_for_user(db: Any, user_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while page <= 500:
        batch, total = await db.get_user_memories(
            user_id=user_id,
            limit=100,
            page=page,
            sort_by="updated_at",
            sort_order="desc",
            deserialize=False,
        )
        if not batch:
            break
        for raw in batch:
            rows.append(raw if isinstance(raw, dict) else row_dict(raw))
        if page * 100 >= int(total or 0) or len(batch) < 100:
            break
        page += 1
    return rows


async def prune_user_memories(
    *,
    user_id: str,
    retention_days: int,
    top_k: int,
    db: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Prune one user's memories; return deletion stats."""
    owner = str(user_id or "").strip()
    if not owner:
        return {"user_id": "", "deleted": 0, "scanned": 0}
    database = db if db is not None else get_async_agno_postgres_db()
    rows = await _fetch_all_memories_for_user(database, owner)
    to_delete = select_memory_ids_to_prune(
        rows,
        retention_days=retention_days,
        top_k=top_k,
        now=now,
    )
    deleted = 0
    # Batch deletes to stay within Agno bulk API comfort.
    for offset in range(0, len(to_delete), 100):
        chunk = to_delete[offset : offset + 100]
        if not chunk:
            continue
        await database.delete_user_memories(chunk, user_id=owner)
        deleted += len(chunk)
    return {
        "user_id": owner,
        "deleted": deleted,
        "scanned": len(rows),
        "delete_ids": to_delete,
    }


async def run_memory_prune(
    *,
    retention_days: int | None = None,
    top_k: int | None = None,
    user_ids: list[str] | None = None,
    db: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run the global (or scoped) prune pass used by the durable job handler."""
    settings = await get_chat_settings()
    days = int(
        retention_days
        if retention_days is not None
        else settings.get("memory_prune_retention_days", 90)
    )
    keep_k = int(top_k if top_k is not None else settings.get("memory_prune_top_k", 50))
    days = max(1, min(3650, days))
    keep_k = max(1, min(500, keep_k))

    database = db if db is not None else get_async_agno_postgres_db()
    targets = list(user_ids) if user_ids is not None else await _list_user_ids_with_memories(
        database
    )
    per_user: list[dict[str, Any]] = []
    total_deleted = 0
    total_scanned = 0
    for uid in targets:
        result = await prune_user_memories(
            user_id=uid,
            retention_days=days,
            top_k=keep_k,
            db=database,
            now=now,
        )
        per_user.append(
            {
                "user_id": result["user_id"],
                "deleted": result["deleted"],
                "scanned": result["scanned"],
            }
        )
        total_deleted += int(result["deleted"])
        total_scanned += int(result["scanned"])

    logger.info(
        "memory prune finished users={} scanned={} deleted={} retention_days={} top_k={}",
        len(targets),
        total_scanned,
        total_deleted,
        days,
        keep_k,
    )
    return {
        "users": len(targets),
        "scanned": total_scanned,
        "deleted": total_deleted,
        "retention_days": days,
        "top_k": keep_k,
        "per_user": per_user,
    }


__all__ = [
    "memory_top_k_score",
    "prune_user_memories",
    "run_memory_prune",
    "select_memory_ids_to_prune",
]
