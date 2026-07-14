from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client, FastMCP

from api.mcp.tools import hitl


@pytest.mark.asyncio
async def test_hitl_tool_is_mounted_with_schema_and_executes_with_request_audit():
    server = FastMCP("HITL test server")
    server.mount(hitl.hitl_mcp, namespace="hitl")

    with (
        patch.object(
            hitl,
            "get_http_headers",
            return_value={
                "x-agno-user-id": "user-1",
                "x-agno-session-id": "session-1",
                "x-agno-run-id": "run-1",
            },
        ),
        patch.object(hitl, "record_audit_event_async", new=AsyncMock()) as audit,
    ):
        async with Client(server) as client:
            tools = await client.list_tools()
            tool = next(item for item in tools if item.name == "hitl_simulate_containment")
            result = await client.call_tool(
                "hitl_simulate_containment",
                {
                    "target": "10.0.0.8",
                    "action": "isolate",
                    "reason": "test boundary",
                },
            )

    assert tool.inputSchema["required"] == ["target", "action", "reason"]
    assert tool.inputSchema["properties"]["action"]["enum"] == ["isolate", "block"]
    assert result.data == {
        "status": "simulated",
        "target": "10.0.0.8",
        "action": "isolate",
        "message": "Approval resolved and simulated containment recorded. No external system was changed.",
    }
    audit.assert_awaited_once()
    audit_call = audit.await_args
    assert audit_call is not None
    assert str(audit_call.args[0].id) == "user-1"
    assert audit_call.kwargs == {
        "action": "skill.simulated_containment.executed",
        "resource_type": "simulated_containment",
        "resource_id": "10.0.0.8",
        "metadata": {
            "action": "isolate",
            "reason": "test boundary",
            "run_id": "run-1",
            "session_id": "session-1",
        },
    }


@pytest.mark.asyncio
async def test_hitl_tool_rejects_blank_target_before_writing_audit():
    with patch.object(hitl, "record_audit_event_async", new=AsyncMock()) as audit:
        with pytest.raises(ValueError, match="target and reason are required"):
            await hitl.simulate_containment(" ", "block", "test boundary")
    audit.assert_not_awaited()
