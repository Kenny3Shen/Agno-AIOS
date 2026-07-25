"""Critical business tests for trace scope, validation, ownership, and error mark."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.routes import trace
from api.routes.trace import effective_trace_user_filter
from api.services import tracing_service
from api.services.tracing_service import get_trace_detail


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


def test_user_trace_filter_forces_current_user():
    assert effective_trace_user_filter(actor("u1"), requested_user_id="u2") == "u1"
    assert (
        effective_trace_user_filter(actor("u2"), requested_user_id=None)
        == "u2"
    )


def test_admin_trace_filter_honors_requested_user_or_all():
    admin = actor("a1", "admin")
    assert effective_trace_user_filter(admin, requested_user_id="u2") == "u2"
    assert effective_trace_user_filter(admin, requested_user_id=None) is None


@pytest.mark.asyncio
async def test_trace_list_forces_current_user_for_non_admin():
    captured: dict[str, str | None] = {}

    async def fake_list_traces(**kwargs):
        captured["user_id"] = kwargs.get("user_id")
        return {
            "data": [],
            "meta": {
                "page": 1,
                "limit": 20,
                "total_pages": 0,
                "total_count": 0,
                "search_time_ms": 0.0,
            },
        }

    with patch.object(trace, "list_traces", fake_list_traces):
        result = await trace.api_list_traces(
            session_id="session-1",
            user_id="attacker-choice",
            user=actor("u1"),
        )
    assert result["data"] == []
    assert captured["user_id"] == "u1"


@pytest.mark.asyncio
async def test_trace_list_admin_can_filter_by_user():
    captured: dict[str, object] = {}

    async def fake_list_traces(**kwargs):
        captured.update(kwargs)
        return {
            "data": [],
            "meta": {
                "page": 1,
                "limit": 20,
                "total_pages": 0,
                "total_count": 0,
                "search_time_ms": 0.0,
            },
        }

    with patch.object(trace, "list_traces", fake_list_traces):
        await trace.api_list_traces(user_id="u2", user=actor("admin-1", "admin"))
    assert captured["user_id"] == "u2"


@pytest.mark.asyncio
async def test_trace_detail_checks_ownership_before_querying_spans() -> None:
    trace_record = SimpleNamespace(
        to_dict=lambda: {"trace_id": "trace-1", "user_id": "owner"}
    )
    span_queries = 0

    async def fake_get_trace(**kwargs):
        assert kwargs == {"trace_id": "trace-1"}
        return trace_record

    async def fake_get_spans(**kwargs):
        nonlocal span_queries
        span_queries += 1
        return []

    with (
        patch.object(tracing_service._trace_db, "get_trace", fake_get_trace),
        patch.object(tracing_service._trace_db, "get_spans", fake_get_spans),
        pytest.raises(HTTPException) as exc,
    ):
        await get_trace_detail("trace-1", actor=actor("other"))

    assert exc.value.status_code == 404
    assert span_queries == 0


@pytest.mark.asyncio
async def test_trace_list_rejects_invalid_status_or_time_range() -> None:
    with pytest.raises(ValueError, match="status"):
        await tracing_service.list_traces(status="BROKEN")
    with pytest.raises(ValueError, match="时区"):
        await tracing_service.list_traces(start_time="2026-02-12T00:00:00")
    with pytest.raises(ValueError, match="不能晚于"):
        await tracing_service.list_traces(
            start_time="2026-02-13T00:00:00Z",
            end_time="2026-02-12T00:00:00Z",
        )


@pytest.mark.asyncio
async def test_mark_trace_error_updates_matching_trace():
    stored: list[object] = []
    fake_trace = SimpleNamespace(status="OK")

    async def fake_get_trace(*, run_id):
        assert run_id == "run-1"
        return fake_trace

    async def fake_upsert_trace(value):
        stored.append(value)

    with (
        patch.object(tracing_service._trace_db, "get_trace", fake_get_trace),
        patch.object(tracing_service._trace_db, "upsert_trace", fake_upsert_trace),
    ):
        assert await tracing_service.mark_trace_error("run-1") is True
    assert fake_trace.status == "ERROR"
    assert stored == [fake_trace]
