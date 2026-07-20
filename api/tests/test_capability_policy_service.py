from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.services import capability_policy_service as policy


def actor(user_id: str = "u1", role: str = "user") -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        role=role,
        is_superuser=role == "admin",
    )


def skill(*, enabled: bool = True) -> dict:
    return {
        "capability_key": "incident-response",
        "name": "incident-response",
        "description": "Respond to incidents",
        "enabled": enabled,
        "has_scripts": True,
        "visibility": "public",
        "owner_user_id": "admin-1",
    }


@pytest.mark.asyncio
async def test_personal_disabled_override_is_isolated_between_users() -> None:
    async def preferences(user_id: str):
        if user_id == "u1":
            return {("skill", "incident-response"): "disabled"}
        return {}

    with (
        patch.object(policy, "list_skill_infos", return_value=[skill()]),
        patch.object(policy, "list_mcp_servers", AsyncMock(return_value=[])),
        patch.object(
            policy,
            "list_capability_preferences",
            AsyncMock(side_effect=preferences),
        ),
    ):
        user_a = await policy.list_capabilities_for_actor(actor("u1"))
        user_b = await policy.list_capabilities_for_actor(actor("u2"))

    assert user_a[0]["preference"] == "disabled"
    assert user_a[0]["effective_enabled"] is False
    assert user_a[0]["unavailable_reason"] == "user_disabled"
    assert user_b[0]["preference"] == "enabled"
    assert user_b[0]["effective_enabled"] is True


@pytest.mark.asyncio
async def test_explicit_enable_cannot_bypass_platform_disable() -> None:
    with (
        patch.object(
            policy,
            "list_skill_infos",
            return_value=[skill(enabled=False)],
        ),
        patch.object(policy, "list_mcp_servers", AsyncMock(return_value=[])),
        patch.object(
            policy,
            "list_capability_preferences",
            AsyncMock(return_value={("skill", "incident-response"): "enabled"}),
        ),
    ):
        items = await policy.list_capabilities_for_actor(actor())

    assert items[0]["preference"] == "enabled"
    assert items[0]["platform_enabled"] is False
    assert items[0]["effective_enabled"] is False
    assert items[0]["unavailable_reason"] == "platform_disabled"


@pytest.mark.asyncio
async def test_enable_clears_sparse_override_for_current_user_only() -> None:
    disabled_item = {
        "kind": "skill",
        "capability_key": "incident-response",
        "name": "incident-response",
        "description": "",
        "platform_enabled": True,
        "preference": "disabled",
        "effective_enabled": False,
        "unavailable_reason": "user_disabled",
        "visibility": "public",
        "owner_user_id": "",
        "server_id": None,
        "namespace": None,
        "risk": "standard",
    }
    enabled_item = {**disabled_item, "preference": "enabled", "effective_enabled": True, "unavailable_reason": None}
    clear = AsyncMock()
    with (
        patch.object(
            policy,
            "list_capabilities_for_actor",
            AsyncMock(side_effect=[[disabled_item], [enabled_item]]),
        ),
        patch.object(policy, "clear_capability_preference", clear),
    ):
        result = await policy.set_preference_for_actor(
            actor("u1"),
            kind="skill",
            capability_key="incident-response",
            state="enabled",
        )

    assert result == enabled_item
    clear.assert_awaited_once_with(
        user_id="u1",
        capability_type="skill",
        capability_key="incident-response",
    )


@pytest.mark.asyncio
async def test_workflow_preflight_reports_user_disabled_binding() -> None:
    item = {
        "kind": "skill",
        "capability_key": "incident-response",
        "name": "incident-response",
        "description": "",
        "platform_enabled": True,
        "preference": "disabled",
        "effective_enabled": False,
        "unavailable_reason": "user_disabled",
        "visibility": "public",
        "owner_user_id": "",
        "server_id": None,
        "namespace": None,
        "risk": "standard",
    }
    with patch.object(
        policy,
        "list_capabilities_for_actor",
        AsyncMock(return_value=[item]),
    ):
        issues = await policy.required_skill_issues_for_actor(
            actor(), ["incident-response"]
        )

    assert issues == [
        {
            "name": "incident-response",
            "capability_key": "incident-response",
            "reason": "user_disabled",
        }
    ]
