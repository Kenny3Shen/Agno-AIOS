from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi.encoders import jsonable_encoder

from api.auth.claims import ActorLike, has_scope, scope_user_id
from api.services.postgres_store import get_async_agno_postgres_db

OverviewRange = Literal["1h", "24h", "7d"]

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


def _token_count(trace: dict[str, Any]) -> int:
    for source in (trace, trace.get("attributes"), trace.get("metadata")):
        if not isinstance(source, dict):
            continue
        for key in (
            "total_tokens",
            "tokens",
            "gen_ai.usage.total_tokens",
            "llm.token_count.total",
        ):
            value = source.get(key)
            if isinstance(value, int | float) and not isinstance(value, bool):
                return max(0, int(value))
            if isinstance(value, dict):
                total = value.get("total")
                if isinstance(total, int | float) and not isinstance(total, bool):
                    return max(0, int(total))
    return 0


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
    range_name: OverviewRange = "24h",
    timezone: str = "UTC",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a permission-scoped, trace-backed runtime overview."""
    if range_name not in _RANGE_WINDOWS:
        raise ValueError("range must be one of: 1h, 24h, 7d")
    try:
        display_timezone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc

    generated_at = now or datetime.now(UTC)
    generated_at = generated_at.replace(tzinfo=UTC) if generated_at.tzinfo is None else generated_at.astimezone(UTC)
    start = generated_at - _RANGE_WINDOWS[range_name]
    traces, snapshots = await asyncio.gather(
        _fetch_traces(start=start, end=generated_at, user_id=scope_user_id(actor, None)),
        _snapshots(actor),
    )

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    durations: list[float] = []
    failed_runs = 0
    total_tokens = 0
    for trace in traces:
        timestamp = _as_datetime(trace.get("start_time"))
        if timestamp is not None:
            buckets[_bucket_timestamp(timestamp, range_name=range_name, timezone=display_timezone)].append(trace)
        duration = _duration_ms(trace)
        if duration is not None:
            durations.append(duration)
        failed_runs += int(_is_failure(trace))
        total_tokens += _token_count(trace)

    series: list[dict[str, Any]] = []
    for timestamp in sorted(buckets):
        bucket = buckets[timestamp]
        bucket_durations = [duration for trace in bucket if (duration := _duration_ms(trace)) is not None]
        series.append(
            {
                "timestamp": timestamp,
                "runs": len(bucket),
                "failed_runs": sum(_is_failure(trace) for trace in bucket),
                "p50_duration_ms": _percentile(bucket_durations, 0.5),
                "p95_duration_ms": _percentile(bucket_durations, 0.95),
                "tokens": sum(_token_count(trace) for trace in bucket),
            }
        )

    response: dict[str, Any] = {
        "generated_at": generated_at.isoformat(),
        "range": range_name,
        "health": {"status": "ready"},
        "metrics": {
            "total_runs": len(traces),
            "failed_runs": failed_runs,
            "failure_rate": round(failed_runs / len(traces), 4) if traces else 0.0,
            "p50_duration_ms": _percentile(durations, 0.5),
            "p95_duration_ms": _percentile(durations, 0.95),
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
