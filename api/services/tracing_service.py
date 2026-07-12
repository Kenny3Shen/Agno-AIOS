from datetime import UTC, datetime
from typing import Any

from agno.tracing import setup_tracing
from fastapi.encoders import jsonable_encoder
from loguru import logger

from api.auth.ownership import assert_owned_resource
from api.services.postgres_store import get_async_agno_postgres_db
from api.utils.json import JSONDecodeError, dumps, loads

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
            pass

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
    """Return a paginated list of traces.

    Uses Agno `AsyncPostgresDb.get_traces()` convenience API.
    """
    if limit <= 0:
        limit = 20
    if limit > 200:
        limit = 200
    if page <= 0:
        page = 1

    st, et = _validate_trace_time_range(start_time, end_time)
    normalized_status = _normalize_trace_status(status)

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

    items = [jsonable_encoder(t.to_dict()) for t in traces]
    return {"items": items, "total_count": total_count, "page": page, "limit": limit}


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
    """Return trace sessions after applying filters, then paginate sessions.

    ``AsyncPostgresDb.get_traces`` paginates individual trace rows.  Fetching
    every matching row before grouping is deliberate: grouping only a single
    trace page was the cause of sessions silently disappearing from the UI.
    """
    limit = min(max(limit, 1), 200)
    page = max(page, 1)
    st, et = _validate_trace_time_range(start_time, end_time)
    normalized_status = _normalize_trace_status(status)

    trace_page = 1
    traces: list[Any] = []
    while True:
        batch, total_count = await _trace_db.get_traces(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
            team_id=team_id,
            workflow_id=workflow_id,
            status=normalized_status,
            start_time=st,
            end_time=et,
            limit=200,
            page=trace_page,
        )
        traces.extend(batch)
        if len(traces) >= total_count or not batch:
            break
        trace_page += 1

    grouped: dict[str, list[dict[str, Any]]] = {}
    for trace in traces:
        item = jsonable_encoder(trace.to_dict())
        session_id = str(item.get("session_id") or "").strip()
        if session_id:
            grouped.setdefault(session_id, []).append(item)

    def trace_time(item: dict[str, Any]) -> str:
        return str(item.get("start_time") or item.get("created_at") or "")

    sessions: list[dict[str, Any]] = []
    for session_id, items in grouped.items():
        latest = max(items, key=trace_time)
        run_ids = {str(item.get("run_id")) for item in items if item.get("run_id")}
        error_count = sum(
            1
            for item in items
            if str(item.get("status") or "").upper() in {"ERROR", "FAILED", "FAILURE"}
        )
        sessions.append(
            {
                "session_id": session_id,
                "name": latest.get("name") or latest.get("agent_id") or session_id,
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
    return {
        "items": sessions[offset : offset + limit],
        "total_count": len(sessions),
        "page": page,
        "limit": limit,
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

    # Agno defaults this call to 1,000 rows. Passing None deliberately asks
    # for the complete trace; expose that contract in the API response.
    spans = await _trace_db.get_spans(trace_id=trace_id, limit=None)
    span_dicts = [jsonable_encoder(s.to_dict()) for s in spans]
    for span in span_dicts:
        span["session_id"] = trace_dict.get("session_id")
        span["run_id"] = trace_dict.get("run_id")
        span["parsed"] = parse_span_display(span)
    tree = _build_span_tree(span_dicts)

    return {
        "trace": trace_dict,
        "spans": span_dicts,
        "tree": tree,
        "spans_complete": True,
        "span_count": len(span_dicts),
    }
