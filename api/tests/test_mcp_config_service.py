import unittest
from unittest.mock import patch

from fastapi import HTTPException

from api.services import mcp_config_service


class McpConfigServiceTest(unittest.TestCase):
    def test_apply_service_toggle_updates_config_and_returns_audit_shape(self):
        stored = {"mcp": {"playbook": True}, "hiagent": []}
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

    def test_add_hiagent_normalizes_entry_and_rejects_duplicate_url(self):
        stored = {"hiagent": []}
        writes: list[dict] = []

        with (
            patch.object(mcp_config_service, "read_mcp_config", return_value=stored),
            patch.object(mcp_config_service, "write_mcp_config", side_effect=writes.append),
        ):
            change = mcp_config_service.add_hiagent_entry(
                name="  SOC Agent ",
                url=" https://agent.example/mcp ",
                description=" external ",
                enabled=False,
            )

        self.assertEqual(
            writes[0]["hiagent"],
            [
                {
                    "name": "SOC Agent",
                    "url": "https://agent.example/mcp",
                    "description": "external",
                    "enabled": False,
                }
            ],
        )
        self.assertEqual(change.resource_id, "https://agent.example/mcp")
        self.assertEqual(change.metadata, {"name": "SOC Agent", "enabled": False})

        with patch.object(mcp_config_service, "read_mcp_config", return_value=writes[0]):
            with self.assertRaises(HTTPException) as exc:
                mcp_config_service.add_hiagent_entry(
                    name="Duplicate",
                    url="https://agent.example/mcp",
                )

        self.assertEqual(exc.exception.status_code, 409)

    def test_apply_mcp_upload_registers_remote_url_and_audit_shape(self):
        stored = {"hiagent": [], "mcp_servers": []}
        writes: list[dict] = []

        with (
            patch.object(mcp_config_service, "read_mcp_config", return_value=stored),
            patch.object(mcp_config_service, "write_mcp_config", side_effect=writes.append),
        ):
            change = mcp_config_service.apply_mcp_upload(
                name="  Remote Agent ",
                url=" https://agent.example/mcp ",
                description=" external ",
                enabled=False,
            )

        self.assertEqual(
            writes[0]["hiagent"],
            [
                {
                    "name": "Remote Agent",
                    "url": "https://agent.example/mcp",
                    "description": "external",
                    "enabled": False,
                }
            ],
        )
        self.assertEqual(
            writes[0]["mcp_servers"],
            [
                {
                    "name": "Remote Agent",
                    "description": "external",
                    "url": "https://agent.example/mcp",
                    "kind": "remote-url",
                    "enabled": False,
                    "manifest": {},
                }
            ],
        )
        self.assertEqual(
            change.response,
            {
                "success": True,
                "name": "Remote Agent",
                "kind": "remote-url",
                "restart_required": True,
            },
        )
        self.assertEqual(change.action, "mcp.upload")
        self.assertEqual(change.resource_type, "mcp")
        self.assertEqual(change.resource_id, "Remote Agent")
        self.assertEqual(
            change.metadata,
            {
                "kind": "remote-url",
                "url": "https://agent.example/mcp",
                "has_manifest": False,
            },
        )

    def test_apply_mcp_upload_normalizes_standard_mcp_manifest(self):
        stored = {"hiagent": [], "mcp_servers": []}
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

        self.assertEqual(writes[0]["hiagent"], [])
        self.assertEqual(
            writes[0]["mcp_servers"],
            [
                {
                    "name": "Filesystem",
                    "description": "",
                    "url": "",
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
            {"kind": "mcp-json", "url": "", "has_manifest": True},
        )

    def test_apply_mcp_upload_rejects_duplicate_url_and_name(self):
        stored = {
            "hiagent": [
                {
                    "name": "Existing Agent",
                    "url": "https://agent.example/mcp",
                    "description": "",
                    "enabled": True,
                }
            ],
            "mcp_servers": [
                {
                    "name": "Existing Server",
                    "description": "",
                    "url": "",
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
                    url="https://agent.example/mcp",
                )
        self.assertEqual(exc.exception.status_code, 409)

        manifest = '{"mcpServers":{"tool":{"command":"python"}}}'
        with patch.object(mcp_config_service, "read_mcp_config", return_value=stored):
            with self.assertRaises(HTTPException) as exc:
                mcp_config_service.apply_mcp_upload(
                    name="Existing Server",
                    manifest=manifest,
                )
        self.assertEqual(exc.exception.status_code, 409)

    def test_update_hiagent_applies_partial_mutation_and_duplicate_guard(self):
        stored = {
            "hiagent": [
                {"name": "A", "url": "https://a.example/mcp", "description": "", "enabled": True},
                {"name": "B", "url": "https://b.example/mcp", "description": "", "enabled": True},
            ]
        }
        writes: list[dict] = []

        with (
            patch.object(mcp_config_service, "read_mcp_config", return_value=stored),
            patch.object(mcp_config_service, "write_mcp_config", side_effect=writes.append),
        ):
            change = mcp_config_service.update_hiagent_entry(
                target_url="https://a.example/mcp",
                url="https://c.example/mcp",
                description="new description",
                enabled=False,
            )

        self.assertEqual(writes[0]["hiagent"][0]["url"], "https://c.example/mcp")
        self.assertEqual(writes[0]["hiagent"][0]["description"], "new description")
        self.assertEqual(writes[0]["hiagent"][0]["enabled"], False)
        self.assertEqual(change.action, "mcp.hiagent_update")
        self.assertEqual(change.resource_id, "https://a.example/mcp")

        with patch.object(mcp_config_service, "read_mcp_config", return_value=stored):
            with self.assertRaises(HTTPException) as exc:
                mcp_config_service.update_hiagent_entry(
                    target_url="https://a.example/mcp",
                    url="https://b.example/mcp",
                )

        self.assertEqual(exc.exception.status_code, 409)

    def test_delete_hiagent_removes_entry_and_reports_not_found(self):
        stored = {
            "hiagent": [
                {"name": "A", "url": "https://a.example/mcp", "description": "", "enabled": True},
                {"name": "B", "url": "https://b.example/mcp", "description": "", "enabled": True},
            ]
        }
        writes: list[dict] = []

        with (
            patch.object(mcp_config_service, "read_mcp_config", return_value=stored),
            patch.object(mcp_config_service, "write_mcp_config", side_effect=writes.append),
        ):
            change = mcp_config_service.delete_hiagent_entry("https://a.example/mcp")

        self.assertEqual(
            [entry["url"] for entry in writes[0]["hiagent"]],
            ["https://b.example/mcp"],
        )
        self.assertEqual(change.action, "mcp.hiagent_delete")
        self.assertEqual(change.resource_id, "https://a.example/mcp")

        with patch.object(mcp_config_service, "read_mcp_config", return_value=writes[0]):
            with self.assertRaises(HTTPException) as exc:
                mcp_config_service.delete_hiagent_entry("https://missing.example/mcp")

        self.assertEqual(exc.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
