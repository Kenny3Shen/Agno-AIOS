from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

OsMetric = dict[str, Any]
OsRecord = dict[str, Any]
OsPayload = dict[str, Any]


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso(value: Any) -> str:
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


def compact(value: Any, limit: int = 96) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def metric(label: str, value: Any, hint: str = "", tone: str = "blue") -> OsMetric:
    return {"label": label, "value": value, "hint": hint, "tone": tone}


def record(
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
        "updated_at": iso(updated_at),
    }


def payload(
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
        "generated_at": iso(now_utc()),
    }


def row_dict(raw_row: Any) -> dict[str, Any]:
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
