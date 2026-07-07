from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from api.services.chat_session_service import get_all_sessions_async
from api.services.os_control_identity import owner_user_id
from api.services.os_control_payloads import OsPayload, OsRecord, compact, iso, metric, now_utc, payload, record


async def get_sessions_payload(actor: Any | None = None) -> OsPayload:
    sessions = await get_all_sessions_async(
        include_archived=True,
        owner_user_id=owner_user_id(actor),
    )
    active_cutoff = now_utc() - timedelta(days=1)
    active_count = 0
    records: list[OsRecord] = []

    for session in sessions[:100]:
        updated_at = session.get("updated_at")
        updated_dt = updated_at if isinstance(updated_at, datetime) else None
        if updated_dt and updated_dt.tzinfo is None:
            updated_dt = updated_dt.replace(tzinfo=UTC)
        if updated_dt and updated_dt >= active_cutoff:
            active_count += 1
        archived = bool(session.get("archived"))
        records.append(
            record(
                record_id=session.get("session_id"),
                title=compact(session.get("preview") or "新对话", 64),
                subtitle=str(session.get("session_id") or ""),
                status="archived" if archived else "active" if updated_dt and updated_dt >= active_cutoff else "idle",
                meta={
                    "created": iso(session.get("created_at")),
                    "archived": archived,
                },
                updated_at=updated_at,
            )
        )

    return payload(
        module="sessions",
        title="Sessions",
        description="Agent 会话库存与上下文历史。",
        metrics=[
            metric("Sessions", len(sessions), "Agno session rows", "blue"),
            metric("Active 24h", active_count, "最近 24 小时更新", "green"),
            metric("Archived", sum(1 for session in sessions if session.get("archived")), "Chat 侧栏软归档", "yellow"),
            metric("Shown", len(records), "当前返回记录", "yellow"),
        ],
        records=records,
    )
