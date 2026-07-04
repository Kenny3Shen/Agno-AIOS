from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from fastapi import HTTPException

from api.routes import os_control
from api.services import os_control_service


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


class FakeMemoryDb:
    def __init__(self):
        self.memory_kwargs: dict[str, object] = {}
        self.stats_kwargs: dict[str, object] = {}
        self.topics_user_id: str | None = None

    def get_user_memories(self, **kwargs):
        self.memory_kwargs = kwargs
        return (
            [
                {
                    "memory_id": "mem-1",
                    "memory": "Prefers concise incident summaries",
                    "topics": ["preference"],
                    "input": "Please keep incident summaries short.",
                    "user_id": kwargs.get("user_id") or "u1",
                    "agent_id": "security-operations",
                    "created_at": 1714560000,
                    "updated_at": 1714560300,
                }
            ],
            1,
        )

    def get_user_memory_stats(self, **kwargs):
        self.stats_kwargs = kwargs
        return (
            [
                {
                    "user_id": kwargs.get("user_id") or "u1",
                    "total_memories": 51,
                    "last_memory_updated_at": 1714560300,
                }
            ],
            1,
        )

    def get_all_memory_topics(self, user_id=None):
        self.topics_user_id = user_id
        return ["preference"]


class OsControlRoutePermissionsTest(IsolatedAsyncioTestCase):
    async def test_guest_cannot_access_studio_inventory(self):
        with self.assertRaises(HTTPException) as context:
            await os_control.require_os_module_permission("studio", user=actor("g1", "guest"))

        self.assertEqual(context.exception.status_code, 403)

    async def test_unknown_module_is_rejected_before_payload_lookup(self):
        with self.assertRaises(HTTPException) as context:
            await os_control.require_os_module_permission("unknown", user=actor("u1"))

        self.assertEqual(context.exception.status_code, 404)

    async def test_route_passes_actor_to_service(self):
        current_actor = actor("u1")

        with patch.object(os_control, "get_control_payload", return_value={"module": "sessions"}) as mocked:
            result = await os_control.get_os_control_module("sessions", user=current_actor)

        self.assertEqual(result["module"], "sessions")
        mocked.assert_called_once_with("sessions", actor=current_actor, query=None)


class OsControlServiceOwnershipTest(TestCase):
    def test_session_payload_filters_to_current_user(self):
        captured: dict[str, object] = {}

        def fake_get_all_sessions(*, owner_user_id: str | None, include_archived: bool = False):
            captured["owner_user_id"] = owner_user_id
            captured["include_archived"] = include_archived
            return []

        with (
            patch.object(os_control_service, "ensure_agno_postgres_tables"),
            patch.object(os_control_service, "get_all_sessions", fake_get_all_sessions),
        ):
            os_control_service.get_sessions_payload(actor("u1"))

        self.assertEqual(captured["owner_user_id"], "u1")
        self.assertIs(captured["include_archived"], True)

    def test_admin_session_payload_can_read_all_users(self):
        captured: dict[str, object] = {}

        def fake_get_all_sessions(*, owner_user_id: str | None, include_archived: bool = False):
            captured["owner_user_id"] = owner_user_id
            return []

        with (
            patch.object(os_control_service, "ensure_agno_postgres_tables"),
            patch.object(os_control_service, "get_all_sessions", fake_get_all_sessions),
        ):
            os_control_service.get_sessions_payload(actor("admin", "admin"))

        self.assertIsNone(captured["owner_user_id"])

    def test_metrics_user_filter_uses_current_user(self):
        where, params = os_control_service._user_where(actor("u1"), "trace:read:any")

        self.assertIsNotNone(where)
        self.assertEqual(params, ("u1",))

    def test_metrics_admin_filter_reads_all_users(self):
        where, params = os_control_service._user_where(actor("admin", "admin"), "trace:read:any")

        self.assertIsNone(where)
        self.assertEqual(params, ())

    def test_memory_payload_uses_current_user_for_ordinary_actor(self):
        db = FakeMemoryDb()

        with (
            patch.object(os_control_service, "ensure_agno_postgres_tables"),
            patch.object(os_control_service, "get_agno_postgres_db", return_value=db),
        ):
            payload = os_control_service.get_memory_payload(
                actor("u1"),
                user_id="other-user",
                topic="preference",
                search="concise",
            )

        self.assertEqual(db.memory_kwargs["user_id"], "u1")
        self.assertEqual(db.memory_kwargs["topics"], ["preference"])
        self.assertEqual(db.memory_kwargs["search_content"], "concise")
        self.assertEqual(db.stats_kwargs["user_id"], "u1")
        self.assertEqual(db.topics_user_id, "u1")
        self.assertEqual(payload["memory_filters"]["user_id"], "u1")
        self.assertEqual(payload["memory_users"][0]["status"], "review")

    def test_memory_payload_admin_can_filter_requested_user(self):
        db = FakeMemoryDb()

        with (
            patch.object(os_control_service, "ensure_agno_postgres_tables"),
            patch.object(os_control_service, "get_agno_postgres_db", return_value=db),
        ):
            payload = os_control_service.get_memory_payload(
                actor("admin", "admin"),
                user_id="u2",
            )

        self.assertEqual(db.memory_kwargs["user_id"], "u2")
        self.assertIsNone(db.stats_kwargs["user_id"])
        self.assertEqual(db.topics_user_id, "u2")
        self.assertEqual(payload["memory_filters"]["user_id"], "u2")
        self.assertTrue(payload["memory_mode"]["update_memory_on_run"])
        self.assertTrue(payload["memory_mode"]["enable_session_summaries"])
