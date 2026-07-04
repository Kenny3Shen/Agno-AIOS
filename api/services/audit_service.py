from __future__ import annotations

from typing import Any, TypedDict

from fastapi import Request
from loguru import logger

from api.persistence.audit_logs import (
    ensure_audit_logs_table,
    insert_audit_log,
    list_audit_logs,
)


class AuditRequestContext(TypedDict):
    ip_address: str
    user_agent: str


def _actor_id(actor: Any) -> str:
    return str(getattr(actor, "id", "") or "")


def _actor_role(actor: Any) -> str:
    if bool(getattr(actor, "is_superuser", False)):
        return "admin"
    role = str(getattr(actor, "role", "user") or "user").lower()
    return role if role in {"admin", "user", "guest"} else "user"


def audit_request_context(request: Request | None) -> AuditRequestContext:
    return {
        "ip_address": request.client.host if request and request.client else "",
        "user_agent": request.headers.get("user-agent", "") if request else "",
    }


def ensure_audit_log_table() -> None:
    ensure_audit_logs_table()


def record_audit_event(
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
        insert_audit_log(
            actor_user_id=_actor_id(actor),
            actor_email=str(getattr(actor, "email", "") or ""),
            actor_role=_actor_role(actor),
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


def list_audit_events(
    *,
    page: int = 1,
    limit: int = 50,
    actor_user_id: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    status: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    return list_audit_logs(
        page=page,
        limit=limit,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        status=status,
    )
