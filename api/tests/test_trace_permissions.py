from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from api.routes import trace
from api.routes.trace import effective_trace_user_filter


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


class TracePermissionsTest(TestCase):
    def test_user_trace_filter_forces_current_user(self):
        self.assertEqual(effective_trace_user_filter(actor("u1"), requested_user_id="u2"), "u1")

    def test_guest_trace_filter_forces_current_user(self):
        self.assertEqual(effective_trace_user_filter(actor("g1", "guest"), requested_user_id=None), "g1")

    def test_admin_trace_filter_honors_requested_user_or_all(self):
        admin = actor("a1", "admin")
        self.assertEqual(effective_trace_user_filter(admin, requested_user_id="u2"), "u2")
        self.assertIsNone(effective_trace_user_filter(admin, requested_user_id=None))


class TraceRoutePermissionsTest(IsolatedAsyncioTestCase):
    async def test_trace_list_forces_current_user_for_non_admin(self):
        captured: dict[str, str | None] = {}

        async def fake_list_traces(**kwargs):
            captured["user_id"] = kwargs.get("user_id")
            captured["session_id"] = kwargs.get("session_id")
            return {"items": [], "total_count": 0, "page": 1, "limit": 20}

        with patch.object(trace, "list_traces", fake_list_traces):
            result = await trace.api_list_traces(
                session_id="session-1",
                user_id="attacker-choice",
                user=actor("u1"),
            )

        self.assertEqual(result["items"], [])
        self.assertEqual(captured["user_id"], "u1")
        self.assertEqual(captured["session_id"], "session-1")

    async def test_trace_detail_passes_current_user_to_service(self):
        captured: dict[str, object] = {}

        async def fake_get_trace_detail(trace_id: str, *, actor):
            captured["trace_id"] = trace_id
            captured["actor"] = actor
            return {"trace": {"trace_id": trace_id}, "spans": [], "tree": []}

        current_actor = actor("u1")
        with patch.object(trace, "get_trace_detail", fake_get_trace_detail):
            result = await trace.api_get_trace("trace-1", user=current_actor)

        self.assertEqual(result["trace"]["trace_id"], "trace-1")
        self.assertIs(captured["actor"], current_actor)
