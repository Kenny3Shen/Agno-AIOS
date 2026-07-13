from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from fastapi.routing import APIRoute
from api.auth import claims
from api.routes import trace
from api.routes.trace import effective_trace_user_filter
from api.services import tracing_service
from api.services.tracing_service import _build_span_tree, get_trace_detail, parse_span_display
import pytest


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


def route_dependency(endpoint_name: str):
    for route in trace.router.routes:
        if isinstance(route, APIRoute) and getattr(route.endpoint, "__name__", "") == endpoint_name:
            return route.dependant.dependencies[0].call
    raise AssertionError(f"missing route for {endpoint_name}")


def test_trace_routes_enforce_trace_permission(monkeypatch):
    monkeypatch.setitem(claims.ROLE_SCOPES, "guest", set())

    for endpoint_name in ("api_list_traces", "api_list_trace_sessions", "api_get_trace"):
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
async def test_trace_session_list_forces_current_user_and_passes_filters():
    captured: dict[str, object] = {}

    async def fake_list_trace_sessions(**kwargs):
        captured.update(kwargs)
        return {"items": [], "total_count": 0, "page": kwargs["page"], "limit": kwargs["limit"]}

    with patch.object(trace, "list_trace_sessions", fake_list_trace_sessions):
        result = await trace.api_list_trace_sessions(
            run_id="run-1",
            session_id="session-1",
            user_id="attacker-choice",
            agent_id="agent-1",
            status="ERROR",
            start_time="2026-02-12T00:00:00Z",
            end_time="2026-02-12T23:59:59Z",
            limit=25,
            page=2,
            user=actor("u1"),
        )
    assert result["page"] == 2
    assert captured["run_id"] == "run-1"
    assert captured["session_id"] == "session-1"
    assert captured["user_id"] == "u1"
    assert captured["agent_id"] == "agent-1"
    assert captured["status"] == "ERROR"
    assert captured["start_time"] == "2026-02-12T00:00:00Z"
    assert captured["end_time"] == "2026-02-12T23:59:59Z"


@pytest.mark.asyncio
async def test_trace_sessions_group_before_paginating_and_skip_empty_session_ids():
    class FakeTrace:
        def __init__(self, **data):
            self.data = data

        def to_dict(self):
            return self.data

    traces = [
        FakeTrace(trace_id="empty", session_id=None, run_id="empty", start_time="2026-02-04T00:00:00Z"),
        FakeTrace(trace_id="one-a", session_id="one", run_id="run-1", status="OK", start_time="2026-02-03T00:00:00Z"),
        FakeTrace(trace_id="one-b", session_id="one", run_id="run-1", status="ERROR", start_time="2026-02-05T00:00:00Z"),
        FakeTrace(trace_id="two", session_id="two", run_id="run-2", status="OK", start_time="2026-02-04T00:00:00Z"),
    ]
    captured: dict[str, object] = {}

    async def fake_get_traces(**kwargs):
        captured.update(kwargs)
        return traces, len(traces)

    with patch.object(tracing_service._trace_db, "get_traces", fake_get_traces):
        result = await tracing_service.list_trace_sessions(
            run_id="run-1", session_id="one", user_id="u1", status="ERROR", limit=1, page=1
        )
    assert result["total_count"] == 1
    assert result["items"][0]["session_id"] == "one"
    assert result["items"][0]["trace_count"] == 1
    assert result["items"][0]["run_count"] == 1
    assert result["items"][0]["status"] == "ERROR"
    assert captured["user_id"] == "u1"
    assert captured["run_id"] == "run-1"
    assert captured["session_id"] == "one"
    assert captured["limit"] == 200


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
    assert "status" not in captured
    assert captured["start_time"] == datetime(2026, 2, 12, 0, 0, tzinfo=timezone.utc)
    assert captured["end_time"] == datetime(
        2026, 2, 12, 23, 59, 59, tzinfo=timezone.utc
    )
    assert captured["limit"] == 200
    assert captured["page"] == 1


@pytest.mark.asyncio
async def test_list_traces_filters_after_audit_status_reconciliation() -> None:
    trace_record = SimpleNamespace(
        to_dict=lambda: {
            "trace_id": "trace-1",
            "run_id": "run-failed",
            "user_id": "u1",
            "status": "OK",
        }
    )

    async def fake_get_traces(**_kwargs):
        return [trace_record], 1

    async def fake_reconcile(items, **_kwargs):
        return [{**items[0], "status": "ERROR"}]

    with (
        patch.object(tracing_service._trace_db, "get_traces", fake_get_traces),
        patch.object(tracing_service, "reconcile_trace_statuses", fake_reconcile),
    ):
        result = await tracing_service.list_traces(user_id="u1", status="ERROR")

    assert result["total_count"] == 1
    assert result["items"][0]["status"] == "ERROR"


@pytest.mark.asyncio
async def test_trace_detail_uses_reconciled_terminal_status() -> None:
    trace_record = SimpleNamespace(
        to_dict=lambda: {
            "trace_id": "trace-1",
            "run_id": "run-failed",
            "user_id": "owner",
            "status": "OK",
        }
    )

    async def fake_reconcile(items, **_kwargs):
        return [{**items[0], "status": "ERROR"}]

    with (
        patch.object(tracing_service._trace_db, "get_trace", AsyncMock(return_value=trace_record)),
        patch.object(tracing_service._trace_db, "get_spans", AsyncMock(return_value=[])),
        patch.object(tracing_service, "reconcile_trace_statuses", fake_reconcile),
    ):
        result = await get_trace_detail("trace-1", actor=actor("owner"))

    assert result is not None
    assert result["trace"]["status"] == "ERROR"


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
    assert parsed["output"]["format"] == "json"
    assert parsed["metadata"]["model"] == "gpt-5.2"
    assert parsed["metadata"]["tokens"]["prompt"] == 31
    assert parsed["events"]


def test_span_tree_is_stable_and_degrades_duplicate_or_invalid_parent_links() -> None:
    spans = [
        {"span_id": "child", "parent_span_id": "root", "start_time": "2026-01-01T00:00:02Z"},
        {"span_id": "root", "start_time": "2026-01-01T00:00:01Z"},
        {"span_id": "duplicate", "start_time": "2026-01-01T00:00:05Z"},
        {"span_id": "duplicate", "parent_span_id": "root", "start_time": "2026-01-01T00:00:04Z"},
        {"span_id": "orphan", "parent_span_id": "missing", "start_time": "2026-01-01T00:00:03Z"},
        {"span_id": "self", "parent_span_id": "self", "start_time": "2026-01-01T00:00:06Z"},
        {"span_id": "a", "parent_span_id": "b", "start_time": "2026-01-01T00:00:08Z"},
        {"span_id": "b", "parent_span_id": "a", "start_time": "2026-01-01T00:00:07Z"},
    ]

    tree = _build_span_tree(spans)
    root_ids = [node["span"]["span_id"] for node in tree]
    assert root_ids == ["root", "orphan", "duplicate", "duplicate", "self", "b", "a"]
    assert [node["span"]["span_id"] for node in tree[0]["children"]] == ["child"]


@pytest.mark.asyncio
async def test_trace_detail_checks_ownership_before_querying_spans() -> None:
    trace_record = SimpleNamespace(to_dict=lambda: {"trace_id": "trace-1", "user_id": "owner"})
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
async def test_trace_detail_requests_all_spans_and_marks_response_complete() -> None:
    trace_record = SimpleNamespace(
        to_dict=lambda: {"trace_id": "trace-1", "user_id": "owner", "session_id": "s", "run_id": "r"}
    )
    span_record = SimpleNamespace(
        to_dict=lambda: {"span_id": "span-1", "name": "root", "attributes": {}}
    )
    captured: dict[str, object] = {}

    async def fake_get_trace(**kwargs):
        return trace_record

    async def fake_get_spans(**kwargs):
        captured.update(kwargs)
        return [span_record]

    with (
        patch.object(tracing_service._trace_db, "get_trace", fake_get_trace),
        patch.object(tracing_service._trace_db, "get_spans", fake_get_spans),
        patch.object(tracing_service._trace_db, "get_session", AsyncMock(return_value=None)),
    ):
        result = await get_trace_detail("trace-1", actor=actor("owner"))

    assert captured == {"trace_id": "trace-1", "limit": None}
    assert result is not None
    assert result["spans_complete"] is True
    assert result["span_count"] == 1


@pytest.mark.asyncio
async def test_trace_detail_enriches_empty_agent_root_from_chat_run() -> None:
    trace_record = SimpleNamespace(
        to_dict=lambda: {
            "trace_id": "trace-1",
            "user_id": "owner",
            "session_id": "session-1",
            "run_id": "run-1",
            "status": "OK",
        }
    )
    root_span = SimpleNamespace(
        to_dict=lambda: {
            "span_id": "root",
            "parent_span_id": None,
            "status_code": "UNSET",
            "attributes": {},
        }
    )
    session = {"runs": [{"run_id": "run-1", "content": "final response"}]}

    with (
        patch.object(tracing_service._trace_db, "get_trace", AsyncMock(return_value=trace_record)),
        patch.object(tracing_service._trace_db, "get_spans", AsyncMock(return_value=[root_span])),
        patch.object(tracing_service._trace_db, "get_session", AsyncMock(return_value=session)),
    ):
        result = await get_trace_detail("trace-1", actor=actor("owner"))

    assert result is not None
    root = result["spans"][0]
    assert root["status_code"] == "OK"
    assert root["parsed"]["output"] == {
        "format": "text",
        "text": "final response",
        "data": None,
    }


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
