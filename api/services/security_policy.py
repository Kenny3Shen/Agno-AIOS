from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request

from api.services.audit_service import audit_request_context, record_audit_event_async


@dataclass(frozen=True)
class PolicyAuditEvent:
    action: str
    resource_type: str
    resource_id: str = ""
    status: str = "success"
    metadata: dict[str, Any] | None = None


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
