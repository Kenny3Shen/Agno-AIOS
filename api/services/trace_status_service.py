from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from loguru import logger

from api.persistence.audit_logs import failed_chat_run_ids_async


async def reconcile_trace_statuses(
    traces: Iterable[dict[str, Any]],
    *,
    actor_user_id: str | None = None,
) -> list[dict[str, Any]]:
    """Overlay durable chat audit failures onto Trace projections.

    Loads failed run IDs for the page in one ``resource_id IN (...)`` audit
    query (see ``failed_chat_run_ids_async``), not per-run lookups.
    """
    items = [dict(trace) for trace in traces]
    run_ids = {
        str(trace.get("run_id") or "").strip()
        for trace in items
        if str(trace.get("run_id") or "").strip()
    }
    try:
        failed_run_ids = await failed_chat_run_ids_async(
            run_ids,
            actor_user_id=actor_user_id,
        )
    except Exception:
        logger.exception("Unable to reconcile Trace status from audit terminals")
        return items
    for trace in items:
        if str(trace.get("run_id") or "").strip() in failed_run_ids:
            trace["status"] = "ERROR"
    return items


def trace_has_status(trace: dict[str, Any], status: str | None) -> bool:
    return status is None or str(trace.get("status") or "").upper() == status
