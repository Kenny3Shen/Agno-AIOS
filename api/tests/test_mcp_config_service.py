import json
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
import pytest

from api.mcp import config as mcp_config
from api.services import mcp_config_service


def actor(actor_id: str, role: str = "user", is_superuser: bool = False):
    return SimpleNamespace(id=actor_id, role=role, is_superuser=is_superuser)


def test_apply_service_toggle_updates_config_and_returns_audit_shape():
    stored = {"mcp": {"playbook": True}}
    writes: list[dict] = []
    with (
        patch.object(mcp_config_service, "read_mcp_config", return_value=stored),
        patch.object(
            mcp_config_service, "write_mcp_config", side_effect=writes.append
        ),
    ):
        change = mcp_config_service.apply_service_toggle("playbook", False)
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


def test_apply_service_toggle_rejects_removed_agent_service():
    with pytest.raises(HTTPException) as exc:
        mcp_config_service.apply_service_toggle("agent", True)
    assert exc.value.status_code == 400


def test_apply_mcp_upload_normalizes_standard_mcp_manifest():
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
        patch.object(mcp_config_service, "read_mcp_config", return_value=stored),
        patch.object(
            mcp_config_service, "write_mcp_config", side_effect=writes.append
        ),
    ):
        change = mcp_config_service.apply_mcp_upload(
            name="Filesystem", manifest=manifest
        )
    assert writes[0]["mcp_servers"] == [
        {
            "name": "Filesystem",
            "description": "",
            "kind": "mcp-json",
            "enabled": True,
            "visibility": "private",
            "owner_user_id": "",
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
    assert change.metadata == {
        "kind": "mcp-json",
        "has_manifest": True,
        "visibility": "private",
    }


def test_apply_mcp_upload_persists_visibility_and_owner_metadata():
    stored = {"mcp_servers": []}
    writes: list[dict] = []
    manifest = '{"mcpServers":{"tool":{"command":"python"}}}'
    with (
        patch.object(mcp_config_service, "read_mcp_config", return_value=stored),
        patch.object(
            mcp_config_service, "write_mcp_config", side_effect=writes.append
        ),
    ):
        change = mcp_config_service.apply_mcp_upload(
            name="Tool",
            manifest=manifest,
            visibility="public",
            owner_user_id="u1",
        )

    assert writes[0]["mcp_servers"][0]["visibility"] == "public"
    assert writes[0]["mcp_servers"][0]["owner_user_id"] == "u1"
    assert change.metadata == {
        "kind": "mcp-json",
        "has_manifest": True,
        "visibility": "public",
    }


def test_visible_mcp_servers_marks_manage_capability():
    entries = [
        {
            "name": "Owned",
            "kind": "mcp-json",
            "visibility": "private",
            "owner_user_id": "u1",
            "manifest": {"mcpServers": {"owned": {"command": "python"}}},
        },
        {
            "name": "Foreign",
            "kind": "mcp-json",
            "visibility": "private",
            "owner_user_id": "u2",
            "manifest": {"mcpServers": {"foreign": {"command": "python"}}},
        },
        {
            "name": "Public",
            "kind": "mcp-json",
            "visibility": "public",
            "owner_user_id": "u2",
            "manifest": {"mcpServers": {"public": {"command": "python"}}},
        },
    ]

    visible = mcp_config_service.visible_mcp_servers(entries, actor("u1"))

    assert [item["name"] for item in visible] == ["Owned", "Public"]
    assert visible[0]["can_manage"] is True
    assert visible[1]["can_manage"] is False


def test_apply_mcp_upload_rejects_non_mcp_project_manifest():
    manifest = '{"source":{"path":"server.py"}}'
    with pytest.raises(HTTPException) as exc:
        mcp_config_service.apply_mcp_upload(
            name="FastMCP Project",
            manifest=manifest,
        )
    assert exc.value.status_code == 400
    assert "mcpServers" in str(exc.value.detail)


def test_apply_mcp_upload_rejects_non_standard_mcp_server_shape():
    manifest = """
        {
          "mcpServers": {
            "filesystem": {
              "command": "python",
              "args": ["-m", "agent_tools"],
              "env": {"TOKEN": "secret"},
              "url": "https://example.invalid/mcp"
            }
          }
        }
        """
    with pytest.raises(HTTPException) as exc:
        mcp_config_service.apply_mcp_upload(
            name="Filesystem",
            manifest=manifest,
        )
    assert exc.value.status_code == 400


def test_apply_mcp_upload_accepts_multi_server_manifest():
    stored = {"mcp_servers": []}
    writes: list[dict] = []
    manifest = """
        {
          "mcpServers": {
            "one": {"command": "python"},
            "two": {"command": "node"}
          }
        }
        """
    with (
        patch.object(mcp_config_service, "read_mcp_config", return_value=stored),
        patch.object(
            mcp_config_service, "write_mcp_config", side_effect=writes.append
        ),
    ):
        change = mcp_config_service.apply_mcp_upload(
            name="Multi",
            manifest=manifest,
        )

    assert change.response["kind"] == "mcp-json"
    assert writes[0]["mcp_servers"][0]["manifest"] == {
        "mcpServers": {
            "one": {"command": "python", "args": [], "env": {}},
            "two": {"command": "node", "args": [], "env": {}},
        }
    }


def test_apply_mcp_upload_rejects_empty_manifest_and_duplicate_name():
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
    with patch.object(mcp_config_service, "read_mcp_config", return_value=stored):
        with pytest.raises(HTTPException) as exc:
            mcp_config_service.apply_mcp_upload(name="New Agent")
    assert exc.value.status_code == 400

    manifest = '{"mcpServers":{"tool":{"command":"python"}}}'
    with patch.object(mcp_config_service, "read_mcp_config", return_value=stored):
        with pytest.raises(HTTPException) as exc:
            mcp_config_service.apply_mcp_upload(
                name="Existing Server", manifest=manifest
            )
    assert exc.value.status_code == 409


def test_mcp_config_service_exposes_sync_mutation_functions():
    assert hasattr(mcp_config_service, "apply_service_toggle")
    assert hasattr(mcp_config_service, "apply_mcp_upload")
    assert not hasattr(mcp_config_service, "apply_service_toggle_async")
    assert not hasattr(mcp_config_service, "apply_mcp_upload_async")


def test_mcp_config_file_uses_json_format():
    assert mcp_config.MCP_CONFIG_FILE.name == "mcp_config.json"


def test_mcp_config_read_write_json_and_drops_legacy_protocols(tmp_path, monkeypatch):
    config_file = tmp_path / "mcp_config.json"
    monkeypatch.setattr(mcp_config, "MCP_DATA_DIR", tmp_path)
    monkeypatch.setattr(mcp_config, "MCP_CONFIG_FILE", config_file)

    mcp_config.write_mcp_config(
        {
            "mcp": {"playbook": False, "basic": True, "agent": True},
            "hiagent": [{"name": "legacy"}],
            "mcp_servers": [],
        }
    )

    raw = json.loads(config_file.read_text(encoding="utf-8"))
    assert raw == {
        "mcp": {"playbook": False, "basic": True},
        "mcp_servers": [],
    }

    assert mcp_config.read_mcp_config() == raw


def test_mcp_config_is_json_only_and_ignores_legacy_toml(tmp_path, monkeypatch):
    config_file = tmp_path / "mcp_config.json"
    legacy_file = tmp_path / "mcp_config.toml"
    legacy_file.write_text(
        """
        [mcp]
        playbook = false
        basic = true
        agent = true

        [[hiagent]]
        name = "Legacy"

        [[mcp_servers]]
        name = "Filesystem"
        description = "Local tools"
        kind = "mcp-json"
        enabled = true

        [mcp_servers.manifest.mcpServers.filesystem]
        command = "python"
        args = ["-m", "agent_tools"]
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(mcp_config, "MCP_DATA_DIR", tmp_path)
    monkeypatch.setattr(mcp_config, "MCP_CONFIG_FILE", config_file)

    assert mcp_config.read_mcp_config() == {
        "mcp": {"playbook": True, "basic": True},
        "mcp_servers": [],
    }
    assert not config_file.exists()
