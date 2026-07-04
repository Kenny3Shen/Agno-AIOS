import inspect
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from api.auth.permissions import has_permission
from api.auth import router as auth_router
from api.auth import users as auth_users
from api.routes import audit, cve, knowledge, mcp, settings, skills
from api.services import audit_service


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


class AuditLogPermissionsTest(TestCase):
    def test_audit_route_requires_admin_read_permission(self):
        source = inspect.getsource(audit.list_audit_logs)

        self.assertIn('require_permission("audit:read")', source)

    def test_non_admin_cannot_read_audit_logs(self):
        self.assertFalse(has_permission(actor("u1"), "audit:read"))
        self.assertFalse(has_permission(actor("g1", "guest"), "audit:read"))

    def test_request_context_helper_extracts_ip_and_user_agent(self):
        request = Request(
            {
                "type": "http",
                "headers": [(b"user-agent", b"pytest-agent")],
                "client": ("127.0.0.1", 54321),
            }
        )

        context = audit_service.audit_request_context(request)

        self.assertEqual(
            context,
            {"ip_address": "127.0.0.1", "user_agent": "pytest-agent"},
        )

    def test_mutating_routes_include_request_context_in_audit_logs(self):
        for source in (
            inspect.getsource(auth_router.audited_logout),
            inspect.getsource(auth_users.UserManager.on_after_login),
            inspect.getsource(skills.toggle_skill),
            inspect.getsource(mcp.update_config),
            inspect.getsource(mcp.issue_token),
            inspect.getsource(mcp.remove_token),
            inspect.getsource(knowledge.create_text_document),
            inspect.getsource(knowledge.create_file_document),
            inspect.getsource(knowledge.remove_document),
            inspect.getsource(knowledge.clear_knowledge),
            inspect.getsource(settings.update_models),
            inspect.getsource(settings.test_model_connectivity),
            inspect.getsource(settings.update_settings),
            inspect.getsource(cve.update_cve_database),
        ):
            self.assertIn("audit_request_context(", source)

    def test_record_audit_event_delegates_to_persistence(self):
        current_actor = SimpleNamespace(
            id="u1",
            email="u1@example.test",
            role="user",
            is_superuser=False,
        )

        with patch.object(audit_service, "insert_audit_log") as mocked:
            audit_service.record_audit_event(
                current_actor,
                action="settings.update",
                resource_type="settings",
                resource_id="models",
                metadata={"changed": True},
                ip_address="127.0.0.1",
                user_agent="pytest",
            )

        mocked.assert_called_once_with(
            actor_user_id="u1",
            actor_email="u1@example.test",
            actor_role="user",
            action="settings.update",
            resource_type="settings",
            resource_id="models",
            status="success",
            ip_address="127.0.0.1",
            user_agent="pytest",
            metadata={"changed": True},
        )

    def test_list_audit_events_delegates_to_persistence(self):
        with patch.object(audit_service, "list_audit_logs", return_value=([], 0)) as mocked:
            result = audit_service.list_audit_events(
                page=2,
                limit=25,
                actor_user_id="u1",
                action="auth.login",
                resource_type="auth",
                status="success",
            )

        self.assertEqual(result, ([], 0))
        mocked.assert_called_once_with(
            page=2,
            limit=25,
            actor_user_id="u1",
            action="auth.login",
            resource_type="auth",
            status="success",
        )


class AuditLogRouteTest(IsolatedAsyncioTestCase):
    async def test_admin_list_audit_logs_delegates_to_service(self):
        admin = actor("admin", "admin")
        rows = [{"id": 1, "action": "auth.login"}]

        with patch.object(audit, "list_audit_events", return_value=(rows, 1)) as mocked:
            result = await audit.list_audit_logs(user=admin)

        self.assertEqual(result["items"], rows)
        self.assertEqual(result["total"], 1)
        mocked.assert_called_once()

    async def test_route_surfaces_service_failure_as_500(self):
        admin = actor("admin", "admin")

        with patch.object(audit, "list_audit_events", side_effect=RuntimeError("db down")):
            with self.assertRaises(HTTPException) as context:
                await audit.list_audit_logs(user=admin)

        self.assertEqual(context.exception.status_code, 500)

    async def test_logout_records_request_context(self):
        current_actor = actor("u1")
        request = Request(
            {
                "type": "http",
                "headers": [(b"user-agent", b"audit-browser")],
                "client": ("10.0.0.8", 44321),
            }
        )

        with patch.object(auth_router, "record_audit_event") as mocked:
            result = await auth_router.audited_logout(request=request, user=current_actor)

        self.assertEqual(result, {"success": True})
        mocked.assert_called_once_with(
            current_actor,
            action="auth.logout",
            resource_type="auth",
            ip_address="10.0.0.8",
            user_agent="audit-browser",
        )
