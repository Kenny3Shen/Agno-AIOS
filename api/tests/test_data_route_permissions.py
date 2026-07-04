import inspect
from types import SimpleNamespace
from unittest import TestCase

from api.auth.permissions import has_permission
from api.routes import collect, cve, skills


def user(role: str = "user"):
    return SimpleNamespace(role=role, is_superuser=False)


class DataRoutePermissionsTest(TestCase):
    def test_readonly_security_data_permissions_are_available_to_guest(self):
        guest = user("guest")

        self.assertTrue(has_permission(guest, "cve:read"))
        self.assertFalse(has_permission(guest, "collect:write"))

    def test_user_can_run_collect_but_guest_cannot(self):
        self.assertTrue(has_permission(user("user"), "collect:write"))
        self.assertFalse(has_permission(user("guest"), "collect:write"))

    def test_collect_parse_requires_write_permission(self):
        source = inspect.getsource(collect.parse_url_to_markdown)

        self.assertIn('require_permission("collect:write")', source)
        self.assertIn("record_audit_event", source)
        self.assertIn('action="collect.parse"', source)

    def test_cve_routes_require_read_or_admin_permission(self):
        search_source = inspect.getsource(cve.search_cve)
        update_source = inspect.getsource(cve.update_cve_database)

        self.assertIn('require_permission("cve:read")', search_source)
        self.assertIn('require_permission("admin:read")', update_source)
        self.assertIn("admin.cve.update", update_source)
        self.assertIn('status="failure"', update_source)
        self.assertIn('"error": str(e)', update_source)

    def test_skills_api_registers_real_upload_route(self):
        route_paths = {
            path
            for route in skills.router.routes
            if isinstance(path := getattr(route, "path", None), str)
        }

        self.assertIn("/api/skills/upload", route_paths)
        self.assertNotIn("/api/skills/upload-request", route_paths)
