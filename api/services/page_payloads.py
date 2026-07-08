from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TypedDict


class PageMetric(TypedDict):
    label: str
    value: str | int | float
    hint: str
    tone: str


class PageRecord(TypedDict):
    id: str
    title: str
    subtitle: str
    status: str
    meta: Mapping[str, object]
    updated_at: str


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso(value: object) -> str:
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


def compact(value: object, limit: int = 96) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def metric(label: str, value: str | int | float, hint: str = "", tone: str = "blue") -> PageMetric:
    return {"label": label, "value": value, "hint": hint, "tone": tone}


def record(
    *,
    record_id: object,
    title: str,
    subtitle: str = "",
    status: str = "ready",
    meta: Mapping[str, object] | None = None,
    updated_at: object = "",
) -> PageRecord:
    return {
        "id": str(record_id or title),
        "title": title,
        "subtitle": subtitle,
        "status": status,
        "meta": meta or {},
        "updated_at": iso(updated_at),
    }


def row_dict(raw_row: object) -> dict[str, object]:
    if isinstance(raw_row, Mapping):
        return {str(key): value for key, value in raw_row.items()}
    mapping = getattr(raw_row, "_mapping", None)
    if isinstance(mapping, Mapping):
        return {str(key): value for key, value in mapping.items()}
    model_dump = getattr(raw_row, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return {str(key): value for key, value in dumped.items()}
    try:
        return {str(key): value for key, value in vars(raw_row).items()}
    except TypeError:
        return {}
