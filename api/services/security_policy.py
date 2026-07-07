from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, status

from api.auth.permissions import has_permission
from api.services.audit_service import audit_request_context, record_audit_event_async

CONTROL_MODULE_PERMISSIONS = {
    "sessions": "session:read:own",
    "memory": "memory:read:own",
    "metrics": "metrics:read:own",
    "evaluation": "agent_eval:read",
    "approvals": "admin:read",
    "scheduler": "admin:read",
    "knowledge": "knowledge:read",
}


@dataclass(frozen=True)
class PolicyAuditEvent:
    action: str
    resource_type: str
    resource_id: str = ""
    status: str = "success"
    metadata: dict[str, Any] | None = None


def require_control_module_access(module: str, actor: Any) -> None:
    try:
        permission = CONTROL_MODULE_PERMISSIONS[module]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unsupported control module: {module}") from exc

    if not has_permission(actor, permission):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")


async def record_policy_event(
    actor: Any,
    event: PolicyAuditEvent,
    request: Request | None,
) -> None:
    await record_audit_event_async(
        actor,
        action=event.action,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        status=event.status,
        metadata=event.metadata,
        **audit_request_context(request),
    )
