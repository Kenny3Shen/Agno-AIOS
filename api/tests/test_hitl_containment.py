from unittest.mock import AsyncMock, patch

import pytest

from api.services.hitl_containment import simulate_containment


def test_containment_tool_requires_blocking_approval():
    assert simulate_containment.approval_type == "required"
    assert simulate_containment.requires_confirmation is True


@pytest.mark.asyncio
async def test_containment_audits_only_after_tool_execution():
    with patch("api.services.hitl_containment.record_audit_event_async", new=AsyncMock()) as audit:
        result = await simulate_containment.entrypoint("10.0.0.8", "isolate", "test boundary")

    assert result["status"] == "simulated"
    audit.assert_awaited_once()
    assert audit.await_args.kwargs["action"] == "skill.simulated_containment.executed"
