from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from fastapi.routing import APIRoute
from starlette.requests import Request
from api.auth.ownership import assert_owned_resource
from api.routes import chat
from api.services import chat_session_service, security_run_runtime
from api.services.chat_run_events import ChatRunEvent
import pytest


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


def raw_request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": [], "client": ("127.0.0.1", 1)})


def test_owned_resource_allows_owner():
    assert_owned_resource(actor("u1"), owner_user_id="u1", resource_name="Session")


def test_owned_resource_hides_foreign_resource():
    with pytest.raises(HTTPException) as exc:
        assert_owned_resource(actor("u1"), owner_user_id="u2", resource_name="Session")
    assert exc.value.status_code == 404


def test_admin_can_access_foreign_resource():
    admin = SimpleNamespace(id="admin", role="admin", is_superuser=False)
    assert_owned_resource(admin, owner_user_id="u2", resource_name="Session")


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


@pytest.mark.asyncio
async def test_rename_session_uses_the_current_actor_and_returns_title():
    current_actor = actor("u1")
    payload = {"session_id": "session-1", "title": "事件调查", "preview": "hello"}
    with patch.object(chat, "rename_session", new_callable=AsyncMock) as rename:
        rename.return_value = payload
        result = await chat.rename_chat_session(
            "session-1",
            chat.SessionRenameRequest(title="事件调查"),
            user=current_actor,
        )
    assert result == payload
    rename.assert_awaited_once_with("session-1", "事件调查", actor=current_actor)


@pytest.mark.asyncio
async def test_rename_session_maps_missing_or_invalid_title_to_http_errors():
    with patch.object(chat, "rename_session", new_callable=AsyncMock) as rename:
        rename.return_value = None
        with pytest.raises(HTTPException) as missing:
            await chat.rename_chat_session(
                "missing", chat.SessionRenameRequest(title="Title"), user=actor("u1")
            )
    assert missing.value.status_code == 404

    with patch.object(chat, "rename_session", new_callable=AsyncMock) as rename:
        rename.side_effect = ValueError("会话标题不能为空")
        with pytest.raises(HTTPException) as invalid:
            await chat.rename_chat_session(
                "session-1", chat.SessionRenameRequest(title=" "), user=actor("u1")
            )
    assert invalid.value.status_code == 422


@pytest.mark.asyncio
async def test_cancel_chat_run_requires_a_live_run_owned_by_the_actor():
    current_actor = actor("u1")
    with patch.object(chat, "cancel_security_run", return_value=False):
        with pytest.raises(HTTPException) as exc:
            await chat.cancel_chat_run("run-1", user=current_actor)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_cancel_chat_run_records_audit_event():
    current_actor = actor("u1")
    audit = AsyncMock()
    with (
        patch.object(chat, "cancel_security_run", return_value=True) as cancel,
        patch.object(chat, "record_audit_event_async", audit),
    ):
        result = await chat.cancel_chat_run("run-1", user=current_actor)
    assert result == {"success": True, "run_id": "run-1"}
    cancel.assert_called_once_with(user_id="u1", run_id="run-1")
    assert audit.await_args is not None
    assert audit.await_args.kwargs["action"] == "chat.run.cancel"


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
        result = await chat.list_sessions(include_archived=True, user=actor("u1"))
    assert result == []
    assert captured["owner_user_id"] == "u1"
    assert captured["include_archived"] == "True"


@pytest.mark.asyncio
async def test_chat_rejects_foreign_existing_session_id():
    with patch.object(chat, "get_session_owner_async", new_callable=AsyncMock) as mocked:
        mocked.return_value = "u2"
        with pytest.raises(HTTPException) as exc:
            await chat.chat_agent(
                chat.ChatRequest(message="hello", session_id="foreign-session"),
                raw_request(),
                user=actor("u1"),
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_chat_allows_owned_existing_session_id():
    with patch.object(chat, "get_session_owner_async", new_callable=AsyncMock) as mocked:
        mocked.return_value = "u1"
        response = await chat.chat_agent(
            chat.ChatRequest(message="hello", session_id="own-session"),
            raw_request(),
            user=actor("u1"),
        )
    assert response.media_type == "text/event-stream"
    assert response.sep == "\n"


@pytest.mark.asyncio
async def test_chat_passes_reasoning_effort_to_the_run_request():
    captured: dict[str, object] = {}
    original = security_run_runtime.SecurityRunRequest.from_chat_args

    def capture_request(*args, **kwargs):
        captured.update(kwargs)
        return original(*args, **kwargs)

    with (
        patch.object(chat, "get_model_for_run", new_callable=AsyncMock) as get_model,
        patch.object(
            chat.SecurityRunRequest,
            "from_chat_args",
            side_effect=capture_request,
        ),
    ):
        get_model.return_value = {
            "provider": "deepseek",
            "api_protocol": "chat-completions",
        }
        response = await chat.chat_agent(
            chat.ChatRequest(
                message="hello",
                model_id="deepseek-1",
                reasoning_effort="max",
            ),
            raw_request(),
            user=actor("u1"),
        )

    assert response.media_type == "text/event-stream"
    assert captured["reasoning_effort"] == "max"


@pytest.mark.asyncio
async def test_chat_rejects_reasoning_effort_for_incompatible_model():
    with patch.object(chat, "get_model_for_run", new_callable=AsyncMock) as get_model:
        get_model.return_value = {
            "provider": "openai-compatible",
            "api_protocol": "chat-completions",
        }
        with pytest.raises(HTTPException) as exc:
            await chat.chat_agent(
                chat.ChatRequest(message="hello", reasoning_effort="high"),
                raw_request(),
                user=actor("u1"),
            )

    assert exc.value.status_code == 422


def test_chat_rejects_openai_chat_minimal_reasoning_effort():
    with pytest.raises(HTTPException) as exc:
        chat._validate_reasoning_effort(
            "minimal",
            {"provider": "openai", "api_protocol": "chat-completions"},
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_event_generator_passes_knowledge_owner_filter():
    captured: dict[str, str | None] = {}

    async def fake_stream_security_run(run_request):
        captured["message"] = run_request.message
        captured["knowledge_owner_user_id"] = run_request.knowledge_owner_user_id
        yield ChatRunEvent("content.delta", {"run_id": "run-1", "delta": "ok"})

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
    assert events == [{"event": "content.delta", "data": '{"run_id": "run-1", "delta": "ok"}'}]


@pytest.mark.asyncio
async def test_event_generator_records_successful_chat_audit():
    async def fake_stream_security_run(_run_request):
        yield ChatRunEvent("run.completed", {"run_id": "run-1", "session_id": "session-1", "metrics": {}, "followups": []})

    audit = AsyncMock()
    request = security_run_runtime.SecurityRunRequest.from_chat_args(
        "hello",
        session_id="session-1",
        model_id="model-1",
        user_id="u1",
    )
    with (
        patch.object(chat, "stream_security_run", fake_stream_security_run),
        patch.object(chat, "record_audit_event_async", audit),
    ):
        _events = [
            event
            async for event in chat._event_generator(
                request,
                actor=actor("u1"),
                request_context={"ip_address": "127.0.0.1", "user_agent": "pytest"},
            )
        ]
    audit.assert_awaited_once()
    assert audit.await_args is not None
    assert audit.await_args.kwargs["resource_id"] == "run-1"
    assert audit.await_args.kwargs["status"] == "success"
    assert audit.await_args.kwargs["metadata"]["reasoning_effort"] == ""


def test_exception_detail_unwraps_task_group():
    error = ExceptionGroup("task group", [ValueError("invalid skill metadata")])
    assert chat._exception_detail(error) == "ValueError: invalid skill metadata"
