from unittest.mock import patch

from fastapi import HTTPException
import pytest

from api.services import mcp_config_service


@pytest.mark.asyncio
async def test_apply_service_toggle_updates_config_and_returns_audit_shape():
    stored = {"mcp": {"playbook": True}}
    writes: list[dict] = []
    with (
        patch.object(mcp_config_service, "read_mcp_config_async", return_value=stored),
        patch.object(
            mcp_config_service, "write_mcp_config_async", side_effect=writes.append
        ),
    ):
        change = await mcp_config_service.apply_service_toggle_async("playbook", False)
    assert writes[0]["mcp"]["playbook"] is False
    assert change.response == {
        "success": True,
        "control_mode": "integrated",
        "restart_required": True,
    }
    assert change.action == "mcp.config_update"
    assert change.resource_type == "mcp_service"
    assert change.resource_id == "playbook"
    assert change.metadata == {"enabled": False}


@pytest.mark.asyncio
async def test_apply_service_toggle_rejects_removed_agent_service():
    with pytest.raises(HTTPException) as exc:
        await mcp_config_service.apply_service_toggle_async("agent", True)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_apply_mcp_upload_normalizes_standard_mcp_manifest():
    stored = {"mcp_servers": []}
    writes: list[dict] = []
    manifest = """
        {
          "mcpServers": {
            "filesystem": {
              "command": "python",
              "args": ["-m", "agent_tools"],
              "env": {"TOKEN": "secret"}
            }
          }
        }
        """
    with (
        patch.object(mcp_config_service, "read_mcp_config_async", return_value=stored),
        patch.object(
            mcp_config_service, "write_mcp_config_async", side_effect=writes.append
        ),
    ):
        change = await mcp_config_service.apply_mcp_upload_async(
            name="Filesystem", manifest=manifest
        )
    assert writes[0]["mcp_servers"] == [
        {
            "name": "Filesystem",
            "description": "",
            "kind": "mcp-json",
            "enabled": True,
            "manifest": {
                "mcpServers": {
                    "filesystem": {
                        "command": "python",
                        "args": ["-m", "agent_tools"],
                        "env": {"TOKEN": "secret"},
                    }
                }
            },
        }
    ]
    assert change.response["kind"] == "mcp-json"
    assert change.metadata == {"kind": "mcp-json", "has_manifest": True}


@pytest.mark.asyncio
async def test_apply_mcp_upload_rejects_empty_manifest_and_duplicate_name():
    stored = {
        "mcp_servers": [
            {
                "name": "Existing Server",
                "description": "",
                "kind": "mcp-json",
                "enabled": True,
                "manifest": {"mcpServers": {"existing": {"command": "python"}}},
            }
        ],
    }
    with patch.object(mcp_config_service, "read_mcp_config_async", return_value=stored):
        with pytest.raises(HTTPException) as exc:
            await mcp_config_service.apply_mcp_upload_async(name="New Agent")
    assert exc.value.status_code == 400

    manifest = '{"mcpServers":{"tool":{"command":"python"}}}'
    with patch.object(mcp_config_service, "read_mcp_config_async", return_value=stored):
        with pytest.raises(HTTPException) as exc:
            await mcp_config_service.apply_mcp_upload_async(
                name="Existing Server", manifest=manifest
            )
    assert exc.value.status_code == 409


def test_mcp_config_service_does_not_expose_sync_mutation_facades():
    assert not hasattr(mcp_config_service, "apply_service_toggle")
    assert not hasattr(mcp_config_service, "apply_mcp_upload")
