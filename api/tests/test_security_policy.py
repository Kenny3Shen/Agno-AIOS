from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from api.services import security_policy


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


class SecurityPolicyTest(TestCase):
    def test_control_module_access_uses_declared_permission_map(self):
        security_policy.require_control_module_access("sessions", actor("u1"))

        with self.assertRaises(HTTPException) as exc:
            security_policy.require_control_module_access("studio", actor("guest", "guest"))
        self.assertEqual(exc.exception.status_code, 403)

        with self.assertRaises(HTTPException) as exc:
            security_policy.require_control_module_access("unknown", actor("u1"))
        self.assertEqual(exc.exception.status_code, 404)

    def test_scheduler_write_requires_admin_permission(self):
        with self.assertRaises(HTTPException) as exc:
            security_policy.require_scheduler_write(actor("u1"))
        self.assertEqual(exc.exception.status_code, 403)

        security_policy.require_scheduler_write(actor("admin", "admin"))

    def test_record_policy_event_includes_request_context(self):
        current_actor = actor("u1")
        request = Request(
            {
                "type": "http",
                "headers": [(b"user-agent", b"policy-browser")],
                "client": ("10.0.0.9", 44321),
            }
        )

        with patch.object(security_policy, "record_audit_event") as mocked:
            security_policy.record_policy_event(
                current_actor,
                security_policy.PolicyAuditEvent(
                    action="scheduler.trigger",
                    resource_type="schedule",
                    resource_id="sched-1",
                    metadata={"run_id": "run-1"},
                ),
                request,
            )

        mocked.assert_called_once_with(
            current_actor,
            action="scheduler.trigger",
            resource_type="schedule",
            resource_id="sched-1",
            status="success",
            metadata={"run_id": "run-1"},
            ip_address="10.0.0.9",
            user_agent="policy-browser",
        )
