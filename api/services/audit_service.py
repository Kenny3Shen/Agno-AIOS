from __future__ import annotations

from typing import Any, TypedDict

from fastapi import Request
from loguru import logger

from api.auth.actors import actor_id, actor_role
from api.persistence.audit_logs import (
    ensure_audit_logs_table_async,
    insert_audit_log_async,
    list_audit_logs_async,
)


class AuditRequestContext(TypedDict):
    ip_address: str
    user_agent: str


def audit_request_context(request: Request | None) -> AuditRequestContext:
    return {
        "ip_address": request.client.host if request and request.client else "",
        "user_agent": request.headers.get("user-agent", "") if request else "",
    }


async def ensure_audit_log_table_async() -> None:
    await ensure_audit_logs_table_async()


async def record_audit_event_async(
    actor: Any,
    *,
    action: str,
    resource_type: str,
    resource_id: str = "",
    status: str = "success",
    metadata: dict[str, Any] | None = None,
    ip_address: str = "",
    user_agent: str = "",
) -> None:
    try:
        await insert_audit_log_async(
            actor_user_id=actor_id(actor),
            actor_email=str(getattr(actor, "email", "") or ""),
            actor_role=actor_role(actor),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=metadata or {},
        )
    except Exception as exc:
        logger.warning("审计日志写入失败: {}", exc)


async def list_audit_events_async(
    *,
    page: int = 1,
    limit: int = 50,
    actor_user_id: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    status: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    return await list_audit_logs_async(
        page=page,
        limit=limit,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        status=status,
    )
