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
        return {"data": [], "meta": {"page": 1, "limit": 20, "total_pages": 0, "total_count": 0, "search_time_ms": 0.0}}

    with patch.object(trace, "list_traces", fake_list_traces):
        result = await trace.api_list_traces(
            session_id="session-1", user_id="attacker-choice", user=actor("u1")
        )
    assert result["data"] == []
    assert captured["user_id"] == "u1"
    assert captured["session_id"] == "session-1"


@pytest.mark.asyncio
async def test_trace_list_passes_all_filters_to_service():
    captured: dict[str, object] = {}

    async def fake_list_traces(**kwargs):
        captured.update(kwargs)
        return {
            "data": [],
            "meta": {
                "page": kwargs["page"],
                "limit": kwargs["limit"],
                "total_pages": 0,
                "total_count": 0,
                "search_time_ms": 0.0,
            },
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
    assert result["meta"]["page"] == 3
    assert result["meta"]["limit"] == 50
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
        return {
            "data": [],
            "meta": {
                "page": kwargs["page"],
                "limit": kwargs["limit"],
                "total_pages": 0,
                "total_count": 0,
                "search_time_ms": 0.0,
            },
        }

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
    assert result["meta"]["page"] == 2
    assert result["meta"]["limit"] == 25
    assert captured["run_id"] == "run-1"
    assert captured["session_id"] == "session-1"
    assert captured["user_id"] == "u1"
    assert captured["agent_id"] == "agent-1"
    assert captured["status"] == "ERROR"
    assert captured["start_time"] == "2026-02-12T00:00:00Z"
    assert captured["end_time"] == "2026-02-12T23:59:59Z"


@pytest.mark.asyncio
async def test_trace_sessions_scan_fallback_groups_before_paginating():
    """When SQL grouping fails, fall back to bounded get_traces scan + Python group."""

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

    with (
        patch.object(
            tracing_service,
            "_list_trace_sessions_sql",
            AsyncMock(side_effect=RuntimeError("force fallback")),
        ),
        patch.object(tracing_service._trace_db, "get_traces", fake_get_traces),
    ):
        result = await tracing_service.list_trace_sessions(
            run_id="run-1", session_id="one", user_id="u1", status="ERROR", limit=1, page=1
        )
    assert result["meta"]["total_count"] == 1
    assert result["data"][0]["session_id"] == "one"
    assert result["data"][0]["trace_count"] == 1
    assert result["data"][0]["run_count"] == 1
    assert result["data"][0]["status"] == "ERROR"
    assert captured["user_id"] == "u1"
    assert captured["run_id"] == "run-1"
    assert captured["session_id"] == "one"
    assert captured["status"] == "ERROR"
    assert captured["limit"] == 200


@pytest.mark.asyncio
async def test_trace_sessions_sql_groups_with_aggregates_and_latest_row():
    """SQL path pages session aggregates and projects latest row fields."""

    class MappingResult:
        def __init__(self, *, scalar=None, rows=None):
            self._scalar = scalar
            self._rows = rows or []

        def scalar_one(self):
            return self._scalar

        def mappings(self):
            return self

        def all(self):
            return self._rows

    class FakeAsyncSession:
        def __init__(self, results):
            self._results = list(results)
            self.execute_count = 0

        async def execute(self, _stmt):
            self.execute_count += 1
            if not self._results:
                raise AssertionError("unexpected extra SQL execute")
            return self._results.pop(0)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    from sqlalchemy import Column, MetaData, String, Table

    meta = MetaData()
    table = Table(
        "agno_traces",
        meta,
        Column("session_id", String),
        Column("run_id", String),
        Column("trace_id", String),
        Column("name", String),
        Column("status", String),
        Column("start_time", String),
        Column("end_time", String),
        Column("user_id", String),
        Column("agent_id", String),
        Column("team_id", String),
        Column("workflow_id", String),
    )

    agg_row = {
        "session_id": "sess-a",
        "trace_count": 3,
        "run_count": 2,
        "error_count": 1,
        "latest_start_time": "2026-07-01T12:00:00Z",
    }
    latest_row = {
        "session_id": "sess-a",
        "trace_id": "tr-latest",
        "run_id": "run-latest",
        "name": "agent-run",
        "status": "OK",
        "start_time": "2026-07-01T12:00:00Z",
        "end_time": "2026-07-01T12:01:00Z",
        "user_id": "u1",
        "agent_id": "agent-1",
        "team_id": None,
        "workflow_id": None,
    }
    fake_session = FakeAsyncSession(
        [
            MappingResult(scalar=1),
            MappingResult(rows=[agg_row]),
            MappingResult(rows=[latest_row]),
        ]
    )

    async def fake_reconcile(items, **_kwargs):
        return items

    with (
        patch.object(
            tracing_service._trace_db,
            "_get_table",
            AsyncMock(return_value=table),
        ),
        patch.object(
            tracing_service._trace_db,
            "async_session_factory",
            lambda: fake_session,
        ),
        patch.object(
            tracing_service,
            "reconcile_trace_statuses",
            AsyncMock(side_effect=fake_reconcile),
        ),
    ):
        result = await tracing_service.list_trace_sessions(
            user_id="u1", status="ERROR", limit=20, page=1
        )

    assert result["meta"]["total_count"] == 1
    assert result["meta"]["page"] == 1
    assert result["meta"]["limit"] == 20
    assert len(result["data"]) == 1
    session = result["data"][0]
    assert session["session_id"] == "sess-a"
    assert session["trace_count"] == 3
    assert session["run_count"] == 2
    assert session["error_count"] == 1
    assert session["status"] == "ERROR"
    assert session["latest_trace_id"] == "tr-latest"
    assert session["latest_run_id"] == "run-latest"
    assert session["name"] == "agent-run"
    assert session["user_id"] == "u1"
    assert fake_session.execute_count == 3


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
    assert result == {"data": [], "meta": {"page": 2, "limit": 25, "total_pages": 0, "total_count": 0, "search_time_ms": 0.0}}
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
        patch.object(
            tracing_service,
            "_batch_root_spans_by_trace_ids",
            AsyncMock(return_value={"trace-1": []}),
        ),
        patch.object(tracing_service, "reconcile_trace_statuses", fake_reconcile),
    ):
        result = await tracing_service.list_traces(user_id="u1", status="ERROR")

    assert result["meta"]["total_count"] == 1
    assert result["data"][0]["status"] == "ERROR"
    assert result["data"][0]["duration"] == "0ms"
    assert "duration_ms" not in result["data"][0]


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
    assert result["spans"][0]["duration"] == "0ms"
    assert "duration_ms" not in result["spans"][0]
    assert "duration_ms" not in result["trace"]
    assert result["trace"]["duration"] == "0ms"


@pytest.mark.asyncio
async def test_trace_detail_prefers_final_chat_run_over_partial_agent_root() -> None:
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
            "status_code": "OK",
            "attributes": {"output.value": "partial response before approval"},
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


@pytest.mark.asyncio
async def test_trace_detail_replaces_pause_placeholder_with_tool_result() -> None:
    trace_record = SimpleNamespace(
        to_dict=lambda: {
            "trace_id": "trace-hitl",
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
            "status_code": "OK",
            "attributes": {
                "input.value": "block test@test.com",
                "output.value": "I have tools to execute, but I need confirmation.",
            },
        }
    )
    session = {
        "runs": [
            {
                "run_id": "run-1",
                "status": "COMPLETED",
                "content": "## HITL 模拟处置已提交\n\n- **状态**：**等待管理员审批**。",
                "tools": [
                    {
                        "tool_name": "simulate_containment",
                        "confirmed": True,
                        "tool_args": {"target": "test@test.com", "action": "block"},
                        "result": {
                            "status": "simulated",
                            "target": "test@test.com",
                            "action": "block",
                            "message": "Approval resolved and simulated containment recorded. No external system was changed.",
                        },
                    }
                ],
            }
        ]
    }

    with (
        patch.object(tracing_service._trace_db, "get_trace", AsyncMock(return_value=trace_record)),
        patch.object(tracing_service._trace_db, "get_spans", AsyncMock(return_value=[root_span])),
        patch.object(tracing_service._trace_db, "get_session", AsyncMock(return_value=session)),
    ):
        result = await get_trace_detail("trace-hitl", actor=actor("owner"))

    assert result is not None
    root = result["spans"][0]
    output_text = root["parsed"]["output"]["text"]
    assert "I have tools to execute, but I need confirmation." not in output_text
    assert "simulate_containment" in output_text
    assert "simulated" in output_text


@pytest.mark.asyncio
async def test_list_traces_native_envelope_duration_and_input() -> None:
    trace_record = SimpleNamespace(
        to_dict=lambda: {
            "trace_id": "trace-1",
            "name": "agent.run",
            "run_id": "run-1",
            "user_id": "u1",
            "status": "OK",
            "duration_ms": 1500,
        }
    )

    async def fake_get_traces(**_kwargs):
        return [trace_record], 1

    async def fake_batch_root_spans(trace_ids):
        assert list(trace_ids) == ["trace-1"]
        return {
            "trace-1": [
                {
                    "parent_span_id": None,
                    "attributes": {"input.value": "inspect host 10.0.0.1"},
                }
            ]
        }

    async def fake_reconcile(items, **_kwargs):
        return list(items)

    get_spans = AsyncMock(return_value=[])
    with (
        patch.object(tracing_service._trace_db, "get_traces", fake_get_traces),
        patch.object(tracing_service, "_batch_root_spans_by_trace_ids", fake_batch_root_spans),
        patch.object(tracing_service._trace_db, "get_spans", get_spans),
        patch.object(tracing_service, "reconcile_trace_statuses", fake_reconcile),
    ):
        result = await tracing_service.list_traces(user_id="u1", page=1, limit=20)

    assert set(result.keys()) == {"data", "meta"}
    assert result["meta"]["page"] == 1
    assert result["meta"]["limit"] == 20
    assert result["meta"]["total_count"] == 1
    assert result["meta"]["total_pages"] == 1
    assert "items" not in result
    assert result["data"][0]["trace_id"] == "trace-1"
    assert "duration_ms" not in result["data"][0]
    assert result["data"][0]["duration"] == "1.50s"
    assert result["data"][0]["input"] == "inspect host 10.0.0.1"
    get_spans.assert_not_called()


@pytest.mark.asyncio
async def test_list_traces_batches_root_inputs_for_page() -> None:
    traces = [
        SimpleNamespace(
            to_dict=lambda tid=tid: {
                "trace_id": tid,
                "name": "agent.run",
                "user_id": "u1",
                "status": "OK",
                "duration_ms": 100,
            }
        )
        for tid in ("trace-a", "trace-b")
    ]
    batch_calls: list[list[str]] = []

    async def fake_get_traces(**_kwargs):
        return traces, 2

    async def fake_batch_root_spans(trace_ids):
        batch_calls.append(list(trace_ids))
        return {
            "trace-a": [
                {"parent_span_id": None, "attributes": {"input.value": "prompt a"}},
            ],
            "trace-b": [
                {"parent_span_id": None, "attributes": {"input.value": "prompt b"}},
            ],
        }

    async def fake_reconcile(items, **_kwargs):
        return list(items)

    get_spans = AsyncMock(side_effect=AssertionError("list path must not N+1 get_spans"))
    with (
        patch.object(tracing_service._trace_db, "get_traces", fake_get_traces),
        patch.object(tracing_service, "_batch_root_spans_by_trace_ids", fake_batch_root_spans),
        patch.object(tracing_service._trace_db, "get_spans", get_spans),
        patch.object(tracing_service, "reconcile_trace_statuses", fake_reconcile),
    ):
        result = await tracing_service.list_traces(user_id="u1", page=1, limit=20)

    assert batch_calls == [["trace-a", "trace-b"]]
    assert [row["input"] for row in result["data"]] == ["prompt a", "prompt b"]
    get_spans.assert_not_called()


@pytest.mark.asyncio
async def test_root_inputs_leave_null_when_batch_fails() -> None:
    get_spans = AsyncMock(return_value=[])

    with (
        patch.object(
            tracing_service,
            "_batch_root_spans_by_trace_ids",
            AsyncMock(side_effect=RuntimeError("db down")),
        ),
        patch.object(tracing_service._trace_db, "get_spans", get_spans),
    ):
        inputs = await tracing_service._root_inputs_for_trace_ids(["trace-1", "trace-2"])

    assert inputs == {"trace-1": None, "trace-2": None}
    get_spans.assert_not_called()


@pytest.mark.asyncio
async def test_list_traces_passes_status_to_agno_native_filter() -> None:
    """ERROR/OK filters use Agno SQL status pagination, not a client-side scan."""
    class FakeTrace:
        def __init__(self, **data):
            self.data = data

        def to_dict(self):
            return self.data

    captured: list[dict[str, object]] = []

    async def fake_get_traces(**kwargs):
        captured.append(kwargs)
        return [
            FakeTrace(trace_id="err-1", run_id="r-err", status="ERROR", session_id="s1"),
        ], 42

    async def fake_reconcile(items, *, actor_user_id=None):
        return list(items)

    async def fake_inputs(items):
        return items

    with (
        patch.object(tracing_service._trace_db, "get_traces", fake_get_traces),
        patch.object(tracing_service, "reconcile_trace_statuses", fake_reconcile),
        patch.object(tracing_service, "_attach_list_inputs", fake_inputs),
        patch.object(
            tracing_service,
            "_merge_audit_error_traces",
            AsyncMock(side_effect=lambda items, **_kwargs: (items, 42)),
        ),
    ):
        result = await tracing_service.list_traces(
            user_id="u1", status="ERROR", page=2, limit=10
        )

    assert captured[0]["status"] == "ERROR"
    assert captured[0]["page"] == 2
    assert captured[0]["limit"] == 10
    assert [item["trace_id"] for item in result["data"]] == ["err-1"]
    assert result["meta"]["total_count"] == 42
    assert "truncated" not in result["meta"]


@pytest.mark.asyncio
async def test_list_traces_error_filter_supplements_audit_failures() -> None:
    class FakeTrace:
        def __init__(self, **data):
            self.data = data

        def to_dict(self):
            return self.data

    async def fake_get_traces(**kwargs):
        assert kwargs.get("status") == "ERROR"
        return [
            FakeTrace(trace_id="err-db", run_id="run-db", status="ERROR", session_id="s1"),
        ], 1

    async def fake_get_trace(*, run_id: str):
        assert run_id == "run-audit"
        return FakeTrace(
            trace_id="err-audit",
            run_id="run-audit",
            status="OK",
            session_id="s1",
            user_id="u1",
            start_time="2026-07-12T12:00:00Z",
        )

    async def fake_reconcile(items, *, actor_user_id=None):
        return list(items)

    async def fake_inputs(items):
        return items

    with (
        patch.object(tracing_service._trace_db, "get_traces", fake_get_traces),
        patch.object(tracing_service._trace_db, "get_trace", fake_get_trace),
        patch.object(tracing_service, "reconcile_trace_statuses", fake_reconcile),
        patch.object(tracing_service, "_attach_list_inputs", fake_inputs),
        patch(
            "api.persistence.audit_logs.recent_failed_chat_run_ids_async",
            AsyncMock(return_value=["run-audit"]),
        ),
    ):
        result = await tracing_service.list_traces(user_id="u1", status="ERROR", page=1, limit=20)

    ids = [item["trace_id"] for item in result["data"]]
    assert "err-db" in ids
    assert "err-audit" in ids
    assert all(item["status"] == "ERROR" for item in result["data"])
