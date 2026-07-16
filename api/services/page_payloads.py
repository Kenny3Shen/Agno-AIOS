from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime


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
