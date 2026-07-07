import asyncio
from datetime import datetime
from typing import Any

from agno.tracing import setup_tracing
from fastapi.encoders import jsonable_encoder

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
    # Accept ISO8601 timestamps; allow trailing 'Z'.
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


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

    st = _parse_dt(start_time)
    et = _parse_dt(end_time)

    traces, total_count = await _trace_db.get_traces(
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        agent_id=agent_id,
        team_id=team_id,
        workflow_id=workflow_id,
        status=status,
        start_time=st,
        end_time=et,
        limit=limit,
        page=page,
    )

    items = [jsonable_encoder(t.to_dict()) for t in traces]
    return {"items": items, "total_count": total_count, "page": page, "limit": limit}


def _build_span_tree(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a hierarchical span tree.

    Input spans are dicts with at least: span_id, parent_span_id.
    """
    by_id: dict[str, dict[str, Any]] = {}

    for s in spans:
        span_id = str(s.get("span_id", ""))
        if not span_id:
            continue
        node = {"span": s, "children": []}
        by_id[span_id] = node

    # attach children
    for span_id, node in by_id.items():
        parent_id = node["span"].get("parent_span_id")
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(node)

    # root nodes = parent_span_id is None or missing parent
    roots: list[dict[str, Any]] = []
    for span_id, node in by_id.items():
        parent_id = node["span"].get("parent_span_id")
        if not parent_id or parent_id not in by_id:
            roots.append(node)

    # Sort roots/children by start_time if present.
    def _key(n: dict[str, Any]):
        st = n.get("span", {}).get("start_time")
        return st or ""

    def _sort_rec(nodes: list[dict[str, Any]]):
        nodes.sort(key=_key)
        for n in nodes:
            _sort_rec(n.get("children", []))

    _sort_rec(roots)
    return roots


async def get_trace_detail(trace_id: str, actor: Any | None = None) -> dict[str, Any] | None:
    trace_task = _trace_db.get_trace(trace_id=trace_id)
    spans_task = _trace_db.get_spans(trace_id=trace_id)
    trace, spans = await asyncio.gather(trace_task, spans_task)
    if not trace:
        return None

    trace_dict = jsonable_encoder(trace.to_dict())
    if actor is not None:
        assert_owned_resource(
            actor,
            owner_user_id=str(trace_dict.get("user_id") or ""),
            resource_name="Trace",
        )

    span_dicts = [jsonable_encoder(s.to_dict()) for s in spans]
    for span in span_dicts:
        span["parsed"] = parse_span_display(span)
    tree = _build_span_tree(span_dicts)

    return {
        "trace": trace_dict,
        "spans": span_dicts,
        "tree": tree,
    }
