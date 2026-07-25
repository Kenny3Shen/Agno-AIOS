"""Critical chat session ownership and route permission tests."""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from api.auth.ownership import assert_owned_resource
from api.routes import chat
import pytest


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


def raw_request(body: dict[str, Any] | None = None) -> Request:
    payload = json.dumps(body or {}).encode()

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": payload, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/chat",
            "headers": [(b"content-type", b"application/json")],
            "client": ("127.0.0.1", 1),
        },
        receive=receive,
    )


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
async def test_cancel_chat_run_requires_a_live_run_owned_by_the_actor():
    current_actor = actor("u1")
    with patch.object(
        chat, "acancel_security_run", new_callable=AsyncMock, return_value=False
    ):
        with pytest.raises(HTTPException) as exc:
            await chat.cancel_chat_run("run-1", user=current_actor)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_chat_rejects_foreign_existing_session_id():
    with patch.object(chat, "get_session_owner_async", new_callable=AsyncMock) as mocked:
        mocked.return_value = "u2"
        with pytest.raises(HTTPException) as exc:
            await chat.chat_agent(
                raw_request({"message": "hello", "session_id": "foreign-session"}),
                user=actor("u1"),
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_sessions_uses_current_user_as_owner_filter():
    captured: dict[str, object] = {}

    async def fake_list_sessions(
        *,
        owner_user_id: str | None,
        include_archived: bool = False,
        archived_only: bool = False,
        include_runs: bool = False,
        page: int = 1,
        limit: int = 40,
        q: str | None = None,
    ):
        captured["owner_user_id"] = owner_user_id
        captured["include_archived"] = str(include_archived)
        captured["archived_only"] = str(archived_only)
        captured["include_runs"] = str(include_runs)
        captured["page"] = page
        captured["limit"] = limit
        captured["q"] = q
        return {
            "data": [],
            "meta": {
                "page": page,
                "limit": limit,
                "total_pages": 0,
                "total_count": 0,
                "search_time_ms": 0.0,
            },
        }

    with patch.object(chat, "list_sessions_async", fake_list_sessions):
        result = await chat.list_sessions(include_archived=True, user=actor("u1"))
    assert result["data"] == []
    assert result["meta"]["total_count"] == 0
    assert captured["owner_user_id"] == "u1"
    assert captured["include_archived"] == "True"
    assert captured["limit"] == 40
