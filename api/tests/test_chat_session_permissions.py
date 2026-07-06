import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from api.auth.permissions import assert_owned_resource
from api.routes import chat
from api.services import llm_service, security_run_runtime
import pytest


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


def test_owned_resource_allows_owner():
    assert_owned_resource(actor("u1"), owner_user_id="u1", resource_name="Session")


def test_owned_resource_hides_foreign_resource():
    with pytest.raises(HTTPException) as exc:
        assert_owned_resource(actor("u1"), owner_user_id="u2", resource_name="Session")
    assert exc.value.status_code == 404


def test_admin_can_access_foreign_resource():
    admin = SimpleNamespace(id="admin", role="admin", is_superuser=False)
    assert_owned_resource(admin, owner_user_id="u2", resource_name="Session")


def test_chat_request_does_not_accept_authoritative_user_id():
    assert "user_id" not in chat.ChatRequest.model_fields


def test_session_list_service_accepts_owner_filter():
    assert "owner_user_id" in llm_service.get_all_sessions_async.__annotations__ | {}


def test_session_list_uses_agno_db_owner_filter():
    source = inspect.getsource(llm_service.get_all_sessions_async)
    assert "get_sessions" in source
    assert "user_id=owner_user_id" in source
    assert "chat_session_archives" not in source


def test_chat_routes_require_explicit_session_permissions():
    assert 'require_permission("session:write:own")' in inspect.getsource(
        chat.chat_agent
    )
    assert 'require_permission("session:read:own")' in inspect.getsource(
        chat.list_sessions
    )
    assert 'require_permission("session:read:own")' in inspect.getsource(
        chat.get_session
    )
    assert 'require_permission("session:write:own")' in inspect.getsource(
        chat.remove_session
    )


@pytest.mark.asyncio
async def test_remove_session_archives_session_and_returns_payload():
    current_actor = actor("u1")
    with patch.object(chat, "archive_session", new_callable=AsyncMock) as archive_session:
        archive_session.return_value = True
        result = await chat.remove_session("session-1", user=current_actor)
    assert result == {"success": True, "archived": True}
    archive_session.assert_awaited_once_with("session-1", actor=current_actor)


def test_provider_block_detector_matches_openai_status_error_text():
    assert security_run_runtime._is_provider_block_error(
        RuntimeError("Your request was blocked.")
    )


@pytest.mark.asyncio
async def test_list_sessions_uses_current_user_as_owner_filter():
    captured: dict[str, str | None] = {}

    async def fake_get_all_sessions(
        *,
        owner_user_id: str | None,
        include_archived: bool = False,
        include_runs: bool = False,
    ):
        captured["owner_user_id"] = owner_user_id
        captured["include_archived"] = str(include_archived)
        captured["include_runs"] = str(include_runs)
        return []

    with patch.object(chat, "get_all_sessions_async", fake_get_all_sessions):
        result = await chat.list_sessions(user=actor("u1"))
    assert result == []
    assert captured["owner_user_id"] == "u1"


@pytest.mark.asyncio
async def test_chat_rejects_foreign_existing_session_id():
    with patch.object(chat, "get_session_owner_async", new_callable=AsyncMock) as mocked:
        mocked.return_value = "u2"
        with pytest.raises(HTTPException) as exc:
            await chat.chat_agent(
                chat.ChatRequest(message="hello", session_id="foreign-session"),
                user=actor("u1"),
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_chat_allows_owned_existing_session_id():
    with patch.object(chat, "get_session_owner_async", new_callable=AsyncMock) as mocked:
        mocked.return_value = "u1"
        response = await chat.chat_agent(
            chat.ChatRequest(message="hello", session_id="own-session"),
            user=actor("u1"),
        )
    assert response.media_type == "text/event-stream"
    assert response.sep == "\n"


@pytest.mark.asyncio
async def test_event_generator_passes_knowledge_owner_filter():
    captured: dict[str, str | None] = {}

    async def fake_stream_security_run(run_request):
        captured["message"] = run_request.message
        captured["knowledge_owner_user_id"] = run_request.knowledge_owner_user_id
        yield "ok"

    with patch.object(chat, "stream_security_run", fake_stream_security_run):
        events = [
            event
            async for event in chat._event_generator(
                security_run_runtime.SecurityRunRequest.from_chat_args(
                    "hello", user_id="u1", knowledge_owner_user_id="u1"
                )
            )
        ]
    assert captured["message"] == "hello"
    assert captured["knowledge_owner_user_id"] == "u1"
    assert events == [{"data": "ok"}, {"data": "[DONE]"}]
