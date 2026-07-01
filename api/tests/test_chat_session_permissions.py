from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from fastapi import HTTPException

from api.auth.permissions import assert_owned_resource
from api.routes import chat
from api.services import llm_service


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


class ChatSessionPermissionsTest(TestCase):
    def test_owned_resource_allows_owner(self):
        assert_owned_resource(actor("u1"), owner_user_id="u1", resource_name="Session")

    def test_owned_resource_hides_foreign_resource(self):
        with self.assertRaises(HTTPException) as exc:
            assert_owned_resource(actor("u1"), owner_user_id="u2", resource_name="Session")
        self.assertEqual(exc.exception.status_code, 404)

    def test_admin_can_access_foreign_resource(self):
        admin = SimpleNamespace(id="admin", role="admin", is_superuser=False)
        assert_owned_resource(admin, owner_user_id="u2", resource_name="Session")

    def test_chat_request_does_not_accept_authoritative_user_id(self):
        self.assertNotIn("user_id", chat.ChatRequest.model_fields)

    def test_session_list_service_accepts_owner_filter(self):
        self.assertIn("owner_user_id", llm_service.get_all_sessions.__annotations__ | {})


class ChatRoutePermissionsTest(IsolatedAsyncioTestCase):
    async def test_guest_cannot_send_chat_message(self):
        with self.assertRaises(HTTPException) as exc:
            await chat.chat_agent(chat.ChatRequest(message="hello"), user=actor("g1", "guest"))
        self.assertEqual(exc.exception.status_code, 403)

    async def test_list_sessions_uses_current_user_as_owner_filter(self):
        captured: dict[str, str | None] = {}

        def fake_get_all_sessions(*, owner_user_id: str | None, include_archived: bool = False):
            captured["owner_user_id"] = owner_user_id
            captured["include_archived"] = str(include_archived)
            return []

        with patch.object(chat, "get_all_sessions", fake_get_all_sessions):
            result = await chat.list_sessions(user=actor("u1"))

        self.assertEqual(result, [])
        self.assertEqual(captured["owner_user_id"], "u1")
