from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, Request
from fastapi.routing import APIRoute

from api.routes import settings
from api.auth.models import User
from api.services import chat_settings_service


def _route_dependency(endpoint_name: str):
    for route in settings.router.routes:
        if isinstance(route, APIRoute) and getattr(route.endpoint, "__name__", None) == endpoint_name:
            return route.dependant.dependencies[0].call
    raise AssertionError(f"missing route {endpoint_name}")


def test_chat_settings_routes_require_admin_scope() -> None:
    actor = SimpleNamespace(role="user", is_superuser=False)
    for endpoint in ("read_chat_settings", "patch_chat_settings"):
        with pytest.raises(HTTPException) as exc:
            _route_dependency(endpoint)(user=actor)
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_read_chat_settings_returns_persisted_defaults() -> None:
    expected = {
        "show_raw_reasoning": False,
        "show_raw_tool_io": False,
        "show_thought_chain": True,
        "memory_enabled": True,
    }
    with patch.object(settings, "get_chat_settings", new=AsyncMock(return_value=expected)):
        assert await settings.read_chat_settings(_user=cast(User, SimpleNamespace())) == expected


@pytest.mark.asyncio
async def test_patch_chat_settings_updates_only_submitted_values_and_audits() -> None:
    request = Request({"type": "http", "method": "PATCH", "path": "/api/settings/chat", "headers": []})
    expected = {
        "show_raw_reasoning": True,
        "show_raw_tool_io": False,
        "show_thought_chain": True,
        "memory_enabled": True,
    }
    with (
        patch.object(settings, "update_chat_settings", new=AsyncMock(return_value=expected)) as update_mock,
        patch.object(settings, "record_audit_event_async", new=AsyncMock()) as audit_mock,
    ):
        result = await settings.patch_chat_settings(
            request,
            settings.ChatSettingsUpdate(show_raw_reasoning=True),
            user=cast(User, SimpleNamespace(id="admin-1")),
        )
    assert result == expected
    update_mock.assert_awaited_once_with({"show_raw_reasoning": True})
    audit_call = audit_mock.await_args
    assert audit_call is not None
    assert audit_call.kwargs["metadata"] == {"keys": ["show_raw_reasoning"]}


@pytest.mark.asyncio
async def test_chat_settings_service_applies_defaults_for_missing_columns() -> None:
    with patch.object(
        chat_settings_service,
        "get_chat_settings_row",
        new=AsyncMock(return_value={}),
    ):
        result = await chat_settings_service.get_chat_settings()
    assert result == {
        "show_raw_reasoning": False,
        "show_raw_tool_io": False,
        "show_thought_chain": True,
        "memory_enabled": True,
    }
