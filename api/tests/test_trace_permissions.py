from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import HTTPException
from fastapi.routing import APIRoute
from api.auth import permissions
from api.routes import trace
from api.routes.trace import effective_trace_user_filter
from api.services import tracing_service
from api.services.tracing_service import parse_span_display
import pytest


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


def route_dependency(endpoint_name: str):
    for route in trace.router.routes:
        if isinstance(route, APIRoute) and getattr(route.endpoint, "__name__", "") == endpoint_name:
            return route.dependant.dependencies[0].call
    raise AssertionError(f"missing route for {endpoint_name}")


def test_trace_routes_enforce_trace_permission(monkeypatch):
    monkeypatch.setitem(permissions.ROLE_PERMISSIONS, "guest", set())

    for endpoint_name in ("api_list_traces", "api_get_trace"):
        with pytest.raises(HTTPException) as exc:
            route_dependency(endpoint_name)(user=actor("g1", "guest"))
        assert exc.value.status_code == 403


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


def test_parse_span_display_extracts_agentos_input_output_metadata() -> None:
    span = {
        "name": "OpenAIChat.ainvoke_stream",
        "attributes": {
            "input.value": '{"messages":[{"role":"user","content":"latest news?"}]}',
            "output.value": '{"content":"Here are the latest stories."}',
            "gen_ai.request.model": "gpt-5.2",
            "gen_ai.usage.prompt_tokens": 31,
            "gen_ai.usage.completion_tokens": 42,
        },
        "events": [
            {"name": "exception", "attributes": {"exception.message": "tool timeout"}}
        ],
    }
    parsed = parse_span_display(span)
    assert parsed["input"]["format"] == "json"
    assert "latest news?" in parsed["input"]["text"]
    assert parsed["output"]["format"] == "json"
    assert "latest stories" in parsed["output"]["text"]
    assert parsed["metadata"]["model"] == "gpt-5.2"
    assert parsed["metadata"]["tokens"]["prompt"] == 31
    assert parsed["events"][0]["message"] == "tool timeout"
