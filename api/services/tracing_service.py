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


def _pagination_meta(*, page: int, limit: int, total_count: int, search_time_ms: float = 0.0) -> dict[str, object]:
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
) -> dict[str, Any]:
    data = [_project_trace_list_item(item) for item in items]
    return {
        "data": data,
        "meta": _pagination_meta(page=page, limit=limit, total_count=total_count),
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


async def _root_inputs_for_trace_ids(trace_ids: list[str]) -> dict[str, str | None]:
    """Best-effort root span input lookup (Agno list does the same)."""
    inputs: dict[str, str | None] = {}
    for trace_id in trace_ids:
        safe_id = str(trace_id or "").strip()
        if not safe_id:
            continue
        try:
            spans = await _trace_db.get_spans(trace_id=safe_id, limit=200)
        except Exception:
            logger.debug("failed to load spans for list input: {}", safe_id)
            inputs[safe_id] = None
            continue
        inputs[safe_id] = _root_input_from_spans(list(spans or []))
    return inputs


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

    if normalized_status is None:
        traces, total_count = await _trace_db.get_traces(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
            team_id=team_id,
            workflow_id=workflow_id,
            start_time=st,
            end_time=et,
            limit=limit,
            page=page,
        )
        items = await reconcile_trace_statuses(
            [jsonable_encoder(trace.to_dict()) for trace in traces],
            actor_user_id=user_id,
        )
        items = await _attach_list_inputs(items)
        return _trace_list_response(
            items,
            page=page,
            limit=limit,
            total_count=int(total_count),
        )

    items = await _all_trace_items(
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        agent_id=agent_id,
        team_id=team_id,
        workflow_id=workflow_id,
        start_time=st,
        end_time=et,
    )
    items = await reconcile_trace_statuses(
        items,
        actor_user_id=user_id,
    )
    filtered = [item for item in items if trace_has_status(item, normalized_status)]
    offset = (page - 1) * limit
    page_items = filtered[offset : offset + limit]
    page_items = await _attach_list_inputs(page_items)
    return _trace_list_response(
        page_items,
        page=page,
        limit=limit,
        total_count=len(filtered),
    )


async def _all_trace_items(
    *,
    run_id: str | None,
    session_id: str | None,
    user_id: str | None,
    agent_id: str | None,
    team_id: str | None,
    workflow_id: str | None,
    start_time: datetime | None,
    end_time: datetime | None,
) -> list[dict[str, Any]]:
    trace_page = 1
    items: list[dict[str, Any]] = []
    while True:
        batch, total_count = await _trace_db.get_traces(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
            team_id=team_id,
            workflow_id=workflow_id,
            start_time=start_time,
            end_time=end_time,
            limit=200,
            page=trace_page,
        )
        items.extend(jsonable_encoder(trace.to_dict()) for trace in batch)
        if len(items) >= total_count or not batch:
            break
        trace_page += 1
    return items


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

    trace_items = await _all_trace_items(
        run_id=run_id,
        session_id=session_id,
        user_id=user_id,
        agent_id=agent_id,
        team_id=team_id,
        workflow_id=workflow_id,
        start_time=st,
        end_time=et,
    )
    trace_items = await reconcile_trace_statuses(
        trace_items,
        actor_user_id=user_id,
    )
    trace_items = [
        item for item in trace_items if trace_has_status(item, normalized_status)
    ]

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in trace_items:
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
    page_sessions = sessions[offset : offset + limit]
    return {
        "data": page_sessions,
        "meta": _pagination_meta(
            page=page,
            limit=limit,
            total_count=len(sessions),
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
            pass
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
