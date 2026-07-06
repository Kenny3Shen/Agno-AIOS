from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from functools import partial
from inspect import isawaitable, iscoroutinefunction
from typing import Any, cast

from agno.memory import UserMemory
from anyio import to_thread
from sqlalchemy import Column, DateTime, Float, MetaData, Table, Text, desc, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import CreateSchema

from api.auth.permissions import actor_id, has_permission
from api.services.approval_control_service import list_approvals_payload
from api.services.llm_service import get_all_sessions_async
from api.persistence.database import get_async_control_plane_engine
from api.services.postgres_store import (
    agno_schema,
    app_schema,
    coerce_json_value,
    get_async_agno_postgres_db,
)
from api.services.knowledge_service import knowledge_status_async
from api.services.scheduler_service import get_scheduler_payload as get_agno_scheduler_payload

OsMetric = dict[str, Any]
OsRecord = dict[str, Any]
OsPayload = dict[str, Any]

MEMORY_OPTIMIZATION_REVIEW_THRESHOLD = 50
MEMORY_ABNORMAL_GROWTH_THRESHOLD = 500

CONTROL_TABLES = {
    "evaluation": "os_eval_runs",
}


class MemoryMutationNotFound(ValueError):
    pass


class MemoryMutationFailed(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(value, UTC).isoformat()
        except (OSError, ValueError):
            return str(value)
    return str(value)


def _compact(value: Any, limit: int = 96) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _metric(label: str, value: Any, hint: str = "", tone: str = "blue") -> OsMetric:
    return {"label": label, "value": value, "hint": hint, "tone": tone}


def _record(
    *,
    record_id: Any,
    title: str,
    subtitle: str = "",
    status: str = "ready",
    meta: dict[str, Any] | None = None,
    updated_at: Any = "",
) -> OsRecord:
    return {
        "id": str(record_id or title),
        "title": title,
        "subtitle": subtitle,
        "status": status,
        "meta": meta or {},
        "updated_at": _iso(updated_at),
    }


def _payload(
    *,
    module: str,
    title: str,
    description: str,
    metrics: list[OsMetric],
    records: list[OsRecord],
    status: str = "ready",
) -> OsPayload:
    return {
        "module": module,
        "title": title,
        "description": description,
        "status": status,
        "metrics": metrics,
        "records": records,
        "generated_at": _iso(_now()),
    }


def _metadata(schema_name: str) -> MetaData:
    return MetaData(schema=schema_name)


def _evaluation_table() -> Table:
    return Table(
        CONTROL_TABLES["evaluation"],
        _metadata(app_schema()),
        Column("id", Text, primary_key=True),
        Column("name", Text, nullable=False),
        Column("target", Text, nullable=False, server_default=""),
        Column("status", Text, nullable=False, server_default="draft"),
        Column("score", Float),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )


def _projection_table(schema_name: str, table_name: str) -> Table:
    return Table(table_name, _metadata(schema_name))


def _row_dict(raw_row: Any) -> dict[str, Any]:
    if isinstance(raw_row, Mapping):
        return dict(raw_row)
    mapping = getattr(raw_row, "_mapping", None)
    if isinstance(mapping, Mapping):
        return dict(mapping)
    model_dump = getattr(raw_row, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    try:
        return dict(vars(raw_row))
    except TypeError:
        return {}


async def _count_projection(schema_name: str, table_name: str) -> int:
    """Narrow dashboard projection for Agno API gaps; do not use for normal runtime reads."""
    try:
        table = _projection_table(schema_name, table_name)
        async with get_async_control_plane_engine().begin() as conn:
            return int((await conn.execute(select(func.count()).select_from(table))).scalar_one())
    except Exception:
        return 0


async def _fetch_control_rows(table: Table, *, limit: int = 100) -> list[dict[str, Any]]:
    await _ensure_control_tables()
    stmt = select(table).order_by(desc(table.c.updated_at)).limit(limit)
    async with get_async_control_plane_engine().begin() as conn:
        return [dict(row) for row in (await conn.execute(stmt)).mappings().all()]


def _owner_user_id(actor: Any | None, any_permission: str) -> str | None:
    if actor is not None and has_permission(actor, any_permission):
        return None
    return actor_id(actor) if actor is not None else ""


def _scoped_requested_user_id(
    actor: Any | None,
    requested_user_id: str | None,
    any_permission: str,
) -> str | None:
    requested = (requested_user_id or "").strip() or None
    if actor is not None and has_permission(actor, any_permission):
        return requested
    return actor_id(actor) if actor is not None else ""


def _memory_status_for_count(count: int) -> str:
    if count >= MEMORY_ABNORMAL_GROWTH_THRESHOLD:
        return "risk"
    if count >= MEMORY_OPTIMIZATION_REVIEW_THRESHOLD:
        return "review"
    return "healthy"


def _memory_text(value: Any) -> str:
    memory = coerce_json_value(value)
    if isinstance(memory, dict):
        return str(
            memory.get("memory")
            or memory.get("content")
            or memory.get("summary")
            or ""
        )
    return str(memory or "")


def _memory_topics(value: Any) -> list[str]:
    topics = coerce_json_value(value)
    if not isinstance(topics, list):
        return []
    return [str(topic) for topic in topics if str(topic).strip()]


def _memory_row(raw_row: Any) -> dict[str, Any]:
    return _row_dict(raw_row)


def _memory_datetime(value: Any) -> datetime | None:
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


def _memory_updated_datetime(row: dict[str, Any]) -> datetime | None:
    return _memory_datetime(row.get("updated_at") or row.get("created_at"))


def _memory_epoch(value: Any) -> int | None:
    parsed = _memory_datetime(value)
    if parsed is None:
        return None
    return int(parsed.timestamp())


def _memory_update_topics(value: Any) -> list[str]:
    topics: list[str] = []
    seen: set[str] = set()
    for topic in _memory_topics(value):
        safe_topic = topic.strip()
        if not safe_topic or safe_topic in seen:
            continue
        topics.append(safe_topic)
        seen.add(safe_topic)
    return topics


async def _span_count_for_actor(actor: Any | None) -> int:
    owner_user_id = _owner_user_id(actor, "trace:read:any")
    if owner_user_id is None:
        return await _count_projection(agno_schema(), "agno_spans")
    db = get_async_agno_postgres_db()
    traces, _ = await db.get_traces(user_id=owner_user_id, limit=500, page=1)
    total = 0
    for raw_trace in traces:
        trace_id = _row_dict(raw_trace).get("trace_id")
        if not trace_id:
            continue
        total += len(await db.get_spans(trace_id=str(trace_id), limit=1000))
    return total


async def _ensure_control_tables() -> None:
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(CreateSchema(app_schema(), if_not_exists=True))
        for table in (_evaluation_table(),):
            await conn.run_sync(table.create, checkfirst=True)


def _runs_count(runs: Any) -> int:
    value = coerce_json_value(runs)
    return len(value) if isinstance(value, list) else 0


def _result_count(result: Any) -> int:
    if isinstance(result, tuple):
        return int(result[1] or 0)
    return len(result) if isinstance(result, list) else 0


def _duration_average(rows: list[dict[str, Any]]) -> float:
    durations: list[float] = []
    for row in rows:
        for key in ("avg_duration_ms", "duration_ms", "average_duration_ms"):
            value = row.get(key)
            if value is None:
                continue
            try:
                durations.append(float(value))
                break
            except (TypeError, ValueError):
                continue
    return sum(durations) / len(durations) if durations else 0.0


async def get_sessions_payload(actor: Any | None = None) -> OsPayload:
    sessions = await get_all_sessions_async(
        include_archived=True,
        owner_user_id=_owner_user_id(actor, "session:read:any"),
    )
    active_cutoff = _now() - timedelta(days=1)
    active_count = 0
    records: list[OsRecord] = []

    for session in sessions[:100]:
        updated_at = session.get("updated_at")
        updated_dt = updated_at if isinstance(updated_at, datetime) else None
        if updated_dt and updated_dt.tzinfo is None:
            updated_dt = updated_dt.replace(tzinfo=UTC)
        if updated_dt and updated_dt >= active_cutoff:
            active_count += 1
        archived = bool(session.get("archived"))
        records.append(
            _record(
                record_id=session.get("session_id"),
                title=_compact(session.get("preview") or "新对话", 64),
                subtitle=str(session.get("session_id") or ""),
                status="archived" if archived else "active" if updated_dt and updated_dt >= active_cutoff else "idle",
                meta={
                    "created": _iso(session.get("created_at")),
                    "archived": archived,
                },
                updated_at=updated_at,
            )
        )

    return _payload(
        module="sessions",
        title="Sessions",
        description="Agent 会话库存与上下文历史。",
        metrics=[
            _metric("Sessions", len(sessions), "Agno session rows", "blue"),
            _metric("Active 24h", active_count, "最近 24 小时更新", "green"),
            _metric("Archived", sum(1 for session in sessions if session.get("archived")), "Chat 侧栏软归档", "yellow"),
            _metric("Shown", len(records), "当前返回记录", "yellow"),
        ],
        records=records,
    )


async def get_memory_payload(
    actor: Any | None = None,
    *,
    user_id: str | None = None,
    topic: str | None = None,
    search: str | None = None,
    page: int = 1,
    limit: int = 50,
) -> OsPayload:
    db = get_async_agno_postgres_db()
    safe_page = max(1, int(page or 1))
    safe_limit = min(100, max(1, int(limit or 50)))
    scoped_user_id = _scoped_requested_user_id(actor, user_id, "memory:read:any")
    scoped_topic = (topic or "").strip()
    scoped_search = (search or "").strip()
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

    stats_scope_user_id = None if actor is not None and has_permission(actor, "memory:read:any") else actor_id(actor)
    user_stats, total_users = await db.get_user_memory_stats(
        user_id=stats_scope_user_id,
        limit=500,
        page=1,
    )
    topics = sorted(await db.get_all_memory_topics(user_id=scoped_user_id))

    memory_users = [
        {
            "user_id": str(row.get("user_id") or "default"),
            "total_memories": int(row.get("total_memories") or 0),
            "last_memory_updated_at": _iso(row.get("last_memory_updated_at")),
            "status": _memory_status_for_count(int(row.get("total_memories") or 0)),
        }
        for row in user_stats
    ]
    user_status_by_id: dict[str, str] = {
        str(row["user_id"]): str(row["status"]) for row in memory_users
    }
    memories = []
    records = []
    for raw_row in raw_memories:
        row = _memory_row(raw_row)
        memory_id = row.get("memory_id") or row.get("id")
        memory = _memory_text(row.get("memory") or row.get("memories") or row.get("content"))
        row_topics = _memory_topics(row.get("topics") or row.get("topic"))
        item_user_id = str(row.get("user_id") or "")
        item_status = user_status_by_id.get(item_user_id, "stored")
        item = {
            "id": str(memory_id or memory or "memory"),
            "memory": memory,
            "topics": row_topics,
            "input": str(row.get("input") or ""),
            "user_id": item_user_id,
            "agent_id": str(row.get("agent_id") or ""),
            "team_id": str(row.get("team_id") or ""),
            "feedback": str(row.get("feedback") or ""),
            "created_at": _iso(row.get("created_at")),
            "updated_at": _iso(row.get("updated_at") or row.get("created_at")),
            "status": item_status,
        }
        memories.append(item)
        records.append(
            _record(
                record_id=item["id"],
                title=_compact(memory or memory_id or "Memory", 96),
                subtitle=item["user_id"] or item["agent_id"] or "default",
                status=item_status,
                meta={
                    "topics": ", ".join(row_topics),
                    "agent_id": item["agent_id"],
                    "input": _compact(item["input"], 120),
                },
                updated_at=item["updated_at"],
            )
        )
    review_users = sum(
        1
        for row in memory_users
        if int(row["total_memories"]) >= MEMORY_OPTIMIZATION_REVIEW_THRESHOLD
    )
    risk_users = sum(
        1
        for row in memory_users
        if int(row["total_memories"]) >= MEMORY_ABNORMAL_GROWTH_THRESHOLD
    )

    payload = _payload(
        module="memory",
        title="Memory",
        description="Agno 用户记忆库存、筛选与增长监测。",
        metrics=[
            _metric("Memories", total_memories, "当前筛选命中的 Agno user memories", "blue"),
            _metric("Users", total_users, "当前权限范围内的 user_id", "green"),
            _metric("Review", review_users, f"{MEMORY_OPTIMIZATION_REVIEW_THRESHOLD}+ memories", "yellow"),
            _metric("Risk", risk_users, f"{MEMORY_ABNORMAL_GROWTH_THRESHOLD}+ memories", "red" if risk_users else "green"),
            _metric("Mode", "Auto", "update_memory_on_run", "yellow"),
        ],
        records=records,
    )
    payload.update(
        {
            "memories": memories,
            "memory_users": memory_users,
            "memory_topics": topics,
            "memory_filters": {
                "user_id": scoped_user_id or "",
                "topic": scoped_topic,
                "search": scoped_search,
                "page": safe_page,
                "limit": safe_limit,
                "total": total_memories,
            },
            "memory_thresholds": {
                "optimization_review": MEMORY_OPTIMIZATION_REVIEW_THRESHOLD,
                "abnormal_growth": MEMORY_ABNORMAL_GROWTH_THRESHOLD,
            },
            "memory_mode": {
                "type": "automatic",
                "update_memory_on_run": True,
                "enable_agentic_memory": False,
                "enable_session_summaries": True,
                "readonly": not (actor is not None and has_permission(actor, "memory:write:own")),
            },
        }
    )
    return payload


async def delete_memory_record(
    actor: Any,
    *,
    memory_id: str,
    user_id: str | None = None,
) -> dict[str, Any]:
    safe_memory_id = str(memory_id or "").strip()
    if not safe_memory_id:
        raise ValueError("memory_id is required")

    db = get_async_agno_postgres_db()
    scoped_user_id = _scoped_requested_user_id(actor, user_id, "memory:write:any")
    raw_memory = await db.get_user_memory(
        safe_memory_id,
        user_id=scoped_user_id,
        deserialize=False,
    )
    if raw_memory is None:
        raise MemoryMutationNotFound("Memory not found")

    row = _memory_row(raw_memory)
    owner_user_id = str(row.get("user_id") or scoped_user_id or "")
    await db.delete_user_memory(safe_memory_id, user_id=owner_user_id or scoped_user_id)
    remaining_memory = await db.get_user_memory(
        safe_memory_id,
        user_id=owner_user_id or scoped_user_id,
        deserialize=False,
    )
    if remaining_memory is not None:
        raise MemoryMutationFailed("Memory delete did not persist")
    return {
        "memory_id": safe_memory_id,
        "user_id": owner_user_id,
        "deleted": True,
    }


async def update_memory_record(
    actor: Any,
    *,
    memory_id: str,
    memory: str,
    topics: list[str] | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    safe_memory_id = str(memory_id or "").strip()
    if not safe_memory_id:
        raise ValueError("memory_id is required")
    safe_memory = str(memory or "").strip()
    if not safe_memory:
        raise ValueError("memory is required")

    scoped_user_id = _scoped_requested_user_id(actor, user_id, "memory:write:any")
    db = get_async_agno_postgres_db()
    raw_memory = await db.get_user_memory(
        safe_memory_id,
        user_id=scoped_user_id,
        deserialize=False,
    )
    if raw_memory is None:
        raise MemoryMutationNotFound("Memory not found")

    row = _memory_row(raw_memory)
    owner_user_id = str(row.get("user_id") or scoped_user_id or "")
    safe_topics = _memory_update_topics(topics or [])
    updated_at = int(_now().timestamp())
    updated_memory = UserMemory(
        memory=safe_memory,
        memory_id=safe_memory_id,
        topics=safe_topics,
        user_id=owner_user_id or scoped_user_id,
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
        "user_id": str(persisted_row.get("user_id") or owner_user_id),
        "agent_id": str(persisted_row.get("agent_id") or updated_memory.agent_id or ""),
        "team_id": str(persisted_row.get("team_id") or updated_memory.team_id or ""),
        "feedback": str(persisted_row.get("feedback") or updated_memory.feedback or ""),
        "created_at": _iso(persisted_row.get("created_at") or updated_memory.created_at),
        "updated_at": _iso(persisted_row.get("updated_at") or updated_at),
    }


async def get_metrics_payload(actor: Any | None = None) -> OsPayload:
    db = get_async_agno_postgres_db()
    trace_user_id = _owner_user_id(actor, "trace:read:any")
    session_user_id = _owner_user_id(actor, "session:read:any")
    memory_user_id = _owner_user_id(actor, "memory:read:any")

    traces, trace_count = await db.get_traces(
        user_id=trace_user_id,
        limit=20,
        page=1,
    )
    trace_stats, _ = await db.get_trace_stats(
        user_id=trace_user_id,
        limit=500,
        page=1,
    )
    _, error_count = await db.get_traces(
        user_id=trace_user_id,
        status="ERROR",
        limit=1,
        page=1,
    )
    session_result = await db.get_sessions(
        user_id=session_user_id,
        limit=1,
        page=1,
        sort_by="updated_at",
        sort_order="desc",
        deserialize=False,
    )
    memory_stats, _ = await db.get_user_memory_stats(
        user_id=memory_user_id,
        limit=500,
        page=1,
    )

    trace_rows = [_row_dict(row) for row in traces]
    trace_stat_rows = [_row_dict(row) for row in trace_stats]
    span_count = await _span_count_for_actor(actor)
    session_count = _result_count(session_result)
    memory_count = sum(int(row.get("total_memories") or 0) for row in memory_stats)
    avg_duration = _duration_average(trace_stat_rows) or _duration_average(trace_rows)

    records = [
        _record(
            record_id=row.get("trace_id"),
            title=_compact(row.get("name") or row.get("trace_id"), 80),
            subtitle=str(row.get("session_id") or row.get("run_id") or ""),
            status=str(row.get("status") or "UNSET"),
            meta={
                "duration_ms": row.get("duration_ms"),
                "spans": row.get("total_spans") or row.get("span_count") or "",
            },
            updated_at=row.get("start_time") or row.get("created_at"),
        )
        for row in trace_rows
    ]

    return _payload(
        module="metrics",
        title="Metrics",
        description="Agent 运行、Trace、Span、Session 与 Memory 聚合指标。",
        metrics=[
            _metric("Sessions", session_count, "Agno sessions", "blue"),
            _metric("Traces", trace_count, "Agno traces", "green"),
            _metric("Spans", span_count, "Agno spans", "yellow"),
            _metric("Errors", error_count, "ERROR traces", "red"),
            _metric("Avg Latency", f"{avg_duration:.1f} ms" if avg_duration else "-", "Trace 平均耗时", "blue"),
            _metric("Memories", memory_count, "Agno memories", "green"),
        ],
        records=records,
    )


async def get_evaluation_payload(actor: Any | None = None) -> OsPayload:
    rows = await _fetch_control_rows(_evaluation_table(), limit=100)
    records = [
        _record(
            record_id=row.get("id"),
            title=str(row.get("name") or row.get("id")),
            subtitle=str(row.get("target") or ""),
            status=str(row.get("status") or "draft"),
            meta={"score": row.get("score"), **(coerce_json_value(row.get("metadata")) if isinstance(coerce_json_value(row.get("metadata")), dict) else {})},
            updated_at=row.get("updated_at"),
        )
        for row in rows
    ]
    completed = sum(1 for row in rows if row.get("status") == "completed")
    draft = sum(1 for row in rows if row.get("status") == "draft")
    return _payload(
        module="evaluation",
        title="Evaluation",
        description="评测运行登记与质量基线准备区。",
        metrics=[
            _metric("Eval Runs", len(rows), "登记的评测运行", "blue"),
            _metric("Completed", completed, "已完成评测", "green"),
            _metric("Draft", draft, "草稿评测", "yellow"),
        ],
        records=records,
    )


async def get_approvals_payload(actor: Any | None = None) -> OsPayload:
    return await list_approvals_payload(actor=actor)


async def get_scheduler_payload(actor: Any | None = None) -> OsPayload:
    return await get_agno_scheduler_payload(actor=actor)


async def get_knowledge_payload(actor: Any | None = None) -> OsPayload:
    status = await knowledge_status_async(owner_user_id=_owner_user_id(actor, "knowledge:read:any"))
    docs = int(status.get("documents") or 0)
    chunks = int(status.get("chunks") or 0)
    records = [
        _record(
            record_id="knowledge:pgvector",
            title="PgVector Knowledge",
            subtitle=str(status.get("collection") or "vector collection"),
            status="ready" if chunks else "empty",
            meta={
                "chunks": chunks,
                "database": status.get("database"),
                "search_type": status.get("search_type"),
            },
        ),
        _record(
            record_id="knowledge:contents",
            title="Knowledge Contents",
            subtitle=str(status.get("contents_db") or "contents catalog"),
            status="ready" if docs else "empty",
            meta={"documents": docs, "schema": status.get("postgres_schema")},
        ),
    ]
    return _payload(
        module="knowledge",
        title="Knowledge",
        description="知识库内容表与向量表轻量状态。",
        metrics=[
            _metric("Documents", docs, "content rows", "blue"),
            _metric("Chunks", chunks, "vector rows", "green"),
        ],
        records=records,
    )


MODULE_HANDLERS = {
    "sessions": get_sessions_payload,
    "memory": get_memory_payload,
    "metrics": get_metrics_payload,
    "evaluation": get_evaluation_payload,
    "approvals": get_approvals_payload,
    "scheduler": get_scheduler_payload,
    "knowledge": get_knowledge_payload,
}


async def get_control_payload(
    module: str,
    actor: Any | None = None,
    *,
    query: dict[str, Any] | None = None,
) -> OsPayload:
    try:
        handler = MODULE_HANDLERS[module]
    except KeyError as exc:
        raise ValueError(f"Unsupported control module: {module}") from exc
    if module == "memory":
        return await get_memory_payload(actor=actor, **(query or {}))
    if iscoroutinefunction(handler):
        payload = handler(actor=actor)
    else:
        payload = await to_thread.run_sync(partial(handler, actor=actor))
    if isawaitable(payload):
        return await payload
    return cast(OsPayload, payload)
