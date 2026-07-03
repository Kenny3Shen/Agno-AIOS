from types import SimpleNamespace
from unittest import TestCase

from api.auth.permissions import actor_role, has_permission


def user(role: str = "user", is_superuser: bool = False):
    return SimpleNamespace(role=role, is_superuser=is_superuser)


class RbacPermissionsTest(TestCase):
    def test_superuser_is_admin(self):
        self.assertEqual(actor_role(user("guest", is_superuser=True)), "admin")
        self.assertTrue(has_permission(user("guest", is_superuser=True), "trace:read:any"))

    def test_admin_can_read_and_write_all_supported_resources(self):
        actor = user("admin")
        for permission in (
            "session:read:any",
            "session:write:any",
            "trace:read:any",
            "knowledge:write",
            "mcp:write",
            "skill:write",
            "settings:write",
            "audit:read",
        ):
            self.assertTrue(has_permission(actor, permission), permission)

    def test_user_is_own_resource_only_and_not_config_writer(self):
        actor = user("user")
        self.assertTrue(has_permission(actor, "session:read:own"))
        self.assertTrue(has_permission(actor, "session:write:own"))
        self.assertTrue(has_permission(actor, "trace:read:own"))
        self.assertTrue(has_permission(actor, "knowledge:write"))
        self.assertFalse(has_permission(actor, "session:read:any"))
        self.assertFalse(has_permission(actor, "mcp:write"))
        self.assertFalse(has_permission(actor, "settings:write"))

    def test_guest_is_read_only_for_owned_resources(self):
        actor = user("guest")
        self.assertTrue(has_permission(actor, "session:read:own"))
        self.assertTrue(has_permission(actor, "trace:read:own"))
        self.assertTrue(has_permission(actor, "knowledge:read"))
        self.assertFalse(has_permission(actor, "session:write:own"))
        self.assertFalse(has_permission(actor, "knowledge:write"))
