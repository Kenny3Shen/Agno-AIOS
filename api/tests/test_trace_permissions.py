import inspect
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from api.routes import trace
from api.routes.trace import effective_trace_user_filter
from api.services import tracing_service
import pytest


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


def test_trace_routes_require_explicit_trace_permission():
    assert 'require_permission("trace:read:own")' in inspect.getsource(
        trace.api_list_traces
    )
    assert 'require_permission("trace:read:own")' in inspect.getsource(
        trace.api_get_trace
    )


def test_user_trace_filter_forces_current_user():
    assert effective_trace_user_filter(actor("u1"), requested_user_id="u2") == "u1"


def test_guest_trace_filter_forces_current_user():
    assert (
        effective_trace_user_filter(actor("g1", "guest"), requested_user_id=None)
        == "g1"
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
        captured["session_id"] = kwargs.get("session_id")
        return {"items": [], "total_count": 0, "page": 1, "limit": 20}

    with patch.object(trace, "list_traces", fake_list_traces):
        result = await trace.api_list_traces(
            session_id="session-1", user_id="attacker-choice", user=actor("u1")
        )
    assert result["items"] == []
    assert captured["user_id"] == "u1"
    assert captured["session_id"] == "session-1"


@pytest.mark.asyncio
async def test_trace_list_passes_all_filters_to_service():
    captured: dict[str, object] = {}

    async def fake_list_traces(**kwargs):
        captured.update(kwargs)
        return {
            "items": [],
            "total_count": 0,
            "page": kwargs["page"],
            "limit": kwargs["limit"],
        }

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
    assert result["page"] == 3
    assert result["limit"] == 50
    assert captured == {
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
    }


@pytest.mark.asyncio
async def test_trace_detail_passes_current_user_to_service():
    captured: dict[str, object] = {}

    async def fake_get_trace_detail(trace_id: str, *, actor):
        captured["trace_id"] = trace_id
        captured["actor"] = actor
        return {"trace": {"trace_id": trace_id}, "spans": [], "tree": []}

    current_actor = actor("u1")
    with patch.object(trace, "get_trace_detail", fake_get_trace_detail):
        result = await trace.api_get_trace("trace-1", user=current_actor)
    assert result["trace"]["trace_id"] == "trace-1"
    assert captured["actor"] is current_actor


@pytest.mark.asyncio
async def test_list_traces_passes_all_filters_to_agno_db():
    captured: dict[str, object] = {}

    async def fake_get_traces(**kwargs):
        captured.update(kwargs)
        return ([], 0)

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
    assert result == {"items": [], "total_count": 0, "page": 2, "limit": 25}
    assert captured["run_id"] == "run-1"
    assert captured["session_id"] == "session-1"
    assert captured["user_id"] == "u1"
    assert captured["agent_id"] == "agent-1"
    assert captured["team_id"] == "team-1"
    assert captured["workflow_id"] == "workflow-1"
    assert captured["status"] == "OK"
    assert captured["start_time"] == datetime(2026, 2, 12, 0, 0, tzinfo=timezone.utc)
    assert captured["end_time"] == datetime(
        2026, 2, 12, 23, 59, 59, tzinfo=timezone.utc
    )
    assert captured["limit"] == 25
    assert captured["page"] == 2


def test_trace_service_uses_async_agno_db_without_thread_offload():
    source = inspect.getsource(tracing_service)
    assert "get_async_agno_postgres_db" in source
    assert "asyncio.to_thread" not in source
