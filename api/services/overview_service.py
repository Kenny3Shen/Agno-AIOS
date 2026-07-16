from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi.encoders import jsonable_encoder
from loguru import logger
from sqlalchemy import and_, case, cast, func, select
from sqlalchemy.types import DateTime, Float

from api.auth.claims import ActorLike, has_scope, scope_user_id
from api.services.postgres_store import get_async_agno_postgres_db
from api.services.trace_status_service import reconcile_trace_statuses

OverviewRange = Literal["1h", "24h", "7d"]
OverviewQueryRange = OverviewRange | Literal["custom"]

_RANGE_WINDOWS: dict[OverviewRange, timedelta] = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}
_PAGE_LIMIT = 1_000
# Cap dashboard materialization so 7d windows cannot load unbounded history.
_MAX_OVERVIEW_TRACE_PAGES = 5  # 5 * 1000 = 5000 traces max per overview request
_MAX_OVERVIEW_TRACES = _PAGE_LIMIT * _MAX_OVERVIEW_TRACE_PAGES


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    return None


def _parse_custom_datetime(value: str | datetime, *, parameter: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = value.strip()
        if not text:
            raise ValueError(f"{parameter} must be an ISO8601 timestamp with timezone")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{parameter} must be an ISO8601 timestamp with timezone") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{parameter} must include a timezone")
    return parsed.astimezone(UTC)


def _custom_range(
    start_time: str | datetime | None, end_time: str | datetime | None
) -> tuple[datetime, datetime] | None:
    if start_time is None and end_time is None:
        return None
    if start_time is None or end_time is None:
        raise ValueError("start_time and end_time must be provided together")
    start = _parse_custom_datetime(start_time, parameter="start_time")
    end = _parse_custom_datetime(end_time, parameter="end_time")
    if start >= end:
        raise ValueError("start_time must be earlier than end_time")
    return start, end


def _bucket_range(start: datetime, end: datetime) -> OverviewRange:
    window = end - start
    if window <= _RANGE_WINDOWS["1h"]:
        return "1h"
    if window <= _RANGE_WINDOWS["24h"]:
        return "24h"
    return "7d"


def _duration_ms(trace: dict[str, Any]) -> float | None:
    for key in ("duration_ms", "duration", "latency_ms"):
        value = trace.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    start_time = _as_datetime(trace.get("start_time"))
    end_time = _as_datetime(trace.get("end_time"))
    if start_time is not None and end_time is not None:
        return max(0.0, (end_time - start_time).total_seconds() * 1_000)
    return None


_INPUT_TOKEN_KEYS = (
    "input_tokens",
    "prompt_tokens",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.prompt_tokens",
    "llm.token_count.input",
    "llm.token_count.prompt",
    "openinference.llm.token_count.input",
    "openinference.llm.token_count.prompt",
)
_OUTPUT_TOKEN_KEYS = (
    "output_tokens",
    "completion_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.completion_tokens",
    "llm.token_count.output",
    "llm.token_count.completion",
    "openinference.llm.token_count.output",
    "openinference.llm.token_count.completion",
)
_TOTAL_TOKEN_KEYS = (
    "total_tokens",
    "tokens",
    "gen_ai.usage.total_tokens",
    "llm.token_count.total",
    "openinference.llm.token_count.total",
)


def _numeric_token(value: Any) -> int | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return max(0, int(value))
    return None


def _token_value(sources: tuple[dict[str, Any], ...], keys: tuple[str, ...], nested_key: str) -> int | None:
    for source in sources:
        for key in keys:
            value = _numeric_token(source.get(key))
            if value is not None:
                return value
        tokens = source.get("tokens")
        if isinstance(tokens, dict):
            value = _numeric_token(tokens.get(nested_key))
            if value is not None:
                return value
    return None


def _token_counts(trace: dict[str, Any]) -> dict[str, int]:
    """Read token usage from common trace, OpenTelemetry, and OpenInference shapes."""
    sources = tuple(
        source for source in (trace, trace.get("attributes"), trace.get("metadata")) if isinstance(source, dict)
    )
    input_tokens = _token_value(sources, _INPUT_TOKEN_KEYS, "input")
    if input_tokens is None:
        input_tokens = _token_value(sources, (), "prompt")
    output_tokens = _token_value(sources, _OUTPUT_TOKEN_KEYS, "output")
    if output_tokens is None:
        output_tokens = _token_value(sources, (), "completion")
    total_tokens = _token_value(sources, _TOTAL_TOKEN_KEYS, "total")
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens or 0,
        "output_tokens": output_tokens or 0,
        "total_tokens": total_tokens or 0,
    }


def _add_token_counts(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    return {
        name: left[name] + right[name]
        for name in ("input_tokens", "output_tokens", "total_tokens")
    }


async def _fetch_span_token_counts(trace_ids: list[str]) -> dict[str, dict[str, int]]:
    """Aggregate LLM usage attributes from spans in a single database query.

    Trace rows intentionally only carry run context. Agno/OpenInference writes
    model usage onto child spans, so a trace-only overview silently reports
    zero for otherwise completed chat runs.
    """
    if not trace_ids:
        return {}

    db = get_async_agno_postgres_db()
    spans_table = await db._get_table(table_type="spans")
    if spans_table is None:
        return {}

    counts: dict[str, dict[str, int]] = {}
    async with db.async_session_factory() as session:
        result = await session.execute(
            select(spans_table.c.trace_id, spans_table.c.attributes).where(
                spans_table.c.trace_id.in_(trace_ids)
            )
        )
        for row in result.mappings():
            attributes = row.get("attributes")
            if not isinstance(attributes, dict):
                continue
            token_counts = _token_counts({"attributes": attributes})
            if not any(token_counts.values()):
                continue
            trace_id = str(row["trace_id"])
            counts[trace_id] = _add_token_counts(
                counts.get(trace_id, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}),
                token_counts,
            )
    return counts


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    if lower == upper:
        return round(values[lower], 2)
    return round(values[lower] + (values[upper] - values[lower]) * (position - lower), 2)


def _is_failure(trace: dict[str, Any]) -> bool:
    return str(trace.get("status") or "").upper() in {"ERROR", "FAILED", "FAILURE"}


def _bucket_timestamp(start: datetime, *, range_name: OverviewRange, timezone: ZoneInfo) -> str:
    local = start.astimezone(timezone)
    if range_name == "7d":
        local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    elif range_name == "24h":
        local = local.replace(minute=0, second=0, microsecond=0)
    else:
        local = local.replace(second=0, microsecond=0)
    return local.isoformat()


def _bucket_end(timestamp: str, *, range_name: OverviewRange, timezone: ZoneInfo) -> str:
    local_start = datetime.fromisoformat(timestamp).astimezone(timezone)
    if range_name == "7d":
        end = local_start + timedelta(days=1)
    elif range_name == "24h":
        end = local_start + timedelta(hours=1)
    else:
        end = local_start + timedelta(minutes=1)
    return end.isoformat()


def _distribution(traces: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    counts = Counter(str(trace.get(field) or "").strip() for trace in traces)
    return [
        {"name": name, "value": value}
        for name, value in counts.most_common()
        if name
    ]


def _recent_failure(trace: dict[str, Any]) -> dict[str, Any]:
    return {
        "trace_id": str(trace.get("trace_id") or trace.get("id") or ""),
        "run_id": str(trace.get("run_id") or ""),
        "session_id": str(trace.get("session_id") or ""),
        "name": str(trace.get("name") or trace.get("agent_name") or trace.get("run_id") or "Run"),
        "status": str(trace.get("status") or "ERROR"),
        "start_time": trace.get("start_time"),
        "duration_ms": _duration_ms(trace),
        "agent_id": trace.get("agent_id"),
        "team_id": trace.get("team_id"),
        "workflow_id": trace.get("workflow_id"),
    }


async def _count_traces(
    *,
    start: datetime,
    end: datetime,
    user_id: str | None,
    status: str | None = None,
) -> int:
    """Cheap window total via Agno ``get_traces`` total (limit=1)."""
    db = get_async_agno_postgres_db()
    _rows, total = await db.get_traces(
        start_time=start,
        end_time=end,
        user_id=user_id,
        status=status,
        limit=1,
        page=1,
    )
    return max(0, int(total or 0))


async def _fetch_recent_failures(
    *,
    start: datetime,
    end: datetime,
    user_id: str | None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Load recent ERROR traces via native status filter (not sample slice)."""
    safe_limit = max(1, min(int(limit or 10), 50))
    db = get_async_agno_postgres_db()
    traces, _total = await db.get_traces(
        start_time=start,
        end_time=end,
        user_id=user_id,
        status="ERROR",
        limit=safe_limit,
        page=1,
    )
    rows: list[dict[str, Any]] = []
    for trace in traces:
        dumped = trace if isinstance(trace, dict) else trace.to_dict()
        rows.append(jsonable_encoder(dumped))
    reconciled = await reconcile_trace_statuses(rows, actor_user_id=user_id)
    # Keep ERROR after audit overlay; drop flipped non-failures.
    failures = [row for row in reconciled if _is_failure(row)]
    failures.sort(
        key=lambda item: _as_datetime(item.get("start_time")) or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    return failures[:safe_limit]


def _trace_window_filters(table, *, start: datetime, end: datetime, user_id: str | None):
    """Shared WHERE clauses for overview SQL over ``agno_traces``."""
    filters = [
        table.c.start_time >= start.isoformat(),
        table.c.start_time <= end.isoformat(),
    ]
    if user_id:
        filters.append(table.c.user_id == user_id)
    return and_(*filters)


def _duration_ms_expr(table):
    """Prefer stored duration_ms; fall back to end-start when present."""
    # start_time / end_time are ISO strings in Agno Postgres storage.
    start_ts = cast(table.c.start_time, DateTime(timezone=True))
    end_ts = cast(table.c.end_time, DateTime(timezone=True))
    computed = func.extract("epoch", end_ts - start_ts) * 1000.0
    return cast(
        func.coalesce(table.c.duration_ms, computed),
        Float,
    )


def _bucket_trunc_unit(range_name: OverviewRange) -> str:
    if range_name == "7d":
        return "day"
    if range_name == "24h":
        return "hour"
    return "minute"


def _sql_bucket_timestamp_expr(table, *, range_name: OverviewRange, timezone_key: str):
    """Local wall-clock bucket start (timestamp without tz) for date_trunc."""
    start_ts = cast(table.c.start_time, DateTime(timezone=True))
    # timestamptz AT TIME ZONE zone → local timestamp without time zone
    local_ts = func.timezone(timezone_key, start_ts)
    return func.date_trunc(_bucket_trunc_unit(range_name), local_ts)


def _format_sql_bucket_timestamp(value: Any, *, timezone: ZoneInfo) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        local = value
        if local.tzinfo is None:
            local = local.replace(tzinfo=timezone)
        else:
            local = local.astimezone(timezone)
        # Match Python path: already truncated by SQL date_trunc.
        return local.isoformat()
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    else:
        parsed = parsed.astimezone(timezone)
    return parsed.isoformat()


async def _sql_window_latency(
    *, start: datetime, end: datetime, user_id: str | None
) -> dict[str, Any] | None:
    """Full-window p50/p95 over duration_ms (no row materialization)."""
    db = get_async_agno_postgres_db()
    table = await db._get_table(table_type="traces")
    if table is None:
        return None

    duration = _duration_ms_expr(table)
    where_clause = _trace_window_filters(table, start=start, end=end, user_id=user_id)
    # Only rows with a positive/finite duration contribute to latency KPIs.
    duration_filter = and_(where_clause, duration.isnot(None), duration >= 0)
    stmt = select(
        func.count().label("n"),
        func.percentile_cont(0.5).within_group(duration).label("p50"),
        func.percentile_cont(0.95).within_group(duration).label("p95"),
    ).where(duration_filter)

    async with db.async_session_factory() as session:
        row = (await session.execute(stmt)).mappings().one()

    n = int(row.get("n") or 0)
    if n <= 0:
        return {"n": 0, "p50_duration_ms": None, "p95_duration_ms": None}

    def _round_ms(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return None

    return {
        "n": n,
        "p50_duration_ms": _round_ms(row.get("p50")),
        "p95_duration_ms": _round_ms(row.get("p95")),
    }


async def _sql_series(
    *,
    start: datetime,
    end: datetime,
    user_id: str | None,
    range_name: OverviewRange,
    timezone: ZoneInfo,
) -> list[dict[str, Any]] | None:
    """Bucket runs/failures/latency with SQL (tokens filled later from sample)."""
    db = get_async_agno_postgres_db()
    table = await db._get_table(table_type="traces")
    if table is None:
        return None

    duration = _duration_ms_expr(table)
    where_clause = _trace_window_filters(table, start=start, end=end, user_id=user_id)
    timezone_key = getattr(timezone, "key", None) or str(timezone)
    bucket = _sql_bucket_timestamp_expr(
        table, range_name=range_name, timezone_key=timezone_key
    ).label("bucket")
    error_case = case(
        (func.upper(table.c.status).in_(("ERROR", "FAILED", "FAILURE")), 1),
        else_=0,
    )
    stmt = (
        select(
            bucket,
            func.count().label("runs"),
            func.coalesce(func.sum(error_case), 0).label("failed_runs"),
            func.percentile_cont(0.5).within_group(duration).label("p50"),
            func.percentile_cont(0.95).within_group(duration).label("p95"),
        )
        .where(where_clause)
        .group_by(bucket)
        .order_by(bucket)
    )

    async with db.async_session_factory() as session:
        rows = (await session.execute(stmt)).mappings().all()

    series: list[dict[str, Any]] = []
    for row in rows:
        timestamp = _format_sql_bucket_timestamp(row.get("bucket"), timezone=timezone)
        if not timestamp:
            continue

        def _round_ms(value: Any) -> float | None:
            if value is None:
                return None
            try:
                return round(float(value), 2)
            except (TypeError, ValueError):
                return None

        series.append(
            {
                "timestamp": timestamp,
                "bucket_end": _bucket_end(
                    timestamp, range_name=range_name, timezone=timezone
                ),
                "runs": int(row.get("runs") or 0),
                "failed_runs": int(row.get("failed_runs") or 0),
                "p50_duration_ms": _round_ms(row.get("p50")),
                "p95_duration_ms": _round_ms(row.get("p95")),
            }
        )
    return series


async def _sql_distributions(
    *, start: datetime, end: datetime, user_id: str | None
) -> dict[str, list[dict[str, Any]]] | None:
    """Full-window agent/workflow/team counts via SQL GROUP BY."""
    db = get_async_agno_postgres_db()
    table = await db._get_table(table_type="traces")
    if table is None:
        return None

    where_clause = _trace_window_filters(table, start=start, end=end, user_id=user_id)
    result: dict[str, list[dict[str, Any]]] = {}
    async with db.async_session_factory() as session:
        for field in ("agent_id", "workflow_id", "team_id"):
            col = getattr(table.c, field)
            stmt = (
                select(col.label("name"), func.count().label("value"))
                .where(and_(where_clause, col.isnot(None), col != ""))
                .group_by(col)
                .order_by(func.count().desc())
            )
            rows = (await session.execute(stmt)).mappings().all()
            key = field.removesuffix("_id")
            result[key] = [
                {"name": str(row["name"]), "value": int(row["value"] or 0)}
                for row in rows
                if row.get("name")
            ]
    return result



async def _safe_sql_window_latency(
    *, start: datetime, end: datetime, user_id: str | None
) -> dict[str, Any] | None:
    try:
        return await _sql_window_latency(start=start, end=end, user_id=user_id)
    except Exception:
        logger.exception("overview SQL latency aggregates failed; using sample path")
        return None


async def _safe_sql_series(
    *,
    start: datetime,
    end: datetime,
    user_id: str | None,
    range_name: OverviewRange,
    timezone: ZoneInfo,
) -> list[dict[str, Any]] | None:
    try:
        return await _sql_series(
            start=start,
            end=end,
            user_id=user_id,
            range_name=range_name,
            timezone=timezone,
        )
    except Exception:
        logger.exception("overview SQL series failed; using sample path")
        return None


async def _safe_sql_distributions(
    *, start: datetime, end: datetime, user_id: str | None
) -> dict[str, list[dict[str, Any]]] | None:
    try:
        return await _sql_distributions(start=start, end=end, user_id=user_id)
    except Exception:
        logger.exception("overview SQL distributions failed; using sample path")
        return None


async def _fetch_traces(
    *, start: datetime, end: datetime, user_id: str | None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load traces for dashboard metrics with a hard row/page cap.

    Full-window scans are unbounded on busy tenants; metrics and series use the
    most recent capped sample. Returns ``(traces, sample_meta)`` where meta has
    ``sample_size``, ``window_total``, and ``truncated``.
    """
    db = get_async_agno_postgres_db()
    traces, total = await db.get_traces(
        start_time=start,
        end_time=end,
        user_id=user_id,
        limit=_PAGE_LIMIT,
        page=1,
    )
    rows = list(traces)
    total_count = int(total or len(rows))
    max_pages = min(
        _MAX_OVERVIEW_TRACE_PAGES,
        max(1, (total_count + _PAGE_LIMIT - 1) // _PAGE_LIMIT),
    )
    for page in range(2, max_pages + 1):
        next_page, _ = await db.get_traces(
            start_time=start,
            end_time=end,
            user_id=user_id,
            limit=_PAGE_LIMIT,
            page=page,
        )
        rows.extend(next_page)
        if len(rows) >= _MAX_OVERVIEW_TRACES:
            rows = rows[:_MAX_OVERVIEW_TRACES]
            break
    truncated = total_count > len(rows)
    if truncated:
        logger.warning(
            "overview truncated traces: loaded {} of {} in window",
            len(rows),
            total_count,
        )
    result: list[dict[str, Any]] = []
    for trace in rows:
        dumped = trace if isinstance(trace, dict) else trace.to_dict()
        result.append(jsonable_encoder(dumped))
    reconciled = await reconcile_trace_statuses(
        result,
        actor_user_id=user_id,
    )
    sample_meta = {
        "sample_size": len(reconciled),
        "window_total": total_count,
        "truncated": truncated,
    }
    return reconciled, sample_meta


async def _snapshots(actor: ActorLike) -> dict[str, Any]:
    """Load cheap scoped inventory values; unavailable features stay omitted."""
    result: dict[str, Any] = {}
    user_id = scope_user_id(actor, None)
    db = get_async_agno_postgres_db()

    if has_scope(actor, "memories:read"):
        try:
            raw = await db.get_user_memories(user_id=user_id, limit=1, page=1)
            result["memories"] = int(raw[1] if isinstance(raw, tuple) else len(raw))
        except Exception:
            logger.exception("overview snapshot failed: memories")

    if has_scope(actor, "approvals:read"):
        try:
            from api.services.approvals_service import get_approval_status_counts

            counts = await get_approval_status_counts(actor=actor)
            result["approvals"] = {
                "pending": counts["pending"],
                "approved": counts["approved"],
                "rejected": counts["rejected"],
            }
        except Exception:
            logger.exception("overview snapshot failed: approvals")

    if has_scope(actor, "knowledge:read"):
        try:
            from api.services.knowledge_service import get_knowledge_base_lifecycle

            knowledge_base = get_knowledge_base_lifecycle()
            _docs, document_count = await knowledge_base.list_documents_page_async(
                owner_user_id=user_id,
                page=1,
                limit=1,
            )
            result["knowledge_documents"] = int(document_count)
        except Exception:
            logger.exception("overview snapshot failed: knowledge_documents")

    if has_scope(actor, "evals:read"):
        try:
            from api.services.agent_eval_result_service import list_agno_eval_runs

            # Cheap dashboard signal: total from meta; pass/fail from a small
            # recent sample (not a full-history scan).
            evaluation_runs = await list_agno_eval_runs(limit=20, page=1)
            items = evaluation_runs.get("data") or []
            meta = evaluation_runs.get("meta") or {}
            passed = sum(item.get("passed") is True for item in items)
            failed = sum(item.get("passed") is False for item in items)
            completed = passed + failed
            result["evaluation"] = {
                "total": int(meta.get("total_count") or len(items)),
                "passed": passed,
                "failed": failed,
                "pass_rate": round(passed / completed, 4) if completed else 0.0,
                "sample_size": len(items),
            }
        except Exception:
            logger.exception("overview snapshot failed: evaluation")
    return result


async def _audit_summary() -> dict[str, Any] | None:
    try:
        from api.services.audit_service import list_audit_events_async

        events, _ = await list_audit_events_async(page=1, limit=10)
    except Exception:
        logger.exception("overview snapshot failed: audit_summary")
        return None
    action_counts = Counter(str(event.get("action") or "") for event in events)
    return {
        "recent": events,
        "top_actions": [
            {"name": action, "value": count}
            for action, count in action_counts.most_common()
            if action
        ],
    }


async def get_runtime_overview(
    actor: ActorLike,
    *,
    range_name: OverviewQueryRange = "24h",
    start_time: str | datetime | None = None,
    end_time: str | datetime | None = None,
    timezone: str = "UTC",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a permission-scoped, trace-backed runtime overview."""
    if range_name not in {*_RANGE_WINDOWS, "custom"}:
        raise ValueError("range must be one of: 1h, 24h, 7d, custom")
    try:
        display_timezone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc

    custom_range = _custom_range(start_time, end_time)
    if range_name == "custom" and custom_range is None:
        raise ValueError("start_time and end_time are required when range is custom")
    if range_name != "custom" and custom_range is not None:
        raise ValueError("start_time and end_time can only be used when range is custom")

    generated_at = now or datetime.now(UTC)
    generated_at = generated_at.replace(tzinfo=UTC) if generated_at.tzinfo is None else generated_at.astimezone(UTC)
    if range_name == "custom":
        # The validation above guarantees the custom bounds are present.
        assert custom_range is not None
        start, end = custom_range
    else:
        start, end = generated_at - _RANGE_WINDOWS[range_name], generated_at
    bucket_range = _bucket_range(start, end)
    owner_user_id = scope_user_id(actor, None)
    gathered = await asyncio.gather(
        _fetch_traces(start=start, end=end, user_id=owner_user_id),
        _count_traces(start=start, end=end, user_id=owner_user_id, status="ERROR"),
        _fetch_recent_failures(start=start, end=end, user_id=owner_user_id, limit=10),
        _snapshots(actor),
        _safe_sql_window_latency(start=start, end=end, user_id=owner_user_id),
        _safe_sql_series(
            start=start,
            end=end,
            user_id=owner_user_id,
            range_name=bucket_range,
            timezone=display_timezone,
        ),
        _safe_sql_distributions(start=start, end=end, user_id=owner_user_id),
    )
    traces_bundle = gathered[0]
    if not isinstance(traces_bundle, tuple) or len(traces_bundle) != 2:
        raise RuntimeError("overview _fetch_traces returned unexpected shape")
    traces = list(traces_bundle[0])  # type: ignore[arg-type]
    trace_sample = dict(traces_bundle[1])  # type: ignore[arg-type]
    failed_raw = gathered[1]
    window_failed_total = int(failed_raw) if isinstance(failed_raw, int | float) else 0
    recent_error_traces: list[dict[str, Any]] = (
        list(gathered[2]) if isinstance(gathered[2], list) else []  # type: ignore[arg-type]
    )
    snapshots: dict[str, Any] = dict(gathered[3]) if isinstance(gathered[3], dict) else {}  # type: ignore[arg-type]
    sql_latency: dict[str, Any] | None = (
        dict(gathered[4]) if isinstance(gathered[4], dict) else None  # type: ignore[arg-type]
    )
    sql_series: list[dict[str, Any]] | None = (
        list(gathered[5]) if isinstance(gathered[5], list) else None  # type: ignore[arg-type]
    )
    sql_distributions: dict[str, list[dict[str, Any]]] | None = (
        dict(gathered[6]) if isinstance(gathered[6], dict) else None  # type: ignore[arg-type]
    )
    span_token_counts = await _fetch_span_token_counts(
        [str(trace.get("trace_id") or trace.get("id") or "") for trace in traces if trace.get("trace_id") or trace.get("id")]
    )

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    durations: list[float] = []
    failed_runs = 0
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    sample_tokens_by_bucket: dict[str, dict[str, int]] = defaultdict(
        lambda: {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    )
    for trace in traces:
        timestamp = _as_datetime(trace.get("start_time"))
        bucket_key: str | None = None
        if timestamp is not None:
            bucket_key = _bucket_timestamp(
                timestamp, range_name=bucket_range, timezone=display_timezone
            )
            buckets[bucket_key].append(trace)
        duration = _duration_ms(trace)
        if duration is not None:
            durations.append(duration)
        failed_runs += int(_is_failure(trace))
        trace_id = str(trace.get("trace_id") or trace.get("id") or "")
        # Span usage is the authoritative source; retain trace-level parsing
        # only for older/external traces that have no token-bearing spans.
        tokens = span_token_counts.get(trace_id) or _token_counts(trace)
        input_tokens += tokens["input_tokens"]
        output_tokens += tokens["output_tokens"]
        total_tokens += tokens["total_tokens"]
        if bucket_key is not None:
            sample_tokens_by_bucket[bucket_key] = _add_token_counts(
                sample_tokens_by_bucket[bucket_key],
                tokens,
            )

    if sql_series is not None:
        series: list[dict[str, Any]] = []
        for item in sql_series:
            bucket_tokens = sample_tokens_by_bucket.get(
                item["timestamp"],
                {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            )
            series.append(
                {
                    **item,
                    **bucket_tokens,
                    # Kept for existing consumers; new clients should use total_tokens.
                    "tokens": bucket_tokens["total_tokens"],
                }
            )
    else:
        series = []
        for timestamp in sorted(buckets):
            bucket = buckets[timestamp]
            bucket_durations = [
                duration for trace in bucket if (duration := _duration_ms(trace)) is not None
            ]
            bucket_tokens = sample_tokens_by_bucket.get(
                timestamp,
                {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            )
            series.append(
                {
                    "timestamp": timestamp,
                    "bucket_end": _bucket_end(
                        timestamp, range_name=bucket_range, timezone=display_timezone
                    ),
                    "runs": len(bucket),
                    "failed_runs": sum(_is_failure(trace) for trace in bucket),
                    "p50_duration_ms": _percentile(bucket_durations, 0.5),
                    "p95_duration_ms": _percentile(bucket_durations, 0.95),
                    **bucket_tokens,
                    "tokens": bucket_tokens["total_tokens"],
                }
            )

    if sql_latency is not None:
        p50_duration_ms = sql_latency.get("p50_duration_ms")
        p95_duration_ms = sql_latency.get("p95_duration_ms")
    else:
        p50_duration_ms = _percentile(durations, 0.5)
        p95_duration_ms = _percentile(durations, 0.95)

    distributions = sql_distributions or {
        "agent": _distribution(traces, "agent_id"),
        "workflow": _distribution(traces, "workflow_id"),
        "team": _distribution(traces, "team_id"),
    }

    response: dict[str, Any] = {
        "generated_at": generated_at.isoformat(),
        "range": range_name,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "health": {"status": "ready"},
        "metrics": {
            # Counts + latency prefer full-window SQL/Agno totals; tokens remain
            # sample-based (span attributes) with truncated sample_size when capped.
            "total_runs": int(trace_sample.get("window_total") or len(traces)),
            "failed_runs": int(window_failed_total),
            "failure_rate": (
                round(int(window_failed_total) / int(trace_sample.get("window_total") or 0), 4)
                if int(trace_sample.get("window_total") or 0)
                else 0.0
            ),
            "p50_duration_ms": p50_duration_ms,
            "p95_duration_ms": p95_duration_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "sample_size": int(trace_sample.get("sample_size") or len(traces)),
            "window_total": int(trace_sample.get("window_total") or len(traces)),
            "truncated": bool(trace_sample.get("truncated")),
            "sample_failed_runs": failed_runs,
        },
        "series": series,
        "distributions": distributions,
        "recent_failures": [_recent_failure(trace) for trace in recent_error_traces],
        "snapshots": snapshots,
    }
    if has_scope(actor, "audit:read"):
        audit = await _audit_summary()
        if audit is not None:
            response["audit"] = audit
    return response
