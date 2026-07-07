from __future__ import annotations

from typing import Any

from sqlalchemy import MetaData, Table, func, select

from api.persistence.database import get_async_control_plane_engine
from api.services.os_control_identity import owner_user_id
from api.services.os_control_payloads import OsPayload, compact, metric, payload, record, row_dict
from api.services.postgres_store import agno_schema, get_async_agno_postgres_db


def _metadata(schema_name: str) -> MetaData:
    return MetaData(schema=schema_name)


def _projection_table(schema_name: str, table_name: str):
    return Table(table_name, _metadata(schema_name))


async def _count_projection(schema_name: str, table_name: str) -> int:
    """Narrow dashboard projection for Agno API gaps; do not use for normal runtime reads."""
    try:
        table = _projection_table(schema_name, table_name)
        async with get_async_control_plane_engine().begin() as conn:
            return int((await conn.execute(select(func.count()).select_from(table))).scalar_one())
    except Exception:
        return 0


async def _span_count_for_actor(actor: Any | None) -> int:
    scoped_user_id = owner_user_id(actor)
    if scoped_user_id is None:
        return await _count_projection(agno_schema(), "agno_spans")
    db = get_async_agno_postgres_db()
    traces, _ = await db.get_traces(user_id=scoped_user_id, limit=500, page=1)
    total = 0
    for raw_trace in traces:
        trace_id = row_dict(raw_trace).get("trace_id")
        if not trace_id:
            continue
        total += len(await db.get_spans(trace_id=str(trace_id), limit=1000))
    return total


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


async def get_metrics_payload(actor: Any | None = None) -> OsPayload:
    db = get_async_agno_postgres_db()
    trace_user_id = owner_user_id(actor)
    session_user_id = owner_user_id(actor)
    memory_user_id = owner_user_id(actor)

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

    trace_rows = [row_dict(row) for row in traces]
    trace_stat_rows = [row_dict(row) for row in trace_stats]
    span_count = await _span_count_for_actor(actor)
    session_count = _result_count(session_result)
    memory_count = sum(int(row.get("total_memories") or 0) for row in memory_stats)
    avg_duration = _duration_average(trace_stat_rows) or _duration_average(trace_rows)

    records = [
        record(
            record_id=row.get("trace_id"),
            title=compact(row.get("name") or row.get("trace_id"), 80),
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

    return payload(
        module="metrics",
        title="Metrics",
        description="Agent 运行、Trace、Span、Session 与 Memory 聚合指标。",
        metrics=[
            metric("Sessions", session_count, "Agno sessions", "blue"),
            metric("Traces", trace_count, "Agno traces", "green"),
            metric("Spans", span_count, "Agno spans", "yellow"),
            metric("Errors", error_count, "ERROR traces", "red"),
            metric("Avg Latency", f"{avg_duration:.1f} ms" if avg_duration else "-", "Trace 平均耗时", "blue"),
            metric("Memories", memory_count, "Agno memories", "green"),
        ],
        records=records,
    )
