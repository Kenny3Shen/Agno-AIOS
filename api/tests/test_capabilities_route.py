from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.routes import capabilities


def actor(*, scopes: list[str] | None = None) -> Any:
    return SimpleNamespace(
        id="u1",
        email="u1@example.com",
        role="user",
        is_superuser=False,
        scopes=scopes if scopes is not None else ["skill:read", "mcp:read"],
    )


def request() -> MagicMock:
    value = MagicMock()
    value.client = SimpleNamespace(host="127.0.0.1")
    value.headers = {"user-agent": "test"}
    return value


@pytest.mark.asyncio
async def test_list_only_returns_capability_kinds_allowed_by_read_scope() -> None:
    data = [
        {"kind": "skill", "capability_key": "s", "name": "Skill"},
        {"kind": "mcp_server", "capability_key": "1", "name": "MCP"},
    ]
    with (
        patch.object(
            capabilities,
            "list_capabilities_for_actor",
            AsyncMock(return_value=data),
        ),
        patch.object(
            capabilities,
            "has_scope",
            side_effect=lambda _user, scope: scope == "skill:read",
        ),
    ):
        result = await capabilities.list_my_capabilities(
            user=actor(scopes=["skill:read"])
        )

    assert result["data"] == [data[0]]


@pytest.mark.asyncio
async def test_preference_update_never_accepts_another_user_id() -> None:
    updated = {
        "kind": "skill",
        "capability_key": "s",
        "effective_enabled": False,
    }
    setter = AsyncMock(return_value=updated)
    audit = AsyncMock()
    user = actor(scopes=["skill:read"])
    with (
        patch.object(capabilities, "set_preference_for_actor", setter),
        patch.object(capabilities, "record_audit_event_async", audit),
    ):
        result = await capabilities.set_my_capability_preference(
            "skill",
            "s",
            capabilities.CapabilityPreferenceRequest(state="disabled"),
            request(),
            user,
        )

    assert result == updated
    setter.assert_awaited_once_with(
        user,
        kind="skill",
        capability_key="s",
        state="disabled",
    )


@pytest.mark.asyncio
async def test_invisible_or_unknown_capability_returns_404() -> None:
    with patch.object(
        capabilities,
        "set_preference_for_actor",
        AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as exc:
            await capabilities.set_my_capability_preference(
                "mcp_server",
                "9",
                capabilities.CapabilityPreferenceRequest(state="enabled"),
                request(),
                actor(scopes=["mcp:read"]),
            )

    assert exc.value.status_code == 404
