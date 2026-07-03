import inspect
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from api.routes import trace
from api.routes.trace import effective_trace_user_filter
from api.services import tracing_service


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


class TracePermissionsTest(TestCase):
    def test_trace_routes_require_explicit_trace_permission(self):
        self.assertIn('require_permission("trace:read:own")', inspect.getsource(trace.api_list_traces))
        self.assertIn('require_permission("trace:read:own")', inspect.getsource(trace.api_get_trace))

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

    async def test_trace_list_passes_all_filters_to_service(self):
        captured: dict[str, object] = {}

        async def fake_list_traces(**kwargs):
            captured.update(kwargs)
            return {"items": [], "total_count": 0, "page": kwargs["page"], "limit": kwargs["limit"]}

        with patch.object(trace, "list_traces", fake_list_traces):
            result = await trace.api_list_traces(
                run_id="run-1",
                session_id="session-1",
                user_id="u2",
                agent_id="agent-1",
                team_id="team-1",
                workflow_id="workflow-1",
                status="ERROR",
                start_time="2026-02-12T00:00:00+08:00",
                end_time="2026-02-12T23:59:59+08:00",
                limit=50,
                page=3,
                user=actor("admin-1", "admin"),
            )

        self.assertEqual(result["page"], 3)
        self.assertEqual(result["limit"], 50)
        self.assertEqual(
            captured,
            {
                "run_id": "run-1",
                "session_id": "session-1",
                "user_id": "u2",
                "agent_id": "agent-1",
                "team_id": "team-1",
                "workflow_id": "workflow-1",
                "status": "ERROR",
                "start_time": "2026-02-12T00:00:00+08:00",
                "end_time": "2026-02-12T23:59:59+08:00",
                "limit": 50,
                "page": 3,
            },
        )

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


class TraceServiceFilterTest(IsolatedAsyncioTestCase):
    async def test_list_traces_passes_all_filters_to_agno_db(self):
        captured: dict[str, object] = {}

        def fake_get_traces(**kwargs):
            captured.update(kwargs)
            return [], 0

        with patch.object(tracing_service._trace_db, "get_traces", fake_get_traces):
            result = await tracing_service.list_traces(
                run_id="run-1",
                session_id="session-1",
                user_id="u1",
                agent_id="agent-1",
                team_id="team-1",
                workflow_id="workflow-1",
                status="OK",
                start_time="2026-02-12T00:00:00Z",
                end_time="2026-02-12T23:59:59+00:00",
                limit=25,
                page=2,
            )

        self.assertEqual(result, {"items": [], "total_count": 0, "page": 2, "limit": 25})
        self.assertEqual(captured["run_id"], "run-1")
        self.assertEqual(captured["session_id"], "session-1")
        self.assertEqual(captured["user_id"], "u1")
        self.assertEqual(captured["agent_id"], "agent-1")
        self.assertEqual(captured["team_id"], "team-1")
        self.assertEqual(captured["workflow_id"], "workflow-1")
        self.assertEqual(captured["status"], "OK")
        self.assertEqual(captured["start_time"], datetime(2026, 2, 12, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(captured["end_time"], datetime(2026, 2, 12, 23, 59, 59, tzinfo=timezone.utc))
        self.assertEqual(captured["limit"], 25)
        self.assertEqual(captured["page"], 2)
