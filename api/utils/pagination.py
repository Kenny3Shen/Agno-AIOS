"""Shared Agno-style list pagination meta helpers."""

from __future__ import annotations

from typing import Any, TypedDict


class PaginationMeta(TypedDict, total=False):
    """Agno-native list ``meta`` fields.

    Required keys are always populated by :func:`pagination_meta`.
    Optional keys (``truncated``, ``unread_count``, domain filters, …) may be
    merged via ``**extra``.
    """

    page: int
    limit: int
    total_pages: int
    total_count: int
    search_time_ms: float
    truncated: bool
    unread_count: int


def pagination_meta(
    *,
    page: int,
    limit: int,
    total_count: int,
    search_time_ms: float = 0.0,
    **extra: Any,
) -> dict[str, Any]:
    """Build ``meta`` for Agno-native ``{data, meta}`` list responses.

    Unknown ``extra`` keys (e.g. ``truncated``) are merged as-is for callers that
    need non-standard list signals without forking the helper.
    """
    safe_page = max(1, int(page or 1))
    safe_limit = max(1, int(limit or 1))
    total = max(0, int(total_count or 0))
    total_pages = (total + safe_limit - 1) // safe_limit if total else 0
    meta: dict[str, Any] = {
        "page": safe_page,
        "limit": safe_limit,
        "total_pages": total_pages,
        "total_count": total,
        "search_time_ms": float(search_time_ms or 0.0),
    }
    for key, value in extra.items():
        if value is not None:
            meta[key] = value
    return meta
