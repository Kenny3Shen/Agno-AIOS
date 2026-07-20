from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.mcp import server
from api.persistence import mcp as mcp_store


@pytest.fixture
def mounted_rows(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    rows = [
        {"id": 1, "name": "Asset Graph", "namespace": "asset_graph"},
        {"id": 2, "name": "Alerts", "namespace": "alerts"},
    ]
    monkeypatch.setattr(server, "_server_rows", rows)
    return rows


def test_component_namespace_maps_names_and_fastmcp_resource_uris(
    mounted_rows: list[dict],
) -> None:
    assert server._component_namespace("asset_graph_lookup") == (1, "asset_graph")
    assert server._component_namespace("inventory://asset_graph/hosts/1") == (
        1,
        "asset_graph",
    )
    assert server._component_namespace("inventory://asset_graph/hosts/{id}") == (
        1,
        "asset_graph",
    )
    assert server._component_namespace("inventory://unknown/hosts") == (None, None)


def test_token_insert_values_never_persist_the_raw_bearer() -> None:
    values = mcp_store._token_insert_values(
        {
            "name": "user token",
            "token": "raw-secret",
            "owner_user_id": "u1",
            "token_kind": "user",
            "created_at": 1,
            "expires_at": 2,
        }
    )

    assert values["token"] == values["token_hash"]
    assert values["token"] != "raw-secret"


@pytest.mark.asyncio
async def test_middleware_filters_tools_resources_templates_and_prompts(
    mounted_rows: list[dict],
) -> None:
    middleware = server.CapabilityPolicyMiddleware()
    components = [
        SimpleNamespace(name="asset_graph_lookup"),
        SimpleNamespace(name="alerts_send"),
        SimpleNamespace(uri="inventory://asset_graph/hosts"),
        SimpleNamespace(uri_template="inventory://alerts/events/{id}"),
    ]
    with patch.object(
        middleware,
        "_allowed_server_ids",
        AsyncMock(return_value={1}),
    ):
        filtered = await middleware._filter_components(components)

    assert filtered == [components[0], components[2]]


@pytest.mark.asyncio
async def test_rest_component_list_and_direct_call_apply_actor_policy(
    mounted_rows: list[dict],
) -> None:
    actor = SimpleNamespace(id="u1", role="user", is_superuser=False)
    loaders = {
        "list_tools": AsyncMock(
            return_value=[
                SimpleNamespace(
                    name="asset_graph_lookup",
                    title=None,
                    description=None,
                    tags=set(),
                    icons=None,
                    annotations=None,
                    parameters=None,
                    output_schema=None,
                    meta={},
                ),
                SimpleNamespace(
                    name="alerts_send",
                    title=None,
                    description=None,
                    tags=set(),
                    icons=None,
                    annotations=None,
                    parameters=None,
                    output_schema=None,
                    meta={},
                ),
            ]
        ),
        "list_resources": AsyncMock(return_value=[]),
        "list_resource_templates": AsyncMock(return_value=[]),
        "list_prompts": AsyncMock(return_value=[]),
    }
    with (
        patch.object(server, "configure_main_mcp", AsyncMock()),
        patch.object(server.main_mcp, "list_tools", loaders["list_tools"]),
        patch.object(
            server.main_mcp,
            "list_resources",
            loaders["list_resources"],
        ),
        patch.object(
            server.main_mcp,
            "list_resource_templates",
            loaders["list_resource_templates"],
        ),
        patch.object(server.main_mcp, "list_prompts", loaders["list_prompts"]),
        patch.object(server, "component_overrides", AsyncMock(return_value=[])),
        patch.object(
            server,
            "effective_mcp_server_ids_for_actor",
            AsyncMock(return_value={1}),
        ),
    ):
        items = await server.list_components(actor=actor)
        with pytest.raises(PermissionError):
            await server.call_tool("alerts_send", {}, actor=actor)

    assert [item["name"] for item in items] == ["asset_graph_lookup"]


@pytest.mark.asyncio
async def test_user_token_verifier_reloads_current_role_and_owner() -> None:
    user = SimpleNamespace(
        id="ba06964f-15d5-47cc-bb08-b313903b43e8",
        role="admin",
        is_superuser=False,
    )
    with (
        patch.object(server, "delegation_subject", return_value=None),
        patch.object(
            server,
            "find_token",
            AsyncMock(
                return_value={
                    "expires_at": 0,
                    "token_kind": "user",
                    "owner_user_id": str(user.id),
                }
            ),
        ),
        patch.object(
            server,
            "get_active_user_by_id",
            AsyncMock(return_value=user),
        ) as get_user,
    ):
        access = await server.DatabaseTokenVerifier().verify_token("raw-secret")

    assert access is not None
    assert access.subject == str(user.id)
    assert access.claims["role"] == "admin"
    assert access.claims["kind"] == "user"
    get_user.assert_awaited_once_with(str(user.id))


@pytest.mark.asyncio
async def test_service_token_cannot_claim_a_normal_user_identity() -> None:
    with (
        patch.object(server, "delegation_subject", return_value=None),
        patch.object(
            server,
            "find_token",
            AsyncMock(
                return_value={
                    "expires_at": 0,
                    "token_kind": "service",
                    "owner_user_id": None,
                }
            ),
        ),
    ):
        access = await server.DatabaseTokenVerifier().verify_token("service-secret")

    assert access is not None
    assert access.subject is None
    assert access.claims == {"kind": "service"}
