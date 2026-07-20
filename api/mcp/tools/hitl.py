"""MCP tools whose execution is gated by Agno administrator approval."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Literal

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token, get_http_headers
from mcp.types import ToolAnnotations

from api.services.audit_service import record_audit_event_async


hitl_mcp = FastMCP("Human In The Loop")


@hitl_mcp.tool(
    title="模拟隔离资产",
    tags={"hitl", "security", "containment"},
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    meta={"category": "hitl", "approval": "required"},
)
async def simulate_containment(
    target: str,
    action: Literal["isolate", "block"],
    reason: str,
) -> dict[str, str]:
    """Record a harmless simulated containment action after approval.

    Args:
        target: Asset identifier to simulate containing.
        action: Simulated containment action.
        reason: Operator justification for the action.
    """
    normalized_target = target.strip()
    normalized_reason = reason.strip()
    if not normalized_target or not normalized_reason:
        raise ValueError("target and reason are required")

    headers = get_http_headers()
    access_token = get_access_token()
    claims = access_token.claims if access_token is not None else {}
    user_id = str(
        (claims or {}).get("sub")
        or (getattr(access_token, "subject", "") if access_token is not None else "")
        or ""
    )
    run_id = headers.get("x-agno-run-id", "")
    session_id = headers.get("x-agno-session-id", "")
    await record_audit_event_async(
        SimpleNamespace(id=user_id, role="user"),
        action="skill.simulated_containment.executed",
        resource_type="simulated_containment",
        resource_id=normalized_target,
        metadata={
            "action": action,
            "reason": normalized_reason,
            "run_id": run_id,
            "session_id": session_id,
        },
    )
    return {
        "status": "simulated",
        "target": normalized_target,
        "action": action,
        "message": "Approval resolved and simulated containment recorded. No external system was changed.",
    }
