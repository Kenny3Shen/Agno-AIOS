"""Safe, UI-facing projections for Agno streaming run events."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal


ChatRunEventName = Literal[
    "run.started",
    "run.paused",
    "run.continued",
    "content.delta",
    "tool.update",
    "reasoning.delta",
    "thought.update",
    "sources",
    "run.completed",
    "run.cancelled",
    "run.failed",
    "run.retrying",
]


@dataclass(frozen=True)
class ChatRunEvent:
    event: ChatRunEventName
    data: dict[str, Any]

    def as_sse(self) -> dict[str, Any]:
        return {"event": self.event, "data": self.data}


def event_value(event: Any, name: str, default: Any = None) -> Any:
    if isinstance(event, dict):
        return event.get(name, default)
    return getattr(event, name, default)


def to_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(value, "__dataclass_fields__"):
        dumped = asdict(value)
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _text(value: Any, limit: int = 280) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def source_items(value: Any) -> list[dict[str, str]]:
    """Project citations/references without leaking arbitrary provider payloads."""
    if isinstance(value, dict):
        value = value.get("references") or value.get("sources") or value.get("items")
    if not isinstance(value, list):
        return []

    items: list[dict[str, str]] = []
    for index, raw in enumerate(value):
        item = to_mapping(raw)
        title = _text(item.get("title") or item.get("name") or item.get("source"))
        url = _text(item.get("url") or item.get("uri"), limit=2048)
        snippet = _text(item.get("snippet") or item.get("content") or item.get("description"))
        if not title:
            title = url or f"来源 {index + 1}"
        items.append({"id": _text(item.get("id"), 128) or str(index), "title": title, "url": url, "snippet": snippet})
    return items


def metric_values(value: Any) -> dict[str, int | float]:
    metrics = to_mapping(value)
    result: dict[str, int | float] = {}
    fields = {
        "input_tokens": "input_tokens",
        "output_tokens": "output_tokens",
        "total_tokens": "total_tokens",
        "duration": "duration",
        "total_time": "duration",
    }
    for source, target in fields.items():
        raw = metrics.get(source)
        if target in result or not isinstance(raw, int | float):
            continue
        result[target] = raw
    return result


def approval_rejection_reason(run: object) -> str:
    run_data = to_mapping(run)
    for requirement in run_data.get("requirements", []):
        requirement_data = to_mapping(requirement)
        reason = _rejection_reason_from_note(requirement_data.get("confirmation_note"))
        if reason:
            return reason
        tool_data = to_mapping(requirement_data.get("tool_execution"))
        reason = _rejection_reason_from_note(tool_data.get("confirmation_note"))
        if reason:
            return reason

    for tool in run_data.get("tools", []):
        reason = _rejection_reason_from_note(to_mapping(tool).get("confirmation_note"))
        if reason:
            return reason

    metadata = to_mapping(run_data.get("metadata"))
    approval = to_mapping(metadata.get("approval"))
    resolution = to_mapping(approval.get("resolution_data"))
    # Agno HITL store: only ``note`` (write path no longer dual-writes rejection_reason).
    return _text(resolution.get("note"), limit=2000)


def _rejection_reason_from_note(value: Any) -> str:
    """Return a meaningful administrator reason, excluding Agno's generic fallback."""
    note = _text(value, limit=2000)
    if not note or note == "Tool call was rejected":
        return ""
    prefix = "Rejected by administrator:"
    if note.startswith(prefix):
        return note[len(prefix) :].strip()
    return note


def tool_update(value: Any, status: Literal["running", "completed", "error"], *, include_raw_io: bool = False) -> dict[str, Any]:
    tool = to_mapping(value)
    tool_id = _text(tool.get("tool_call_id") or tool.get("id") or tool.get("call_id"), 128)
    name = _text(tool.get("tool_name") or tool.get("name"), 160)
    result: dict[str, Any] = {"id": tool_id or name or "tool", "name": name or "工具调用", "status": status}
    if include_raw_io:
        raw_input = tool.get("arguments", tool.get("input", tool.get("parameters")))
        raw_output = tool.get("result", tool.get("output", tool.get("content")))
        if raw_input is not None:
            result["input"] = raw_input
        if raw_output is not None:
            result["output"] = raw_output
    return result


def completed_payload(event: Any) -> dict[str, Any]:
    followups = event_value(event, "followups", [])
    content = event_value(event, "content")
    payload: dict[str, Any] = {
        "run_id": _text(event_value(event, "run_id"), 128),
        "session_id": _text(event_value(event, "session_id"), 128),
        "metrics": metric_values(event_value(event, "metrics")),
        "followups": [_text(item, 240) for item in followups if _text(item, 240)] if isinstance(followups, list) else [],
    }
    # Include final content when present so clients can recover empty streams
    # (e.g. Team route respond_directly edge cases / reconnect).
    if isinstance(content, str) and content.strip():
        # Cap to keep SSE payload reasonable for long reports.
        payload["content"] = content.strip()[:200_000]
    return payload


def paused_payload(event: Any) -> dict[str, Any]:
    """Project only the approval identity and tool summary needed by the chat UI."""
    tools = event_value(event, "tools", [])
    approval_id = _text(event_value(event, "approval_id"), 128)
    tool_name = ""
    if isinstance(tools, list):
        for raw_tool in tools:
            tool = to_mapping(raw_tool)
            approval_id = approval_id or _text(tool.get("approval_id"), 128)
            tool_name = tool_name or _text(tool.get("tool_name") or tool.get("name"), 160)
    return {
        "run_id": _text(event_value(event, "run_id"), 128),
        "session_id": _text(event_value(event, "session_id"), 128),
        "approval_id": approval_id,
        "tool_name": tool_name or "需要审批的工具",
    }
