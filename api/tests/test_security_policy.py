from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from starlette.requests import Request
from api.services import security_policy
import pytest


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


def test_control_module_access_uses_declared_permission_map():
    security_policy.require_control_module_access("sessions", actor("u1"))
    with pytest.raises(HTTPException) as exc:
        security_policy.require_control_module_access("studio", actor("guest", "guest"))
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        security_policy.require_control_module_access("unknown", actor("u1"))
    assert exc.value.status_code == 404


def test_scheduler_write_requires_admin_permission():
    with pytest.raises(HTTPException) as exc:
        security_policy.require_scheduler_write(actor("u1"))
    assert exc.value.status_code == 403
    security_policy.require_scheduler_write(actor("admin", "admin"))


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
