import unittest
from unittest.mock import patch

from fastapi import HTTPException

from api.services import mcp_config_service


class McpConfigServiceTest(unittest.TestCase):
    def test_apply_service_toggle_updates_config_and_returns_audit_shape(self):
        stored = {"mcp": {"playbook": True}}
        writes: list[dict] = []

        with (
            patch.object(mcp_config_service, "read_mcp_config", return_value=stored),
            patch.object(mcp_config_service, "write_mcp_config", side_effect=writes.append),
        ):
            change = mcp_config_service.apply_service_toggle("playbook", False)

        self.assertEqual(writes[0]["mcp"]["playbook"], False)
        self.assertEqual(
            change.response,
            {"success": True, "control_mode": "integrated", "restart_required": True},
        )
        self.assertEqual(change.action, "mcp.config_update")
        self.assertEqual(change.resource_type, "mcp_service")
        self.assertEqual(change.resource_id, "playbook")
        self.assertEqual(change.metadata, {"enabled": False})

    def test_apply_mcp_upload_normalizes_standard_mcp_manifest(self):
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
            patch.object(mcp_config_service, "write_mcp_config", side_effect=writes.append),
        ):
            change = mcp_config_service.apply_mcp_upload(
                name="Filesystem",
                manifest=manifest,
            )

        self.assertEqual(
            writes[0]["mcp_servers"],
            [
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
            ],
        )
        self.assertEqual(change.response["kind"], "mcp-json")
        self.assertEqual(
            change.metadata,
            {"kind": "mcp-json", "has_manifest": True},
        )

    def test_apply_mcp_upload_rejects_empty_manifest_and_duplicate_name(self):
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
            with self.assertRaises(HTTPException) as exc:
                mcp_config_service.apply_mcp_upload(
                    name="New Agent",
                )
        self.assertEqual(exc.exception.status_code, 400)

        manifest = '{"mcpServers":{"tool":{"command":"python"}}}'
        with patch.object(mcp_config_service, "read_mcp_config", return_value=stored):
            with self.assertRaises(HTTPException) as exc:
                mcp_config_service.apply_mcp_upload(
                    name="Existing Server",
                    manifest=manifest,
                )
        self.assertEqual(exc.exception.status_code, 409)

if __name__ == "__main__":
    unittest.main()
