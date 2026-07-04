import inspect
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from fastapi import HTTPException

from api.auth.permissions import assert_owned_resource
from api.routes import chat
from api.services import llm_service, security_run_runtime


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

    def test_session_list_owner_filter_applies_when_including_archived(self):
        source = inspect.getsource(llm_service.get_all_sessions)

        self.assertIn("WHERE (%s", source)
        self.assertIn(")\n                    AND (%s::text IS NULL OR s.user_id = %s::text)", source)

    def test_chat_routes_require_explicit_session_permissions(self):
        self.assertIn('require_permission("session:write:own")', inspect.getsource(chat.chat_agent))
        self.assertIn('require_permission("session:read:own")', inspect.getsource(chat.list_sessions))
        self.assertIn('require_permission("session:read:own")', inspect.getsource(chat.get_session))
        self.assertIn('require_permission("session:write:own")', inspect.getsource(chat.remove_session))

    def test_chat_provider_block_falls_back_to_lightweight_agent(self):
        source = inspect.getsource(security_run_runtime.stream_chat_with_agent)

        self.assertIn("_is_provider_block_error", source)
        self.assertIn("_build_fallback_agent", source)
        self.assertIn("无工具降级模式", source)

    def test_provider_block_detector_matches_openai_status_error_text(self):
        self.assertTrue(
            security_run_runtime._is_provider_block_error(
                RuntimeError("Your request was blocked.")
            )
        )


class ChatRoutePermissionsTest(IsolatedAsyncioTestCase):
    async def test_list_sessions_uses_current_user_as_owner_filter(self):
        captured: dict[str, str | None] = {}

        def fake_get_all_sessions(
            *,
            owner_user_id: str | None,
            include_archived: bool = False,
            include_runs: bool = False,
        ):
            captured["owner_user_id"] = owner_user_id
            captured["include_archived"] = str(include_archived)
            captured["include_runs"] = str(include_runs)
            return []

        with patch.object(chat, "get_all_sessions", fake_get_all_sessions):
            result = await chat.list_sessions(user=actor("u1"))

        self.assertEqual(result, [])
        self.assertEqual(captured["owner_user_id"], "u1")

    async def test_chat_rejects_foreign_existing_session_id(self):
        with patch.object(chat, "get_session_owner", return_value="u2"):
            with self.assertRaises(HTTPException) as exc:
                await chat.chat_agent(
                    chat.ChatRequest(message="hello", session_id="foreign-session"),
                    user=actor("u1"),
                )

        self.assertEqual(exc.exception.status_code, 404)

    async def test_chat_allows_owned_existing_session_id(self):
        with patch.object(chat, "get_session_owner", return_value="u1"):
            response = await chat.chat_agent(
                chat.ChatRequest(message="hello", session_id="own-session"),
                user=actor("u1"),
            )

        self.assertEqual(response.media_type, "text/event-stream")

    async def test_event_generator_passes_knowledge_owner_filter(self):
        captured: dict[str, str | None] = {}

        async def fake_stream_chat_with_agent(
            message: str,
            session_id: str | None,
            model_id: str | None,
            user_id: str | None,
            *,
            knowledge_owner_user_id: str | None,
        ):
            captured["message"] = message
            captured["knowledge_owner_user_id"] = knowledge_owner_user_id
            yield "ok"

        with patch.object(chat, "stream_chat_with_agent", fake_stream_chat_with_agent):
            chunks = [
                chunk
                async for chunk in chat._event_generator(
                    "hello",
                    user_id="u1",
                    knowledge_owner_user_id="u1",
                )
            ]

        self.assertEqual(captured["message"], "hello")
        self.assertEqual(captured["knowledge_owner_user_id"], "u1")
        self.assertIn("data: ok", chunks[0])
