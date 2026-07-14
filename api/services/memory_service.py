from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from agno.memory import UserMemory

from api.auth.claims import ActorLike
from api.services.actor_scope import scoped_requested_user_id
from api.services.page_payloads import iso, now_utc, row_dict
from api.services.postgres_store import coerce_json_value, get_async_agno_postgres_db

MEMORY_OPTIMIZATION_REVIEW_THRESHOLD = 50
MEMORY_ABNORMAL_GROWTH_THRESHOLD = 500


class MemoryItemPayload(TypedDict):
    memory_id: str
    memory: str
    topics: list[str]
    input: str
    user_id: str
    agent_id: str
    team_id: str
    feedback: str
    created_at: str
    updated_at: str
    status: str


class MemoryPaginationMeta(TypedDict):
    page: int
    limit: int
    total_pages: int
    total_count: int
    search_time_ms: float


class MemoryListNativeResponse(TypedDict):
    data: list[MemoryItemPayload]
    meta: MemoryPaginationMeta


class MemoryMutationNotFound(ValueError):
    pass


class MemoryMutationFailed(RuntimeError):
    pass


def _now() -> datetime:
    return now_utc()


def _memory_status_for_count(count: int) -> str:
    if count >= MEMORY_ABNORMAL_GROWTH_THRESHOLD:
        return "risk"
    if count >= MEMORY_OPTIMIZATION_REVIEW_THRESHOLD:
        return "review"
    return "healthy"


def _memory_text(value: object) -> str:
    memory = coerce_json_value(value)
    if isinstance(memory, dict):
        return str(
            memory.get("memory")
            or memory.get("content")
            or memory.get("summary")
            or ""
        )
    return str(memory or "")


def _memory_topics(value: object) -> list[str]:
    topics = coerce_json_value(value)
    if not isinstance(topics, list):
        return []
    return [str(topic) for topic in topics if str(topic).strip()]


def _memory_row(raw_row: object) -> dict[str, object]:
    return row_dict(raw_row)


def _memory_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(value, UTC)
        except (OSError, ValueError):
            return None
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        if text_value.isdigit():
            return datetime.fromtimestamp(int(text_value), UTC)
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _memory_epoch(value: object) -> int | None:
    parsed = _memory_datetime(value)
    if parsed is None:
        return None
    return int(parsed.timestamp())


def _memory_update_topics(value: object) -> list[str]:
    topics: list[str] = []
    seen: set[str] = set()
    for topic in _memory_topics(value):
        safe_topic = topic.strip()
        if not safe_topic or safe_topic in seen:
            continue
        topics.append(safe_topic)
        seen.add(safe_topic)
    return topics


def _pagination_meta(*, page: int, limit: int, total_count: int, search_time_ms: float = 0.0) -> MemoryPaginationMeta:
    safe_page = max(1, int(page or 1))
    safe_limit = max(1, int(limit or 1))
    total = max(0, int(total_count or 0))
    total_pages = (total + safe_limit - 1) // safe_limit if total else 0
    return {
        "page": safe_page,
        "limit": safe_limit,
        "total_pages": total_pages,
        "total_count": total,
        "search_time_ms": float(search_time_ms or 0.0),
    }


def _memory_item(
    row: dict[str, object],
    *,
    status: str = "stored",
) -> MemoryItemPayload:
    memory_id = row.get("memory_id") or row.get("id")
    memory = _memory_text(row.get("memory") or row.get("memories") or row.get("content"))
    item_id = str(memory_id or memory or "memory")
    return {
        "memory_id": item_id,
        "memory": memory,
        "topics": _memory_topics(row.get("topics") or row.get("topic")),
        "input": str(row.get("input") or ""),
        "user_id": str(row.get("user_id") or ""),
        "agent_id": str(row.get("agent_id") or ""),
        "team_id": str(row.get("team_id") or ""),
        "feedback": str(row.get("feedback") or ""),
        "created_at": iso(row.get("created_at")),
        "updated_at": iso(row.get("updated_at") or row.get("created_at")),
        "status": status,
    }


async def list_memories_native(
    actor: ActorLike | None = None,
    *,
    user_id: str | None = None,
    topic: str | None = None,
    search_content: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> MemoryListNativeResponse:
    """List memories in Agno-native paginated form."""
    db = get_async_agno_postgres_db()
    safe_page = max(1, int(page or 1))
    safe_limit = min(100, max(1, int(limit or 20)))
    scoped_user_id = scoped_requested_user_id(actor, user_id)
    scoped_topic = (topic or "").strip()
    scoped_search = (
        str(search_content).strip()
        if search_content is not None and str(search_content).strip()
        else ""
    )
    topics_filter = [scoped_topic] if scoped_topic else None

    raw_result = await db.get_user_memories(
        user_id=scoped_user_id,
        topics=topics_filter,
        search_content=scoped_search or None,
        limit=safe_limit,
        page=safe_page,
        sort_by="updated_at",
        sort_order="desc",
        deserialize=False,
    )
    if isinstance(raw_result, tuple):
        raw_memories, total_memories = raw_result
    else:
        raw_memories = raw_result
        total_memories = len(raw_memories)

    # Growth status is derived from per-user memory counts in the actor scope.
    user_stats, _total_users = await db.get_user_memory_stats(
        user_id=scoped_requested_user_id(actor, None),
        limit=500,
        page=1,
    )
    user_status_by_id: dict[str, str] = {
        str(row.get("user_id") or "default"): _memory_status_for_count(
            int(row.get("total_memories") or 0)
        )
        for row in user_stats
    }

    items: list[MemoryItemPayload] = []
    for raw_row in raw_memories:
        row = _memory_row(raw_row)
        item_user_id = str(row.get("user_id") or "")
        items.append(
            _memory_item(
                row,
                status=user_status_by_id.get(item_user_id, "stored"),
            )
        )

    return {
        "data": items,
        "meta": _pagination_meta(
            page=safe_page,
            limit=safe_limit,
            total_count=int(total_memories),
        ),
    }


async def delete_memory_record(
    actor: ActorLike,
    *,
    memory_id: str,
    user_id: str | None = None,
) -> dict[str, object]:
    safe_memory_id = str(memory_id or "").strip()
    if not safe_memory_id:
        raise ValueError("memory_id is required")

    db = get_async_agno_postgres_db()
    scoped_user_id = scoped_requested_user_id(actor, user_id)
    raw_memory = await db.get_user_memory(
        safe_memory_id,
        user_id=scoped_user_id,
        deserialize=False,
    )
    if raw_memory is None:
        raise MemoryMutationNotFound("Memory not found")

    row = _memory_row(raw_memory)
    owner_user = str(row.get("user_id") or scoped_user_id or "")
    await db.delete_user_memory(safe_memory_id, user_id=owner_user or scoped_user_id)
    remaining_memory = await db.get_user_memory(
        safe_memory_id,
        user_id=owner_user or scoped_user_id,
        deserialize=False,
    )
    if remaining_memory is not None:
        raise MemoryMutationFailed("Memory delete did not persist")
    return {
        "memory_id": safe_memory_id,
        "user_id": owner_user,
        "deleted": True,
    }


async def update_memory_record(
    actor: ActorLike,
    *,
    memory_id: str,
    memory: str,
    topics: list[str] | None = None,
    user_id: str | None = None,
) -> dict[str, object]:
    safe_memory_id = str(memory_id or "").strip()
    if not safe_memory_id:
        raise ValueError("memory_id is required")
    safe_memory = str(memory or "").strip()
    if not safe_memory:
        raise ValueError("memory is required")

    scoped_user_id = scoped_requested_user_id(actor, user_id)
    db = get_async_agno_postgres_db()
    raw_memory = await db.get_user_memory(
        safe_memory_id,
        user_id=scoped_user_id,
        deserialize=False,
    )
    if raw_memory is None:
        raise MemoryMutationNotFound("Memory not found")

    row = _memory_row(raw_memory)
    owner_user = str(row.get("user_id") or scoped_user_id or "")
    safe_topics = _memory_update_topics(topics or [])
    updated_at = int(_now().timestamp())
    updated_memory = UserMemory(
        memory=safe_memory,
        memory_id=safe_memory_id,
        topics=safe_topics,
        user_id=owner_user or scoped_user_id,
        input=str(row.get("input") or ""),
        created_at=_memory_epoch(row.get("created_at")),
        updated_at=updated_at,
        feedback=str(row.get("feedback") or ""),
        agent_id=str(row.get("agent_id") or ""),
        team_id=str(row.get("team_id") or ""),
    )
    persisted_memory = await db.upsert_user_memory(memory=updated_memory, deserialize=False)
    if persisted_memory is None:
        raise MemoryMutationFailed("Memory update did not persist")
    persisted_row = _memory_row(persisted_memory)
    return {
        "memory_id": safe_memory_id,
        "memory": _memory_text(persisted_row.get("memory")) or safe_memory,
        "topics": _memory_topics(persisted_row.get("topics")) or safe_topics,
        "input": str(persisted_row.get("input") or updated_memory.input or ""),
        "user_id": str(persisted_row.get("user_id") or owner_user),
        "agent_id": str(persisted_row.get("agent_id") or updated_memory.agent_id or ""),
        "team_id": str(persisted_row.get("team_id") or updated_memory.team_id or ""),
        "feedback": str(persisted_row.get("feedback") or updated_memory.feedback or ""),
        "created_at": iso(persisted_row.get("created_at") or updated_memory.created_at),
        "updated_at": iso(persisted_row.get("updated_at") or updated_at),
    }
