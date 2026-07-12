from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from api.auth.claims import ActorLike, has_scope, scope_user_id
from api.services.postgres_store import get_async_agno_postgres_db

OverviewRange = Literal["1h", "24h", "7d"]
OverviewQueryRange = OverviewRange | Literal["custom"]

_RANGE_WINDOWS: dict[OverviewRange, timedelta] = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}
_PAGE_LIMIT = 1_000


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


async def _fetch_traces(
    *, start: datetime, end: datetime, user_id: str | None
) -> list[dict[str, Any]]:
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
    for page in range(2, (total_count + _PAGE_LIMIT - 1) // _PAGE_LIMIT + 1):
        next_page, _ = await db.get_traces(
            start_time=start,
            end_time=end,
            user_id=user_id,
            limit=_PAGE_LIMIT,
            page=page,
        )
        rows.extend(next_page)
    result: list[dict[str, Any]] = []
    for trace in rows:
        dumped = trace if isinstance(trace, dict) else trace.to_dict()
        result.append(jsonable_encoder(dumped))
    return result


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
            pass

    if has_scope(actor, "approvals:read"):
        try:
            result["pending_approvals"] = int(await db.get_pending_approval_count(user_id=user_id))
        except Exception:
            pass

    if has_scope(actor, "knowledge:read"):
        try:
            from api.services.knowledge_service import list_documents_async

            result["knowledge_documents"] = len(await list_documents_async(owner_user_id=user_id))
        except Exception:
            pass

    if has_scope(actor, "evals:read"):
        try:
            from api.services.agent_eval_result_service import list_agno_eval_runs

            evaluation_runs = await list_agno_eval_runs(limit=100, page=1)
            items = evaluation_runs.get("items", [])
            passed = sum(item.get("passed") is True for item in items)
            failed = sum(item.get("passed") is False for item in items)
            completed = passed + failed
            result["evaluation"] = {
                "total": int(evaluation_runs.get("total") or len(items)),
                "passed": passed,
                "failed": failed,
                "pass_rate": round(passed / completed, 4) if completed else 0.0,
            }
        except Exception:
            pass
    return result


async def _audit_summary() -> dict[str, Any] | None:
    try:
        from api.services.audit_service import list_audit_events_async

        events, _ = await list_audit_events_async(page=1, limit=10)
    except Exception:
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
    traces, snapshots = await asyncio.gather(
        _fetch_traces(start=start, end=end, user_id=scope_user_id(actor, None)),
        _snapshots(actor),
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
    for trace in traces:
        timestamp = _as_datetime(trace.get("start_time"))
        if timestamp is not None:
            buckets[_bucket_timestamp(timestamp, range_name=bucket_range, timezone=display_timezone)].append(trace)
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

    series: list[dict[str, Any]] = []
    for timestamp in sorted(buckets):
        bucket = buckets[timestamp]
        bucket_durations = [duration for trace in bucket if (duration := _duration_ms(trace)) is not None]
        bucket_tokens = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        for trace in bucket:
            trace_id = str(trace.get("trace_id") or trace.get("id") or "")
            bucket_tokens = _add_token_counts(
                bucket_tokens,
                span_token_counts.get(trace_id) or _token_counts(trace),
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
                # Kept for existing consumers; new clients should use total_tokens.
                "tokens": bucket_tokens["total_tokens"],
            }
        )

    response: dict[str, Any] = {
        "generated_at": generated_at.isoformat(),
        "range": range_name,
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "health": {"status": "ready"},
        "metrics": {
            "total_runs": len(traces),
            "failed_runs": failed_runs,
            "failure_rate": round(failed_runs / len(traces), 4) if traces else 0.0,
            "p50_duration_ms": _percentile(durations, 0.5),
            "p95_duration_ms": _percentile(durations, 0.95),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        },
        "series": series,
        "distributions": {
            "agent": _distribution(traces, "agent_id"),
            "workflow": _distribution(traces, "workflow_id"),
            "team": _distribution(traces, "team_id"),
        },
        "recent_failures": [
            _recent_failure(trace)
            for trace in sorted(
                (trace for trace in traces if _is_failure(trace)),
                key=lambda item: _as_datetime(item.get("start_time")) or datetime.min.replace(tzinfo=UTC),
                reverse=True,
            )[:10]
        ],
        "snapshots": snapshots,
    }
    if has_scope(actor, "audit:read"):
        audit = await _audit_summary()
        if audit is not None:
            response["audit"] = audit
    return response
