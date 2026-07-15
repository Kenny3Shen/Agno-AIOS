from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from api.auth import claims
from api.routes import overview
from api.services import overview_service


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


def route_dependency():
    for route in overview.router.routes:
        if isinstance(route, APIRoute) and getattr(route.endpoint, "__name__", "") == "get_overview":
            return route.dependant.dependencies[0].call
    raise AssertionError("missing overview route")


@pytest.mark.asyncio
async def test_overview_aggregates_scoped_traces_into_stable_payload():
    traces = [
        {
            "trace_id": "ok-1",
            "start_time": "2026-07-12T11:10:00+00:00",
            "end_time": "2026-07-12T11:10:00.100000+00:00",
            "status": "OK",
            "agent_id": "security-agent",
            "attributes": {
                "gen_ai.usage.prompt_tokens": 7,
                "gen_ai.usage.completion_tokens": 5,
            },
        },
        {
            "trace_id": "failed-1",
            "run_id": "run-2",
            "start_time": "2026-07-12T11:30:00+00:00",
            "duration_ms": 300,
            "status": "ERROR",
            "workflow_id": "triage",
            "metadata": {"tokens": {"input": 3, "output": 5}},
        },
    ]
    with (
        patch.object(overview_service, "_fetch_traces", AsyncMock(return_value=traces)) as fetch,
        patch.object(overview_service, "_snapshots", AsyncMock(return_value={"memories": 3})),
        patch.object(
            overview_service,
            "_fetch_span_token_counts",
            AsyncMock(return_value={
                "ok-1": {"input_tokens": 7, "output_tokens": 5, "total_tokens": 12},
                "failed-1": {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8},
            }),
        ) as fetch_span_tokens,
    ):
        result = await overview_service.get_runtime_overview(
            actor("u1"),
            range_name="24h",
            timezone="UTC",
            now=datetime(2026, 7, 12, 12, tzinfo=UTC),
        )

    assert fetch.await_args is not None
    assert fetch.await_args.kwargs["user_id"] == "u1"
    assert fetch_span_tokens.await_args is not None
    assert fetch_span_tokens.await_args.args[0] == ["ok-1", "failed-1"]
    assert result["health"] == {"status": "ready"}
    assert result["metrics"] == {
        "total_runs": 2,
        "failed_runs": 1,
        "failure_rate": 0.5,
        "p50_duration_ms": 200.0,
        "p95_duration_ms": 290.0,
        "input_tokens": 10,
        "output_tokens": 10,
        "total_tokens": 20,
    }
    assert [item["runs"] for item in result["series"]] == [2]
    assert result["series"][0] == {
        "timestamp": "2026-07-12T11:00:00+00:00",
        "bucket_end": "2026-07-12T12:00:00+00:00",
        "runs": 2,
        "failed_runs": 1,
        "p50_duration_ms": 200.0,
        "p95_duration_ms": 290.0,
        "input_tokens": 10,
        "output_tokens": 10,
        "total_tokens": 20,
        "tokens": 20,
    }
    assert result["distributions"]["agent"] == [{"name": "security-agent", "value": 1}]
    assert result["recent_failures"][0]["trace_id"] == "failed-1"
    assert result["snapshots"] == {"memories": 3}
    assert "audit" not in result


@pytest.mark.parametrize(
    ("trace", "expected"),
    [
        (
            {
                "attributes": {
                    "openinference.llm.token_count.prompt": 11,
                    "openinference.llm.token_count.completion": 4,
                }
            },
            {"input_tokens": 11, "output_tokens": 4, "total_tokens": 15},
        ),
        (
            {"metadata": {"gen_ai.usage.total_tokens": 9}},
            {"input_tokens": 0, "output_tokens": 0, "total_tokens": 9},
        ),
        ({}, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}),
    ],
)
def test_overview_extracts_token_aliases_and_falls_back_to_input_plus_output(trace, expected):
    assert overview_service._token_counts(trace) == expected


@pytest.mark.asyncio
async def test_overview_uses_span_usage_instead_of_empty_trace_rows():
    traces = [{
        "trace_id": "chat-run",
        "start_time": "2026-07-12T11:10:00+00:00",
        "end_time": "2026-07-12T11:10:01+00:00",
        "status": "OK",
        "attributes": {},
    }]
    with (
        patch.object(overview_service, "_fetch_traces", AsyncMock(return_value=traces)),
        patch.object(overview_service, "_snapshots", AsyncMock(return_value={})),
        patch.object(
            overview_service,
            "_fetch_span_token_counts",
            AsyncMock(return_value={"chat-run": {"input_tokens": 4219, "output_tokens": 157, "total_tokens": 4376}}),
        ),
    ):
        result = await overview_service.get_runtime_overview(
            actor("u1"), now=datetime(2026, 7, 12, 12, tzinfo=UTC),
        )

    assert result["metrics"]["input_tokens"] == 4219
    assert result["metrics"]["output_tokens"] == 157
    assert result["metrics"]["total_tokens"] == 4376
    assert result["series"][0]["total_tokens"] == 4376


@pytest.mark.asyncio
async def test_overview_uses_trace_database_time_and_owner_filter():
    captured: dict[str, object] = {}

    async def get_traces(**kwargs):
        captured.update(kwargs)
        return [], 0

    with patch.object(overview_service.get_async_agno_postgres_db(), "get_traces", get_traces):
        await overview_service._fetch_traces(
            start=datetime(2026, 7, 12, 11, tzinfo=UTC),
            end=datetime(2026, 7, 12, 12, tzinfo=UTC),
            user_id="u1",
        )
    assert captured["user_id"] == "u1"
    assert captured["limit"] == 1_000
    assert captured["page"] == 1


@pytest.mark.asyncio
async def test_overview_reads_every_trace_page_inside_the_selected_window():
    calls: list[int] = []

    async def get_traces(**kwargs):
        calls.append(kwargs["page"])
        if kwargs["page"] == 1:
            return [{"trace_id": "first"}], 1_001
        return [{"trace_id": "second"}], 1_001

    with patch.object(overview_service.get_async_agno_postgres_db(), "get_traces", get_traces):
        traces = await overview_service._fetch_traces(
            start=datetime(2026, 7, 12, 11, tzinfo=UTC),
            end=datetime(2026, 7, 12, 12, tzinfo=UTC),
            user_id="u1",
        )

    assert calls == [1, 2]
    assert [trace["trace_id"] for trace in traces] == ["first", "second"]


@pytest.mark.asyncio
async def test_overview_caps_trace_pages_when_window_is_huge():
    calls: list[int] = []

    async def get_traces(**kwargs):
        calls.append(kwargs["page"])
        return [{"trace_id": f"t{kwargs['page']}"}], 50_000

    with patch.object(overview_service.get_async_agno_postgres_db(), "get_traces", get_traces):
        traces = await overview_service._fetch_traces(
            start=datetime(2026, 7, 12, 11, tzinfo=UTC),
            end=datetime(2026, 7, 12, 12, tzinfo=UTC),
            user_id="u1",
        )

    assert calls == [1, 2, 3, 4, 5]
    assert len(traces) == 5


@pytest.mark.asyncio
async def test_overview_fetch_reconciles_audit_failures_before_metrics() -> None:
    trace = SimpleNamespace(
        to_dict=lambda: {"trace_id": "trace-1", "run_id": "run-1", "status": "OK"}
    )

    async def get_traces(**_kwargs):
        return [trace], 1

    reconcile = AsyncMock(
        return_value=[{"trace_id": "trace-1", "run_id": "run-1", "status": "ERROR"}]
    )
    with (
        patch.object(overview_service.get_async_agno_postgres_db(), "get_traces", get_traces),
        patch.object(overview_service, "reconcile_trace_statuses", reconcile),
    ):
        traces = await overview_service._fetch_traces(
            start=datetime(2026, 7, 12, 11, tzinfo=UTC),
            end=datetime(2026, 7, 12, 12, tzinfo=UTC),
            user_id="u1",
        )

    assert traces[0]["status"] == "ERROR"
    assert reconcile.await_args is not None
    assert reconcile.await_args.kwargs["actor_user_id"] == "u1"


@pytest.mark.asyncio
async def test_admin_overview_includes_audit_summary():
    with (
        patch.object(overview_service, "_fetch_traces", AsyncMock(return_value=[])),
        patch.object(overview_service, "_snapshots", AsyncMock(return_value={})),
        patch.object(
            overview_service,
            "_audit_summary",
            AsyncMock(return_value={"recent": [{"action": "auth.login"}], "top_actions": []}),
        ),
    ):
        result = await overview_service.get_runtime_overview(actor("a1", "admin"))
    assert result["audit"]["recent"][0]["action"] == "auth.login"


@pytest.mark.asyncio
async def test_overview_adds_evaluation_snapshot_for_authorized_actor(monkeypatch):
    async def fake_list_runs(*, limit: int, page: int):
        assert (limit, page) == (100, 1)
        return {
            "data": [
                {"passed": True},
                {"passed": False},
                {"passed": None},
            ],
            "meta": {
                "page": 1,
                "limit": 100,
                "total_pages": 1,
                "total_count": 4,
                "search_time_ms": 0.0,
            },
        }

    from api.services import agent_eval_result_service

    monkeypatch.setattr(agent_eval_result_service, "list_agno_eval_runs", fake_list_runs)
    snapshots = await overview_service._snapshots(actor("u1"))

    assert snapshots["evaluation"] == {
        "total": 4,
        "passed": 1,
        "failed": 1,
        "pass_rate": 0.5,
    }


def test_overview_route_enforces_trace_scope(monkeypatch):
    monkeypatch.setitem(claims.ROLE_SCOPES, "guest", set())
    with pytest.raises(HTTPException) as exc:
        route_dependency()(user=actor("g1", "guest"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_overview_route_passes_range_and_timezone_to_service():
    with patch.object(overview, "get_runtime_overview", AsyncMock(return_value={"range": "7d"})) as mocked:
        result = await overview.get_overview(
            range_name="7d",
            start_time=None,
            end_time=None,
            timezone="Asia/Shanghai",
            user=actor("u1"),
        )
    assert result == {"range": "7d"}
    assert mocked.await_args is not None
    assert mocked.await_args.args[0].id == "u1"
    assert mocked.await_args.kwargs == {
        "range_name": "7d",
        "start_time": None,
        "end_time": None,
        "timezone": "Asia/Shanghai",
    }


@pytest.mark.asyncio
async def test_overview_custom_range_uses_requested_window_and_adaptive_buckets():
    start = "2026-07-10T00:00:00+08:00"
    end = "2026-07-12T00:00:00+08:00"
    traces = [
        {"trace_id": "inside", "start_time": "2026-07-11T04:00:00+00:00", "status": "OK"},
    ]
    with (
        patch.object(overview_service, "_fetch_traces", AsyncMock(return_value=traces)) as fetch,
        patch.object(overview_service, "_fetch_span_token_counts", AsyncMock(return_value={})),
        patch.object(overview_service, "_snapshots", AsyncMock(return_value={})),
    ):
        result = await overview_service.get_runtime_overview(
            actor("u1"),
            range_name="custom",
            start_time=start,
            end_time=end,
            timezone="Asia/Shanghai",
            now=datetime(2026, 7, 12, 12, tzinfo=UTC),
        )

    assert fetch.await_args is not None
    assert fetch.await_args.kwargs["start"] == datetime(2026, 7, 9, 16, tzinfo=UTC)
    assert fetch.await_args.kwargs["end"] == datetime(2026, 7, 11, 16, tzinfo=UTC)
    assert result["range"] == "custom"
    assert result["start_time"] == "2026-07-09T16:00:00+00:00"
    assert result["end_time"] == "2026-07-11T16:00:00+00:00"
    assert result["series"][0]["timestamp"] == "2026-07-11T00:00:00+08:00"
    assert result["series"][0]["bucket_end"] == "2026-07-12T00:00:00+08:00"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("range_name", "start_time", "end_time", "message"),
    [
        ("custom", None, None, "required"),
        ("24h", "2026-07-12T00:00:00Z", None, "provided together"),
        ("24h", "2026-07-12T00:00:00Z", "2026-07-12T01:00:00Z", "only be used"),
        ("custom", "2026-07-12T00:00:00", "2026-07-12T01:00:00Z", "timezone"),
        ("custom", "2026-07-12T01:00:00Z", "2026-07-12T00:00:00Z", "earlier"),
    ],
)
async def test_overview_rejects_invalid_custom_ranges(range_name, start_time, end_time, message):
    with pytest.raises(ValueError, match=message):
        await overview_service.get_runtime_overview(
            actor("u1"), range_name=range_name, start_time=start_time, end_time=end_time
        )


@pytest.mark.asyncio
async def test_overview_route_passes_custom_range_to_service():
    with patch.object(overview, "get_runtime_overview", AsyncMock(return_value={})) as mocked:
        await overview.get_overview(
            range_name="custom",
            start_time="2026-07-11T00:00:00Z",
            end_time="2026-07-12T00:00:00Z",
            timezone="UTC",
            user=actor("u1"),
        )

    assert mocked.await_args is not None
    assert mocked.await_args.kwargs == {
        "range_name": "custom",
        "start_time": "2026-07-11T00:00:00Z",
        "end_time": "2026-07-12T00:00:00Z",
        "timezone": "UTC",
    }


@pytest.mark.asyncio
async def test_overview_rejects_invalid_timezone():
    with pytest.raises(ValueError):
        await overview_service.get_runtime_overview(actor("u1"), timezone="not/a-timezone")


@pytest.mark.asyncio
async def test_overview_adds_approval_status_snapshot_for_authorized_actor(monkeypatch):
    async def fake_counts(*, actor=None, user_id=None):
        return {"pending": 2, "approved": 4, "rejected": 1, "total": 7}

    from api.services import approvals_service

    monkeypatch.setattr(approvals_service, "get_approval_status_counts", fake_counts)
    snapshots = await overview_service._snapshots(actor("u1"))

    assert snapshots.get("approvals") == {
        "pending": 2,
        "approved": 4,
        "rejected": 1,
    }
    assert "pending_approvals" not in snapshots



@pytest.mark.asyncio
async def test_overview_snapshot_failures_are_logged(monkeypatch):
    class FakeDb:
        async def get_user_memories(self, **_kwargs):
            raise RuntimeError("memories down")

    logged: list[str] = []

    def fake_exception(message, *args, **_kwargs):
        logged.append(str(message).format(*args) if args else str(message))

    monkeypatch.setattr(overview_service, "get_async_agno_postgres_db", lambda: FakeDb())
    monkeypatch.setattr(
        overview_service,
        "has_scope",
        lambda _actor, scope: scope == "memories:read",
    )
    monkeypatch.setattr(overview_service.logger, "exception", fake_exception)

    snapshots = await overview_service._snapshots(actor("u1"))

    assert snapshots == {}
    assert any("overview snapshot failed: memories" in message for message in logged)
