from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
import pytest

from api.services import mcp_config_service


def actor(actor_id: str, role: str = "user", is_superuser: bool = False):
    return SimpleNamespace(id=actor_id, role=role, is_superuser=is_superuser)


@pytest.mark.asyncio
async def test_apply_service_toggle_updates_postgres_row():
    rows = [{"id": 1, "name": "playbook", "server_type": "builtin", "enabled": True}]
    update = AsyncMock()
    with (
        patch.object(mcp_config_service, "get_server_row_by_name", AsyncMock(return_value=rows[0])),
        patch.object(mcp_config_service, "update_server_row", update),
    ):
        change = await mcp_config_service.apply_service_toggle("playbook", False)
    update.assert_awaited_once()
    assert change.response["restart_required"] is True
    assert change.metadata == {"enabled": False}


@pytest.mark.asyncio
async def test_apply_service_toggle_rejects_unknown_service():
    with patch.object(mcp_config_service, "get_server_row_by_name", AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc:
            await mcp_config_service.apply_service_toggle("agent", True)
    assert exc.value.status_code == 400


def test_parse_manifest_supports_stdio_and_http():
    transport, stdio = mcp_config_service.parse_mcp_manifest(
        '{"mcpServers":{"filesystem":{"command":"python","args":["-m","tools"]}}}'
    )
    assert transport == "stdio"
    assert stdio["mcpServers"]["filesystem"]["command"] == "python"

    transport, http = mcp_config_service.parse_mcp_manifest(
        '{"mcpServers":{"remote":{"url":"https://example.invalid/mcp","transport":"streamable-http"}}}'
    )
    assert transport == "streamable-http"
    assert http["mcpServers"]["remote"]["url"] == "https://example.invalid/mcp"


@pytest.mark.parametrize(
    "manifest",
    [
        "",
        '{"source":{"path":"server.py"}}',
        '{"mcpServers":{"bad":{"command":"python","url":"https://example.invalid/mcp"}}}',
    ],
)
def test_parse_manifest_rejects_invalid_shapes(manifest: str):
    with pytest.raises(HTTPException):
        mcp_config_service.parse_mcp_manifest(manifest)


@pytest.mark.asyncio
async def test_apply_upload_inserts_postgres_server():
    inserted = {
        "id": 7,
        "name": "Filesystem",
        "namespace": "filesystem",
    }
    upsert = AsyncMock(return_value=inserted)
    with (
        patch.object(mcp_config_service, "server_name_exists", AsyncMock(return_value=False)),
        patch.object(mcp_config_service, "insert_server_row", upsert),
    ):
        change = await mcp_config_service.apply_mcp_upload(
            name="Filesystem",
            manifest='{"mcpServers":{"filesystem":{"command":"python","env":{"TOKEN":"secret"}}}}',
            visibility="public",
            owner_user_id="u1",
        )
    assert upsert.await_args is not None
    record = upsert.await_args.args[0]
    assert record["config"]["mcpServers"]["filesystem"]["env"] == {"TOKEN": "secret"}
    assert record["owner_user_id"] == "u1"
    assert change.response["namespace"] == "filesystem"


@pytest.mark.asyncio
async def test_apply_upload_rejects_duplicate_name():
    with patch.object(
        mcp_config_service,
        "server_name_exists",
        AsyncMock(return_value=True),
    ):
        with pytest.raises(HTTPException) as exc:
            await mcp_config_service.apply_mcp_upload(
                name="Existing",
                manifest='{"mcpServers":{"tool":{"command":"python"}}}',
            )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_visible_servers_redacts_secrets_and_marks_manage_capability():
    rows = [
        {
            "id": 1,
            "name": "Owned",
            "server_type": "external",
            "visibility": "private",
            "owner_user_id": "u1",
            "config": {"mcpServers": {"owned": {"command": "python", "env": {"TOKEN": "secret"}}}},
        },
        {
            "id": 2,
            "name": "Public",
            "server_type": "external",
            "visibility": "public",
            "owner_user_id": "u2",
            "config": {},
        },
    ]
    with patch.object(mcp_config_service, "list_mcp_servers", AsyncMock(return_value=rows)):
        visible = await mcp_config_service.visible_mcp_servers(actor("u1"))
    assert [item["name"] for item in visible] == ["Owned", "Public"]
    assert visible[0]["manifest"]["mcpServers"]["owned"]["env"]["TOKEN"] == "********"
    assert visible[0]["can_manage"] is True
    assert visible[1]["can_manage"] is False
