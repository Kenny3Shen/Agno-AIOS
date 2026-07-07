from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from fastapi.routing import APIRoute
from starlette.requests import Request
from api.auth.claims import has_scope
from api.auth import router as auth_router
from api.routes import audit
from api.services import audit_service
import pytest


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


def route_dependency(endpoint_name: str):
    for route in audit.router.routes:
        if isinstance(route, APIRoute) and getattr(route.endpoint, "__name__", "") == endpoint_name:
            return route.dependant.dependencies[0].call
    raise AssertionError(f"missing route for {endpoint_name}")


def test_audit_route_rejects_non_admin_reader():
    with pytest.raises(HTTPException) as exc:
        route_dependency("list_audit_logs")(user=actor("u1"))

    assert exc.value.status_code == 403


def test_non_admin_cannot_read_audit_logs():
    assert not has_scope(actor("u1"), "audit:read")
    assert not has_scope(actor("g1", "guest"), "audit:read")


def test_request_context_helper_extracts_ip_and_user_agent():
    request = Request(
        {
            "type": "http",
            "headers": [(b"user-agent", b"pytest-agent")],
            "client": ("127.0.0.1", 54321),
        }
    )
    context = audit_service.audit_request_context(request)
    assert context == {"ip_address": "127.0.0.1", "user_agent": "pytest-agent"}


@pytest.mark.asyncio
async def test_record_audit_event_delegates_to_async_persistence():
    current_actor = SimpleNamespace(
        id="u1", email="u1@example.test", role="user", is_superuser=False
    )
    with patch.object(audit_service, "insert_audit_log_async", new_callable=AsyncMock) as mocked:
        await audit_service.record_audit_event_async(
            current_actor,
            action="settings.update",
            resource_type="settings",
            resource_id="models",
            metadata={"changed": True},
            ip_address="127.0.0.1",
            user_agent="pytest",
        )
    mocked.assert_awaited_once_with(
        actor_user_id="u1",
        actor_email="u1@example.test",
        actor_role="user",
        action="settings.update",
        resource_type="settings",
        resource_id="models",
        status="success",
        ip_address="127.0.0.1",
        user_agent="pytest",
        metadata={"changed": True},
    )


@pytest.mark.asyncio
async def test_list_audit_events_delegates_to_async_persistence():
    with patch.object(
        audit_service,
        "list_audit_logs_async",
        new_callable=AsyncMock,
    ) as mocked:
        mocked.return_value = ([], 0)
        result = await audit_service.list_audit_events_async(
            page=2,
            limit=25,
            actor_user_id="u1",
            action="auth.login",
            resource_type="auth",
            status="success",
        )
    assert result == ([], 0)
    mocked.assert_awaited_once_with(
        page=2,
        limit=25,
        actor_user_id="u1",
        action="auth.login",
        resource_type="auth",
        status="success",
    )


@pytest.mark.asyncio
async def test_admin_list_audit_logs_delegates_to_service():
    admin = actor("admin", "admin")
    rows = [{"id": 1, "action": "auth.login"}]
    with patch.object(audit, "list_audit_events_async", new_callable=AsyncMock) as mocked:
        mocked.return_value = (rows, 1)
        result = await audit.list_audit_logs(user=admin)
    assert result["items"] == rows
    assert result["total"] == 1
    mocked.assert_awaited_once()


@pytest.mark.asyncio
async def test_route_surfaces_service_failure_as_500():
    admin = actor("admin", "admin")
    with patch.object(
        audit,
        "list_audit_events_async",
        new_callable=AsyncMock,
        side_effect=RuntimeError("db down"),
    ):
        with pytest.raises(HTTPException) as context:
            await audit.list_audit_logs(user=admin)
    assert context.value.status_code == 500


@pytest.mark.asyncio
async def test_logout_records_request_context():
    current_actor = actor("u1")
    request = Request(
        {
            "type": "http",
            "headers": [(b"user-agent", b"audit-browser")],
            "client": ("10.0.0.8", 44321),
        }
    )
    with patch.object(auth_router, "record_audit_event_async", new_callable=AsyncMock) as mocked:
        result = await auth_router.audited_logout(request=request, user=current_actor)
    assert result == {"success": True}
    mocked.assert_awaited_once_with(
        current_actor,
        action="auth.logout",
        resource_type="auth",
        ip_address="10.0.0.8",
        user_agent="audit-browser",
    )
