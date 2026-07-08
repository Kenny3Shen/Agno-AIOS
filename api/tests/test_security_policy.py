from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from starlette.requests import Request
from api.services import security_policy
import pytest


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


@pytest.mark.asyncio
async def test_record_policy_event_includes_request_context():
    current_actor = actor("u1")
    request = Request(
        {
            "type": "http",
            "headers": [(b"user-agent", b"policy-browser")],
            "client": ("10.0.0.9", 44321),
        }
    )
    with patch.object(security_policy, "record_audit_event_async", new_callable=AsyncMock) as mocked:
        await security_policy.record_policy_event(
            current_actor,
            security_policy.PolicyAuditEvent(
                action="scheduler.trigger",
                resource_type="schedule",
                resource_id="sched-1",
                metadata={"run_id": "run-1"},
            ),
            request,
        )
    mocked.assert_awaited_once_with(
        current_actor,
        action="scheduler.trigger",
        resource_type="schedule",
        resource_id="sched-1",
        status="success",
        metadata={"run_id": "run-1"},
        ip_address="10.0.0.9",
        user_agent="policy-browser",
    )
