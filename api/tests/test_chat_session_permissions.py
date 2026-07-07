from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from fastapi.routing import APIRoute
from api.auth.permissions import assert_owned_resource
from api.routes import chat
from api.services import chat_session_service, security_run_runtime
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
    assert "owner_user_id" in chat_session_service.get_all_sessions_async.__annotations__ | {}


@pytest.mark.asyncio
async def test_session_list_service_passes_owner_filter_to_agno_db():
    captured: dict[str, object] = {}

    class FakeDb:
        async def get_sessions(self, **kwargs):
            captured.update(kwargs)
            return []

    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async", new_callable=AsyncMock),
        patch.object(chat_session_service, "get_async_agno_postgres_db", return_value=FakeDb()),
    ):
        result = await chat_session_service.get_all_sessions_async(owner_user_id="u1")

    assert result == []
    assert captured["user_id"] == "u1"
    assert captured["deserialize"] is False


def route_dependency(endpoint_name: str):
    for route in chat.router.routes:
        if isinstance(route, APIRoute) and getattr(route.endpoint, "__name__", "") == endpoint_name:
            return route.dependant.dependencies[0].call
    raise AssertionError(f"missing route for {endpoint_name}")


def test_chat_write_route_rejects_guest_actor():
    dependency = route_dependency("chat_agent")

    with pytest.raises(HTTPException) as exc:
        dependency(user=actor("g1", "guest"))

    assert exc.value.status_code == 403


def test_chat_read_route_allows_guest_actor():
    dependency = route_dependency("list_sessions")

    assert dependency(user=actor("g1", "guest")).id == "g1"


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
