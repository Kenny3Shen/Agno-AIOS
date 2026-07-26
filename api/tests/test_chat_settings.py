from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, Request
from pydantic import ValidationError

from api.routes import settings
from api.auth.models import User
from api.persistence.chat_settings import chat_settings_table
from api.services import chat_settings_service
from api.tests.route_fakes import route_dependency
from api.utils.ttl_cache import TtlCache


def test_chat_settings_routes_require_admin_scope() -> None:
    actor = SimpleNamespace(role="user", is_superuser=False)
    for endpoint in ("read_chat_settings", "patch_chat_settings"):
        with pytest.raises(HTTPException) as exc:
            route_dependency(settings.router, endpoint)(user=actor)
        assert exc.value.status_code == 403


def test_chat_settings_table_uses_memory_mode_without_legacy_flags() -> None:
    columns = chat_settings_table().c
    assert "memory_mode" in columns
    assert "memory_enabled" not in columns
    assert "enable_agentic_memory" not in columns


@pytest.mark.asyncio
async def test_read_chat_settings_returns_persisted_defaults() -> None:
    expected = {
        "show_raw_reasoning": False,
        "show_raw_tool_io": False,
        "show_thought_chain": True,
        "memory_mode": "automatic",
        "num_history_runs": 5,
        "session_summaries_enabled": True,
        "add_datetime_to_context": True,
        "max_tool_calls_from_history": None,
        "default_tool_call_limit": None,
        "markdown": True,
        "memory_tool_content_enabled": False,
        "memory_prune_enabled": True,
        "memory_prune_retention_days": 90,
        "memory_prune_top_k": 50,
        "memory_inject_enabled": True,
        "memory_inject_top_k": 12,
        "memory_inject_window_days": 90,
        "memory_inject_dedupe_topics": True,
    }
    with patch.object(settings, "get_chat_settings", new=AsyncMock(return_value=expected)):
        assert await settings.read_chat_settings(_user=cast(User, SimpleNamespace())) == expected


@pytest.mark.asyncio
async def test_patch_chat_settings_updates_only_submitted_values_and_audits() -> None:
    request = Request({"type": "http", "method": "PATCH", "path": "/api/settings/chat", "headers": []})
    expected = {
        "show_raw_reasoning": True,
        "show_raw_tool_io": False,
        "show_thought_chain": True,
        "memory_mode": "automatic",
        "num_history_runs": 3,
        "session_summaries_enabled": True,
        "add_datetime_to_context": True,
        "max_tool_calls_from_history": 10,
        "default_tool_call_limit": None,
        "markdown": True,
        "memory_tool_content_enabled": False,
        "memory_prune_enabled": True,
        "memory_prune_retention_days": 90,
        "memory_prune_top_k": 50,
        "memory_inject_enabled": True,
        "memory_inject_top_k": 12,
        "memory_inject_window_days": 90,
        "memory_inject_dedupe_topics": True,
    }
    with (
        patch.object(settings, "update_chat_settings", new=AsyncMock(return_value=expected)) as update_mock,
        patch.object(settings, "record_audit_event_async", new=AsyncMock()) as audit_mock,
    ):
        result = await settings.patch_chat_settings(
            request,
            settings.ChatSettingsUpdate(show_raw_reasoning=True),
            user=cast(User, SimpleNamespace(id="admin-1")),
        )
    assert result == expected
    update_mock.assert_awaited_once_with({"show_raw_reasoning": True})
    audit_call = audit_mock.await_args
    assert audit_call is not None
    assert audit_call.kwargs["metadata"] == {"keys": ["show_raw_reasoning"]}


@pytest.mark.asyncio
async def test_chat_settings_service_applies_defaults_for_missing_columns() -> None:
    with patch.object(
        chat_settings_service,
        "get_chat_settings_row",
        new=AsyncMock(return_value={}),
    ):
        result = await chat_settings_service.get_chat_settings()
    assert result["show_raw_reasoning"] is False
    assert result["show_raw_tool_io"] is False
    assert result["show_thought_chain"] is True
    assert result["memory_mode"] == "automatic"
    assert "memory_enabled" not in result
    assert "enable_agentic_memory" not in result
    assert result["num_history_runs"] == 5
    assert result["session_summaries_enabled"] is True
    assert result["markdown"] is True
    assert result["max_tool_calls_from_history"] is None
    assert result["memory_tool_content_enabled"] is False
    assert result["memory_prune_enabled"] is True
    assert result["memory_prune_retention_days"] == 90
    assert result["memory_prune_top_k"] == 50
    assert result["memory_inject_enabled"] is True
    assert result["memory_inject_top_k"] == 12
    assert result["memory_inject_window_days"] == 90
    assert result["memory_inject_dedupe_topics"] is True


@pytest.mark.asyncio
async def test_update_memory_mode_persists_only_canonical_value() -> None:
    with (
        patch.object(
            chat_settings_service,
            "update_chat_settings_row",
            new=AsyncMock(
                side_effect=lambda values: {
                    "memory_mode": values.get("memory_mode", "automatic"),
                    "show_raw_reasoning": False,
                    "show_raw_tool_io": False,
                    "show_thought_chain": True,
                    "num_history_runs": 5,
                    "session_summaries_enabled": True,
                    "add_datetime_to_context": True,
                    "max_tool_calls_from_history": None,
                    "default_tool_call_limit": None,
                    "markdown": True,
                    "memory_tool_content_enabled": False,
                    "memory_prune_enabled": True,
                    "memory_prune_retention_days": 90,
                    "memory_prune_top_k": 50,
                    "memory_inject_enabled": True,
                    "memory_inject_top_k": 12,
                    "memory_inject_window_days": 90,
                    "memory_inject_dedupe_topics": True,
                }
            ),
        ) as update_row,
    ):
        result = await chat_settings_service.update_chat_settings(
            {"memory_mode": "agentic"}
        )
    assert result["memory_mode"] == "agentic"
    assert "memory_enabled" not in result
    assert "enable_agentic_memory" not in result
    update_row.assert_awaited_once()
    assert update_row.await_args is not None
    sent = update_row.await_args.args[0]
    assert sent == {"memory_mode": "agentic"}


def test_chat_settings_update_rejects_legacy_memory_flags() -> None:
    for field in ("memory_enabled", "enable_agentic_memory"):
        with pytest.raises(ValidationError):
            settings.ChatSettingsUpdate.model_validate({field: True})


@pytest.fixture(autouse=True)
def _chat_settings_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_settings_service, "_SETTINGS_CACHE", TtlCache(ttl_sec=5.0))


@pytest.mark.asyncio
async def test_get_chat_settings_uses_short_ttl_cache() -> None:
    row = {
        "show_raw_reasoning": True,
        "show_raw_tool_io": False,
        "show_thought_chain": True,
        "memory_mode": "off",
    }
    get_row = AsyncMock(return_value=row)
    with patch.object(chat_settings_service, "get_chat_settings_row", get_row):
        first = await chat_settings_service.get_chat_settings()
        second = await chat_settings_service.get_chat_settings()
    assert first == second
    assert first["show_raw_reasoning"] is True
    assert first["memory_mode"] == "off"
    assert get_row.await_count == 1
