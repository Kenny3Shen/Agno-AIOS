from datetime import UTC, datetime
from typing import Any

from agno.tracing import setup_tracing
from agno.os.routers.traces.schemas import format_duration_ms
from fastapi.encoders import jsonable_encoder
from loguru import logger

from api.auth.ownership import assert_owned_resource
from api.services.chat_run_events import approval_rejection_reason
from api.services.postgres_store import coerce_json_value, get_async_agno_postgres_db
from api.services.trace_status_service import reconcile_trace_statuses, trace_has_status
from api.utils.json import JSONDecodeError, dumps, loads
from api.utils.pagination import pagination_meta

# Keep a single DB wrapper instance.
_trace_db = get_async_agno_postgres_db()

INPUT_ATTRIBUTE_KEYS = (
    "input.value",
    "input",
    "openinference.input.value",
    "llm.input_messages",
    "gen_ai.prompt",
    "tool.input",
    "tool.arguments",
    "function.arguments",
)
OUTPUT_ATTRIBUTE_KEYS = (
    "output.value",
    "output",
    "openinference.output.value",
    "llm.output_messages",
    "gen_ai.completion",
    "tool.output",
    "tool.result",
    "function.response",
)

TRACE_STATUSES = frozenset({"OK", "ERROR", "UNSET"})




def _duration_ms_value(value: object) -> int | None:
    """Coerce storage/runtime duration_ms to int for Agno format_duration_ms."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value.strip()))
        except ValueError:
            return None
    return None


def _project_duration(row: dict[str, Any]) -> dict[str, Any]:
    """Project Agno storage ``duration_ms`` to wire ``duration`` (drop ms field).

    DB/engine keep ``duration_ms`` (Agno Trace/Span schema). HTTP responses only
    expose Agno OS-style ``duration`` strings via format_duration_ms.
    """
    projected = dict(row)
    duration_ms = _duration_ms_value(projected.pop("duration_ms", None))
    projected["duration"] = format_duration_ms(duration_ms)
    return projected


def _project_trace_list_item(item: dict[str, Any]) -> dict[str, Any]:
    """Project list item toward Agno TraceSummary wire fields."""
    projected = _project_duration(item)
    projected.setdefault("input", None)
    return projected


def _trace_list_response(
    items: list[dict[str, Any]],
    *,
    page: int,
    limit: int,
    total_count: int,
    truncated: bool | None = None,
    scanned_count: int | None = None,
) -> dict[str, Any]:
    data = [_project_trace_list_item(item) for item in items]
    return {
        "data": data,
        "meta": pagination_meta(
            page=page,
            limit=limit,
            total_count=total_count,
            truncated=truncated if truncated else None,
            scanned_count=scanned_count,
        ),
    }


def _root_input_from_spans(spans: list[Any]) -> str | None:
    root = next((span for span in spans if not getattr(span, "parent_span_id", None)), None)
    if root is None and spans:
        # Fall back to first span if parent linkage is missing.
        root = spans[0]
    if root is None:
        return None

    if isinstance(root, dict):
        attributes = root.get("attributes") if isinstance(root.get("attributes"), dict) else {}
    else:
        attributes = getattr(root, "attributes", None)
        attributes = attributes if isinstance(attributes, dict) else {}
    if not attributes:
        return None

    value = _first_attribute(attributes, INPUT_ATTRIBUTE_KEYS)
    if value is None:
        return None
    parsed = _json_or_text(value)
    if isinstance(parsed, dict):
        for key in ("text", "content", "message", "input"):
            candidate = parsed.get(key)
            if candidate not in (None, ""):
                return str(candidate)
        return dumps(parsed)
    if isinstance(parsed, list):
        return dumps(parsed)
    text_value = str(parsed or "").strip()
    return text_value or None


async def _batch_root_spans_by_trace_ids(trace_ids: list[str]) -> dict[str, list[Any]]:
    """Load preferred root spans for many traces in one spans-table query.

    Prefers ``parent_span_id IS NULL`` rows. Traces without a root still get
    one earliest span so ``_root_input_from_spans`` can fall back.
    """
    safe_ids = [str(trace_id).strip() for trace_id in trace_ids if str(trace_id or "").strip()]
    if not safe_ids:
        return {}

    from sqlalchemy import case, select

    table = await _trace_db._get_table(table_type="spans")
    if table is None:
        return {}

    # DISTINCT ON (trace_id): one row per trace, root first, then earliest start.
    stmt = (
        select(
            table.c.trace_id,
            table.c.parent_span_id,
            table.c.attributes,
            table.c.start_time,
        )
        .where(table.c.trace_id.in_(safe_ids))
        .distinct(table.c.trace_id)
        .order_by(
            table.c.trace_id,
            case((table.c.parent_span_id.is_(None), 0), else_=1),
            table.c.start_time,
        )
    )

    by_trace: dict[str, list[Any]] = {trace_id: [] for trace_id in safe_ids}
    async with _trace_db.async_session_factory() as session:
        result = await session.execute(stmt)
        for row in result.mappings():
            trace_id = str(row["trace_id"])
            attributes = row.get("attributes")
            if not isinstance(attributes, dict):
                attributes = coerce_json_value(attributes)
            if not isinstance(attributes, dict):
                attributes = {}
            by_trace.setdefault(trace_id, []).append(
                {
                    "parent_span_id": row.get("parent_span_id"),
                    "attributes": attributes,
                }
            )
    return by_trace


async def _root_inputs_for_trace_ids(trace_ids: list[str]) -> dict[str, str | None]:
    """Best-effort root span input lookup via one batch spans query.

    On batch failure, leave ``input`` as null rather than reintroducing N+1
    ``get_spans`` calls on the list path.
    """
    safe_ids = [str(trace_id).strip() for trace_id in trace_ids if str(trace_id or "").strip()]
    inputs: dict[str, str | None] = {trace_id: None for trace_id in safe_ids}
    if not safe_ids:
        return inputs

    try:
        spans_by_trace = await _batch_root_spans_by_trace_ids(safe_ids)
    except Exception:
        # List path must stay O(1) queries: never fall back to per-trace get_spans.
        logger.exception("batch root span input load failed; leaving list inputs null")
        return inputs

    for trace_id in safe_ids:
        inputs[trace_id] = _root_input_from_spans(spans_by_trace.get(trace_id) or [])
    return inputs



async def _batch_traces_by_run_ids(run_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Load one trace row per run_id in a single traces-table query.

    Prefer the newest ``start_time`` when a run has multiple traces. Returns
    plain dict rows suitable for list projection (no Agno model objects).
    """
    safe_ids = [str(run_id).strip() for run_id in run_ids if str(run_id or "").strip()]
    if not safe_ids:
        return {}

    from sqlalchemy import select

    table = await _trace_db._get_table(table_type="traces")
    if table is None:
        return {}

    # DISTINCT ON (run_id): one row per run, newest start first.
    stmt = (
        select(table)
        .where(table.c.run_id.in_(safe_ids))
        .distinct(table.c.run_id)
        .order_by(table.c.run_id, table.c.start_time.desc())
    )

    by_run: dict[str, dict[str, Any]] = {}
    async with _trace_db.async_session_factory() as session:
        result = await session.execute(stmt)
        for row in result.mappings():
            data = dict(row)
            run_key = str(data.get("run_id") or "").strip()
            if not run_key:
                continue
            by_run[run_key] = data
    return by_run


async def _attach_list_inputs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        return items
    trace_ids = [str(item.get("trace_id") or "") for item in items if item.get("trace_id")]
    inputs = await _root_inputs_for_trace_ids(trace_ids)
    for item in items:
        trace_id = str(item.get("trace_id") or "")
        if "input" not in item or item.get("input") in (None, ""):
            item["input"] = inputs.get(trace_id)
    return items



def setup_agno_tracing() -> None:
    setup_tracing(db=get_async_agno_postgres_db(), batch_processing=False)


def _first_attribute(attributes: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in attributes and attributes[key] not in (None, ""):
            return attributes[key]
    return None


def _json_or_text(value: Any) -> dict[str, Any]:
    if value is None:
        return {"format": "empty", "text": "", "data": None}
    if isinstance(value, dict | list):
        return {
            "format": "json",
            "text": dumps(value, indent=True),
            "data": value,
        }

    text = str(value)
    stripped = text.strip()
    if not stripped:
        return {"format": "empty", "text": "", "data": None}
    if stripped[0:1] in {"{", "["}:
        try:
            data = loads(stripped)
            return {
                "format": "json",
                "text": dumps(data, indent=True),
                "data": data,
            }
        except JSONDecodeError:
            logger.debug("trace payload not JSON; treating as text")

    markdown_markers = ("# ", "## ", "- ", "* ", "```", "|", "> ")
    fmt = "markdown" if any(marker in stripped for marker in markdown_markers) else "text"
    return {"format": fmt, "text": stripped, "data": None}


def _compact_event(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict):
        return {"name": "event", "message": str(event), "attributes": {}}
    attributes = event.get("attributes")
    attrs = attributes if isinstance(attributes, dict) else {}
    message = (
        attrs.get("exception.message")
        or attrs.get("message")
        or event.get("message")
        or event.get("name")
        or ""
    )
    return {
        "name": str(event.get("name") or "event"),
        "message": str(message),
        "attributes": attrs,
    }


def _token_value(attributes: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = attributes.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def parse_span_display(span: dict[str, Any]) -> dict[str, Any]:
    attributes = span.get("attributes")
    attrs = attributes if isinstance(attributes, dict) else {}
    input_value = _first_attribute(attrs, INPUT_ATTRIBUTE_KEYS)
    output_value = _first_attribute(attrs, OUTPUT_ATTRIBUTE_KEYS)
    prompt_tokens = _token_value(
        attrs,
        "gen_ai.usage.prompt_tokens",
        "llm.token_count.prompt",
        "openinference.llm.token_count.prompt",
    )
    completion_tokens = _token_value(
        attrs,
        "gen_ai.usage.completion_tokens",
        "llm.token_count.completion",
        "openinference.llm.token_count.completion",
    )
    total_tokens = _token_value(
        attrs,
        "gen_ai.usage.total_tokens",
        "llm.token_count.total",
        "openinference.llm.token_count.total",
    )
    if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens

    events = span.get("events")
    event_items = events if isinstance(events, list) else []
    return {
        "input": _json_or_text(input_value),
        "output": _json_or_text(output_value),
        "metadata": {
            "model": attrs.get("gen_ai.request.model")
            or attrs.get("llm.model_name")
            or attrs.get("model"),
            "provider": attrs.get("gen_ai.system") or attrs.get("llm.provider"),
            "tool": attrs.get("tool.name") or attrs.get("function.name"),
            "operation": attrs.get("gen_ai.operation.name") or span.get("name"),
            "tokens": {
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": total_tokens,
            },
        },
        "events": [_compact_event(event) for event in event_items],
    }


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    # Accept ISO8601 timestamps; allow trailing 'Z'.  Requiring an explicit
    # offset prevents a server-local timezone from changing query results.
    value = value.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("start_time 和 end_time 必须是 ISO8601 时间") from exc
    if parsed.tzinfo is None:
        raise ValueError("start_time 和 end_time 必须包含时区")
    return parsed.astimezone(UTC)


def _normalize_trace_status(status: str | None) -> str | None:
    if status is None:
        return None
    normalized = status.strip().upper()
    if not normalized:
        return None
    if normalized not in TRACE_STATUSES:
        allowed = ", ".join(sorted(TRACE_STATUSES))
        raise ValueError(f"status 必须是以下值之一: {allowed}")
    return normalized


def _validate_trace_time_range(
    start_time: str | None, end_time: str | None
) -> tuple[datetime | None, datetime | None]:
    start = _parse_dt(start_time)
    end = _parse_dt(end_time)
    if start is not None and end is not None and start > end:
        raise ValueError("start_time 不能晚于 end_time")
    return start, end


async def list_traces(
    *,
    run_id: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    agent_id: str | None = None,
    team_id: str | None = None,
    workflow_id: str | None = None,
    status: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 20,
    page: int = 1,
) -> dict[str, Any]:
    """Return a paginated list of traces (Agno-native data/meta envelope).

    Uses Agno `AsyncPostgresDb.get_traces()` convenience API, then applies
    T.A.I.S status reconciliation. Wire fields project storage ``duration_ms`` to Agno-style ``duration``
    and optional root ``input``; storage schema is unchanged.
    """
    if limit <= 0:
        limit = 20
    if limit > 200:
        limit = 200
    if page <= 0:
        page = 1

    st, et = _validate_trace_time_range(start_time, end_time)
    normalized_status = _normalize_trace_status(status)

    # Agno AsyncPostgresDb.get_traces supports SQL ``status`` (OK/ERROR/UNSET).
    # Prefer native pagination over a post-hoc full-window scan.
    traces, total_count = await _trace_db.get_traces(
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        agent_id=agent_id,
        team_id=team_id,
        workflow_id=workflow_id,
        status=normalized_status,
        start_time=st,
        end_time=et,
        limit=limit,
        page=page,
    )
    items = await reconcile_trace_statuses(
        [jsonable_encoder(trace.to_dict()) for trace in traces],
        actor_user_id=user_id,
    )
    # Audit may flip OK→ERROR after fetch; re-apply the requested status.
    if normalized_status is not None:
        items = [item for item in items if trace_has_status(item, normalized_status)]
    # ERROR filter: also surface chat-audit failures still stored as OK/UNSET.
    if normalized_status == "ERROR":
        items, total_count = await _merge_audit_error_traces(
            items,
            total_count=int(total_count),
            page=page,
            limit=limit,
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
            team_id=team_id,
            workflow_id=workflow_id,
            start_time=st,
            end_time=et,
        )
    items = await _attach_list_inputs(items)
    return _trace_list_response(
        items,
        page=page,
        limit=limit,
        total_count=int(total_count),
    )


# Session grouping still needs a bounded multi-page scan (no native session page
# that includes per-session error counts + latest run). Cap the window.
_STATUS_FILTER_MAX_TRACES = 2_000
_STATUS_FILTER_PAGE_SIZE = 200
_AUDIT_ERROR_SUPPLEMENT_LIMIT = 50


async def _scan_trace_items(
    *,
    run_id: str | None,
    session_id: str | None,
    user_id: str | None,
    agent_id: str | None,
    team_id: str | None,
    workflow_id: str | None,
    start_time: datetime | None,
    end_time: datetime | None,
    status: str | None = None,
    keep_all: bool = False,
) -> tuple[list[dict[str, Any]], int, bool]:
    """Page through get_traces, reconcile each batch, optionally status-filter.

    When ``keep_all`` is True, every reconciled row is kept (used by session
    grouping). When False, only ``status`` matches are retained.
    """
    trace_page = 1
    kept: list[dict[str, Any]] = []
    scanned = 0
    truncated = False
    while True:
        batch, total_count = await _trace_db.get_traces(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
            team_id=team_id,
            workflow_id=workflow_id,
            # Native SQL status when filtering; keep_all session scans leave this None.
            status=None if keep_all else status,
            start_time=start_time,
            end_time=end_time,
            limit=_STATUS_FILTER_PAGE_SIZE,
            page=trace_page,
        )
        if not batch:
            break
        remaining = _STATUS_FILTER_MAX_TRACES - scanned
        if remaining <= 0:
            truncated = True
            break
        if len(batch) > remaining:
            batch = batch[:remaining]
            truncated = True
        raw_items = [jsonable_encoder(trace.to_dict()) for trace in batch]
        scanned += len(raw_items)
        reconciled = await reconcile_trace_statuses(
            raw_items,
            actor_user_id=user_id,
        )
        if status is None or keep_all:
            kept.extend(reconciled)
        else:
            # Status was SQL-prefiltered; reconcile may flip OK→ERROR (and vice versa).
            kept.extend(item for item in reconciled if trace_has_status(item, status))
        if truncated or scanned >= _STATUS_FILTER_MAX_TRACES:
            if int(total_count or 0) > scanned:
                truncated = True
                logger.warning(
                    "trace status filter truncated scan: loaded {} of {}",
                    scanned,
                    total_count,
                )
            break
        if scanned >= int(total_count or 0):
            break
        if len(batch) < _STATUS_FILTER_PAGE_SIZE:
            break
        trace_page += 1
    return kept, scanned, truncated



async def _merge_audit_error_traces(
    items: list[dict[str, Any]],
    *,
    total_count: int,
    page: int,
    limit: int,
    run_id: str | None,
    session_id: str | None,
    user_id: str | None,
    agent_id: str | None,
    team_id: str | None,
    workflow_id: str | None,
    start_time: datetime | None,
    end_time: datetime | None,
) -> tuple[list[dict[str, Any]], int]:
    """Append chat-audit failures that are still OK/UNSET in the traces table.

    Only on the first page (and when the page still has room) so ERROR lists stay
    paginated via Agno while not hiding unrepaired audit failures.
    """
    if page != 1 or len(items) >= limit:
        return items, total_count

    present = {
        str(item.get("run_id") or "").strip()
        for item in items
        if str(item.get("run_id") or "").strip()
    }
    try:
        from api.persistence.audit_logs import recent_failed_chat_run_ids_async

        failed_ids = await recent_failed_chat_run_ids_async(
            limit=_AUDIT_ERROR_SUPPLEMENT_LIMIT,
            actor_user_id=user_id,
        )
    except Exception:
        logger.exception("Unable to load recent failed chat run ids for ERROR filter")
        return items, total_count

    candidates = [
        failed_run_id
        for failed_run_id in failed_ids
        if failed_run_id not in present and (not run_id or failed_run_id == run_id)
    ]
    if not candidates:
        return items, total_count

    # Cap candidates to remaining page slots to keep the batch bounded.
    remaining_slots = max(0, limit - len(items))
    if remaining_slots <= 0:
        return items, total_count
    candidates = candidates[: max(remaining_slots, _AUDIT_ERROR_SUPPLEMENT_LIMIT)]

    try:
        traces_by_run = await _batch_traces_by_run_ids(candidates)
    except Exception:
        logger.exception("Unable to batch-load audit-supplement traces")
        return items, total_count

    extras: list[dict[str, Any]] = []
    for failed_run_id in candidates:
        raw = traces_by_run.get(failed_run_id)
        if not raw:
            continue
        row = jsonable_encoder(raw)
        if session_id and str(row.get("session_id") or "") != session_id:
            continue
        if user_id and str(row.get("user_id") or "") != user_id:
            continue
        if agent_id and str(row.get("agent_id") or "") != agent_id:
            continue
        if team_id and str(row.get("team_id") or "") != team_id:
            continue
        if workflow_id and str(row.get("workflow_id") or "") != workflow_id:
            continue
        raw_start = str(row.get("start_time") or row.get("created_at") or "")
        if (start_time or end_time) and raw_start:
            try:
                ts = datetime.fromisoformat(raw_start.replace("Z", "+00:00"))
                if start_time and ts < start_time:
                    continue
                if end_time and ts > end_time:
                    continue
            except ValueError:
                logger.debug("trace start_time not parseable: {!r}", raw_start)
        row["status"] = "ERROR"
        extras.append(row)
        present.add(failed_run_id)
        if len(items) + len(extras) >= limit:
            break

    if not extras:
        return items, total_count

    merged = items + extras
    merged.sort(
        key=lambda item: str(item.get("start_time") or item.get("created_at") or ""),
        reverse=True,
    )
    merged = merged[:limit]
    return merged, max(int(total_count), len(merged))


async def list_trace_sessions(
    *,
    run_id: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    agent_id: str | None = None,
    team_id: str | None = None,
    workflow_id: str | None = None,
    status: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 20,
    page: int = 1,
) -> dict[str, Any]:
    """Return paginated trace sessions (group-by session_id).

    Prefers SQL aggregation on ``agno_traces`` so large windows do not require
    loading every matching trace into Python. Falls back to the bounded scan
    path when the table is unavailable.
    """
    limit = min(max(limit, 1), 200)
    page = max(page, 1)
    st, et = _validate_trace_time_range(start_time, end_time)
    normalized_status = _normalize_trace_status(status)

    try:
        return await _list_trace_sessions_sql(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
            team_id=team_id,
            workflow_id=workflow_id,
            status=normalized_status,
            start_time=st,
            end_time=et,
            limit=limit,
            page=page,
        )
    except Exception:
        logger.exception("SQL trace session grouping failed; falling back to scan")

    return await _list_trace_sessions_scan(
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        agent_id=agent_id,
        team_id=team_id,
        workflow_id=workflow_id,
        status=normalized_status,
        start_time=st,
        end_time=et,
        limit=limit,
        page=page,
    )


async def _list_trace_sessions_sql(
    *,
    run_id: str | None,
    session_id: str | None,
    user_id: str | None,
    agent_id: str | None,
    team_id: str | None,
    workflow_id: str | None,
    status: str | None,
    start_time: datetime | None,
    end_time: datetime | None,
    limit: int,
    page: int,
) -> dict[str, Any]:
    """Group traces by session_id with SQL aggregates + latest-row projection."""
    from sqlalchemy import and_, case, func, select

    table = await _trace_db._get_table(table_type="traces")
    if table is None:
        raise RuntimeError("traces table unavailable")

    filters = [table.c.session_id.isnot(None), table.c.session_id != ""]
    if run_id:
        filters.append(table.c.run_id == run_id)
    if session_id:
        filters.append(table.c.session_id == session_id)
    if user_id:
        filters.append(table.c.user_id == user_id)
    if agent_id:
        filters.append(table.c.agent_id == agent_id)
    if team_id:
        filters.append(table.c.team_id == team_id)
    if workflow_id:
        filters.append(table.c.workflow_id == workflow_id)
    if status:
        filters.append(func.upper(table.c.status) == status)
    if start_time is not None:
        filters.append(table.c.start_time >= start_time.isoformat())
    if end_time is not None:
        filters.append(table.c.start_time <= end_time.isoformat())
    where_clause = and_(*filters)

    # Aggregates per session (counts only).
    agg_stmt = (
        select(
            table.c.session_id.label("session_id"),
            func.count().label("trace_count"),
            func.count(func.distinct(table.c.run_id)).label("run_count"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            func.upper(table.c.status).in_(("ERROR", "FAILED", "FAILURE")),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("error_count"),
            func.max(table.c.start_time).label("latest_start_time"),
        )
        .where(where_clause)
        .group_by(table.c.session_id)
    )
    agg_subq = agg_stmt.subquery("session_agg")

    count_stmt = select(func.count()).select_from(agg_subq)
    offset = (page - 1) * limit
    page_stmt = (
        select(agg_subq)
        .order_by(agg_subq.c.latest_start_time.desc())
        .limit(limit)
        .offset(offset)
    )

    # Latest trace row per session (DISTINCT ON session_id, newest start_time).
    latest_stmt = (
        select(
            table.c.session_id,
            table.c.trace_id,
            table.c.run_id,
            table.c.name,
            table.c.status,
            table.c.start_time,
            table.c.end_time,
            table.c.user_id,
            table.c.agent_id,
            table.c.team_id,
            table.c.workflow_id,
        )
        .where(where_clause)
        .distinct(table.c.session_id)
        .order_by(table.c.session_id, table.c.start_time.desc())
    )
    latest_subq = latest_stmt.subquery("session_latest")

    async with _trace_db.async_session_factory() as session:
        total_count = int((await session.execute(count_stmt)).scalar_one() or 0)
        agg_rows = [dict(row) for row in (await session.execute(page_stmt)).mappings().all()]
        if not agg_rows:
            return {
                "data": [],
                "meta": pagination_meta(page=page, limit=limit, total_count=total_count),
            }
        page_session_ids = [str(row["session_id"]) for row in agg_rows]
        latest_rows = (
            await session.execute(
                select(latest_subq).where(latest_subq.c.session_id.in_(page_session_ids))
            )
        ).mappings().all()

    latest_by_session = {str(row["session_id"]): dict(row) for row in latest_rows}
    # Overlay audit failures onto latest run_ids for the page.
    latest_items = [
        {
            "run_id": latest_by_session.get(sid, {}).get("run_id"),
            "status": latest_by_session.get(sid, {}).get("status"),
            "session_id": sid,
        }
        for sid in page_session_ids
    ]
    reconciled_latest = await reconcile_trace_statuses(latest_items, actor_user_id=user_id)
    reconciled_status_by_session = {
        str(item.get("session_id") or ""): str(item.get("status") or "UNSET")
        for item in reconciled_latest
    }

    sessions: list[dict[str, Any]] = []
    for row in agg_rows:
        sid = str(row["session_id"])
        latest = latest_by_session.get(sid, {})
        error_count = int(row.get("error_count") or 0)
        latest_status = reconciled_status_by_session.get(sid) or str(latest.get("status") or "UNSET")
        if str(latest_status).upper() in {"ERROR", "FAILED", "FAILURE"} and error_count == 0:
            error_count = 1
        sessions.append(
            {
                "session_id": sid,
                "name": latest.get("name") or latest.get("agent_id") or sid,
                "latest_trace_id": latest.get("trace_id"),
                "latest_run_id": latest.get("run_id"),
                "latest_start_time": latest.get("start_time") or row.get("latest_start_time"),
                "latest_end_time": latest.get("end_time"),
                "trace_count": int(row.get("trace_count") or 0),
                "run_count": int(row.get("run_count") or 0),
                "error_count": error_count,
                "status": "ERROR" if error_count else latest_status,
                "user_id": latest.get("user_id"),
                "agent_id": latest.get("agent_id"),
                "team_id": latest.get("team_id"),
                "workflow_id": latest.get("workflow_id"),
            }
        )

    return {
        "data": sessions,
        "meta": pagination_meta(page=page, limit=limit, total_count=total_count),
    }


async def _list_trace_sessions_scan(
    *,
    run_id: str | None,
    session_id: str | None,
    user_id: str | None,
    agent_id: str | None,
    team_id: str | None,
    workflow_id: str | None,
    status: str | None,
    start_time: datetime | None,
    end_time: datetime | None,
    limit: int,
    page: int,
) -> dict[str, Any]:
    """Legacy bounded scan + Python group (fallback)."""
    trace_items, scanned_count, truncated = await _scan_trace_items(
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        agent_id=agent_id,
        team_id=team_id,
        workflow_id=workflow_id,
        start_time=start_time,
        end_time=end_time,
        status=status,
        keep_all=status is None,
    )
    if status is not None:
        trace_items = [item for item in trace_items if trace_has_status(item, status)]

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in trace_items:
        sid = str(item.get("session_id") or "").strip()
        if sid:
            grouped.setdefault(sid, []).append(item)

    def trace_time(item: dict[str, Any]) -> str:
        return str(item.get("start_time") or item.get("created_at") or "")

    sessions: list[dict[str, Any]] = []
    for sid, items in grouped.items():
        latest = max(items, key=trace_time)
        run_ids = {str(item.get("run_id")) for item in items if item.get("run_id")}
        error_count = sum(
            1
            for item in items
            if str(item.get("status") or "").upper() in {"ERROR", "FAILED", "FAILURE"}
        )
        sessions.append(
            {
                "session_id": sid,
                "name": latest.get("name") or latest.get("agent_id") or sid,
                "latest_trace_id": latest.get("trace_id"),
                "latest_run_id": latest.get("run_id"),
                "latest_start_time": latest.get("start_time"),
                "latest_end_time": latest.get("end_time"),
                "trace_count": len(items),
                "run_count": len(run_ids),
                "error_count": error_count,
                "status": "ERROR" if error_count else str(latest.get("status") or "UNSET"),
                "user_id": latest.get("user_id"),
                "agent_id": latest.get("agent_id"),
                "team_id": latest.get("team_id"),
                "workflow_id": latest.get("workflow_id"),
            }
        )
    sessions.sort(key=lambda item: str(item.get("latest_start_time") or ""), reverse=True)
    offset = (page - 1) * limit
    page_sessions = sessions[offset : offset + limit]
    return {
        "data": page_sessions,
        "meta": pagination_meta(
            page=page,
            limit=limit,
            total_count=len(sessions),
            truncated=truncated if truncated else None,
            scanned_count=scanned_count,
        ),
    }


async def mark_trace_error(run_id: str) -> bool:
    """Best-effort status repair for a trace whose chat run failed."""
    if not run_id:
        return False
    try:
        trace = await _trace_db.get_trace(run_id=run_id)
        if trace is None:
            logger.debug("No trace found to mark failed for run {}", run_id)
            return False
        trace.status = "ERROR"
        await _trace_db.upsert_trace(trace)
        return True
    except Exception:
        logger.exception("Unable to mark trace as ERROR for run {}", run_id)
        return False


_PAUSE_PLACEHOLDER_MARKERS = (
    "i have tools to execute, but i need confirmation",
    "i have tools to execute, but i need user input",
    "i have tools to execute, but it needs external execution",
)
_WAITING_APPROVAL_MARKERS = (
    "等待管理员审批",
    "waiting for admin",
    "awaiting approval",
)


def _text_has_marker(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(marker in lowered for marker in markers)


def _is_pause_placeholder(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return _text_has_marker(stripped, _PAUSE_PLACEHOLDER_MARKERS)


def _is_stale_waiting_content(text: str) -> bool:
    return _is_pause_placeholder(text) or _text_has_marker(text, _WAITING_APPROVAL_MARKERS)


def _format_tool_result(result: object) -> str:
    if isinstance(result, dict):
        return dumps(result, indent=True)
    text_value = str(result).strip()
    if text_value[:1] in {"{", "["}:
        try:
            return dumps(loads(text_value), indent=True)
        except JSONDecodeError:
            logger.debug("tool result not JSON; keeping raw text")
    return text_value


def _project_run_output(run: dict[str, Any]) -> str:
    """Prefer final assistant text, falling back to confirmed/rejected tool outcomes after HITL."""
    content = run.get("content")
    content_text = content.strip() if isinstance(content, str) else ""
    tools_value = run.get("tools")
    tools: list[Any] = tools_value if isinstance(tools_value, list) else []

    confirmed_tools: list[dict[str, Any]] = []
    rejected_tools: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        if tool.get("confirmed") is True and tool.get("result") not in (None, ""):
            confirmed_tools.append(tool)
        elif tool.get("confirmed") is False or tool.get("tool_call_error") is True:
            rejected_tools.append(tool)

    has_admin_reason = "Rejected by administrator" in content_text or "拒绝原因" in content_text
    if rejected_tools and (not content_text or _is_stale_waiting_content(content_text) or not has_admin_reason):
        admin_reason = approval_rejection_reason(run)
        notes = [str(tool.get("confirmation_note") or "").strip() for tool in rejected_tools]
        if admin_reason:
            notes.append(f"Rejected by administrator: {admin_reason}")
        if notes and not has_admin_reason:
            lines = ["## HITL 请求未执行"]
            for tool in rejected_tools:
                name = str(tool.get("tool_name") or "tool")
                note = str(tool.get("confirmation_note") or "").strip()
                if admin_reason and (not note or note == "Tool call was rejected"):
                    note = f"Rejected by administrator: {admin_reason}"
                note = note or "Tool call was rejected"
                args = tool.get("tool_args") if isinstance(tool.get("tool_args"), dict) else {}
                lines.append(f"- **工具**：`{name}`")
                if isinstance(args, dict) and args.get("target"):
                    lines.append(f"- **目标**：`{args.get('target')}`")
                lines.append(f"- **拒绝原因**：{note}")
            lines.append("")
            lines.append("管理员已拒绝该 HITL 请求；工具未执行。")
            return chr(10).join(lines)

    if confirmed_tools and (not content_text or _is_stale_waiting_content(content_text)):
        lines = ["## HITL 工具已执行"]
        for tool in confirmed_tools:
            name = str(tool.get("tool_name") or "tool")
            args = tool.get("tool_args") if isinstance(tool.get("tool_args"), dict) else {}
            result_text = _format_tool_result(tool.get("result"))
            lines.append(f"- **工具**：`{name}`")
            if args:
                lines.append(f"- **参数**：`{dumps(args)}`")
            lines.append("- **结果**：")
            lines.append("```json")
            lines.append(result_text)
            lines.append("```")
        lines.append("")
        lines.append("管理员审批已处理；以上结果来自审批恢复后的工具执行记录。")
        return chr(10).join(lines)

    if content_text:
        return content_text

    messages_value = run.get("messages")
    messages: list[Any] = messages_value if isinstance(messages_value, list) else []
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        if str(message.get("role") or "") != "assistant":
            continue
        text_value = message.get("content")
        if isinstance(text_value, str) and text_value.strip() and not _is_pause_placeholder(text_value):
            return text_value.strip()
    return ""



async def _chat_run_output(session_id: str | None, run_id: str | None) -> str:
    """Return the persisted assistant response for a traced chat run, if any."""
    if not session_id or not run_id:
        return ""
    try:
        session = await _trace_db.get_session(session_id, deserialize=False)
    except Exception:
        logger.exception("Unable to load chat run output for trace run {}", run_id)
        return ""
    if not isinstance(session, dict):
        return ""
    runs = coerce_json_value(session.get("runs"))
    if not isinstance(runs, list):
        return ""
    for run in reversed(runs):
        if not isinstance(run, dict) or str(run.get("run_id") or "") != run_id:
            continue
        return _project_run_output({str(key): value for key, value in run.items()})
    return ""


def _enrich_root_spans(
    spans: list[dict[str, Any]],
    *,
    trace_status: str | None,
    chat_run_output: str,
) -> None:
    """Fill Agent root display fields absent from Agno's OpenTelemetry span."""
    normalized_trace_status = str(trace_status or "").upper()
    for span in spans:
        if span.get("parent_span_id"):
            continue
        if (
            str(span.get("status_code") or "").upper() == "UNSET"
            and normalized_trace_status in {"OK", "ERROR"}
        ):
            span["status_code"] = normalized_trace_status
        parsed = span.get("parsed")
        if not isinstance(parsed, dict) or not chat_run_output:
            continue
        parsed["output"] = _json_or_text(chat_run_output)


def _build_span_tree(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a hierarchical span tree.

    Every valid input span is represented exactly once. Duplicate span IDs,
    self-references, cycles, and references to absent parents are detached as
    roots instead of making the response ambiguous or non-serializable.
    """
    nodes: list[tuple[str, dict[str, Any]]] = []
    canonical: dict[str, dict[str, Any]] = {}
    duplicate_nodes: list[dict[str, Any]] = []
    for span in spans:
        span_id = str(span.get("span_id") or "").strip()
        if not span_id:
            # A span without an identity cannot participate in parent linkage,
            # but remains visible to the caller as a detached item.
            duplicate_nodes.append({"span": span, "children": []})
            continue
        node = {"span": span, "children": []}
        nodes.append((span_id, node))
        if span_id in canonical:
            duplicate_nodes.append(node)
            logger.warning("Duplicate span_id {} in trace response", span_id)
        else:
            canonical[span_id] = node

    parent_for: dict[str, str] = {}
    for span_id, node in canonical.items():
        parent_id = str(node["span"].get("parent_span_id") or "").strip()
        if parent_id and parent_id != span_id and parent_id in canonical:
            parent_for[span_id] = parent_id

    cycle_ids: set[str] = set()
    for span_id in canonical:
        path: list[str] = []
        positions: dict[str, int] = {}
        current = span_id
        while current in parent_for:
            if current in positions:
                cycle_ids.update(path[positions[current] :])
                break
            positions[current] = len(path)
            path.append(current)
            current = parent_for[current]

    roots = list(duplicate_nodes)
    for span_id, node in nodes:
        if canonical[span_id] is not node:
            # Duplicate IDs deliberately stay detached. Linking one of them
            # through the canonical ID would make the parent relationship
            # depend on database row order.
            continue
        parent_id = parent_for.get(span_id)
        if parent_id is None or span_id in cycle_ids:
            roots.append(node)
        else:
            canonical[parent_id]["children"].append(node)

    def node_key(node: dict[str, Any]) -> tuple[str, str]:
        span = node["span"]
        return (str(span.get("start_time") or ""), str(span.get("span_id") or ""))

    # Sort iteratively so an unusually deep (but valid) trace cannot overflow
    # Python's recursion limit while being rendered.
    pending = [roots]
    while pending:
        siblings = pending.pop()
        siblings.sort(key=node_key)
        pending.extend(node["children"] for node in siblings)
    return roots


async def get_trace_detail(trace_id: str, actor: Any | None = None) -> dict[str, Any] | None:
    # Do not query spans until the trace itself has passed ownership checks.
    # Besides avoiding unnecessary work, this prevents access patterns from
    # revealing whether a protected trace has span data.
    trace = await _trace_db.get_trace(trace_id=trace_id)
    if not trace:
        return None

    trace_dict = jsonable_encoder(trace.to_dict())
    if actor is not None:
        assert_owned_resource(
            actor,
            owner_user_id=str(trace_dict.get("user_id") or ""),
            resource_name="Trace",
        )
    trace_dict = (
        await reconcile_trace_statuses(
            [trace_dict],
            actor_user_id=str(trace_dict.get("user_id") or "") or None,
        )
    )[0]
    trace_dict = _project_duration(trace_dict)

    # Agno defaults this call to 1,000 rows. Passing None deliberately asks
    # for the complete trace; expose that contract in the API response.
    spans = await _trace_db.get_spans(trace_id=trace_id, limit=None)
    span_dicts: list[dict[str, Any]] = []
    for raw in spans:
        span = _project_duration(jsonable_encoder(raw.to_dict()))
        span["session_id"] = trace_dict.get("session_id")
        span["run_id"] = trace_dict.get("run_id")
        span["parsed"] = parse_span_display(span)
        span_dicts.append(span)
    chat_run_output = await _chat_run_output(
        str(trace_dict.get("session_id") or "") or None,
        str(trace_dict.get("run_id") or "") or None,
    )
    _enrich_root_spans(
        span_dicts,
        trace_status=trace_dict.get("status"),
        chat_run_output=chat_run_output,
    )
    tree = _build_span_tree(span_dicts)

    return {
        "trace": trace_dict,
        "spans": span_dicts,
        "tree": tree,
        "spans_complete": True,
        "span_count": len(span_dicts),
    }
