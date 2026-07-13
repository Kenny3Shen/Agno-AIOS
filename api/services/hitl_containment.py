"""The deliberately harmless action used to prove the HITL boundary."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Literal

from agno.approval import approval
from agno.run import RunContext
from agno.tools import tool

from api.services.audit_service import record_audit_event_async


@approval(type="required")
@tool(requires_confirmation=True)
async def simulate_containment(
    target: str,
    action: Literal["isolate", "block"],
    reason: str,
    run_context: RunContext | None = None,
) -> dict[str, str]:
    """Record a simulated asset isolation or block after administrator approval."""
    normalized_target = target.strip()
    normalized_reason = reason.strip()
    if not normalized_target or not normalized_reason:
        raise ValueError("target and reason are required")
    await record_audit_event_async(
        SimpleNamespace(id=getattr(run_context, "user_id", ""), role="user"),
        action="skill.simulated_containment.executed",
        resource_type="simulated_containment",
        resource_id=normalized_target,
        metadata={
            "action": action,
            "reason": normalized_reason,
            "run_id": str(getattr(run_context, "run_id", "") or ""),
            "session_id": str(getattr(run_context, "session_id", "") or ""),
        },
    )
    return {
        "status": "simulated",
        "target": normalized_target,
        "action": action,
        "message": "Approval resolved and simulated containment recorded. No external system was changed.",
    }
