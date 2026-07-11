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
        if isinstance(route, APIRoute) and route.endpoint.__name__ == "get_overview":
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
            "attributes": {"gen_ai.usage.total_tokens": 12},
        },
        {
            "trace_id": "failed-1",
            "run_id": "run-2",
            "start_time": "2026-07-12T11:30:00+00:00",
            "duration_ms": 300,
            "status": "ERROR",
            "workflow_id": "triage",
            "total_tokens": 8,
        },
    ]
    with (
        patch.object(overview_service, "_fetch_traces", AsyncMock(return_value=traces)) as fetch,
        patch.object(overview_service, "_snapshots", AsyncMock(return_value={"memories": 3})),
    ):
        result = await overview_service.get_runtime_overview(
            actor("u1"),
            range_name="24h",
            timezone="UTC",
            now=datetime(2026, 7, 12, 12, tzinfo=UTC),
        )

    assert fetch.await_args.kwargs["user_id"] == "u1"
    assert result["health"] == {"status": "ready"}
    assert result["metrics"] == {
        "total_runs": 2,
        "failed_runs": 1,
        "failure_rate": 0.5,
        "p50_duration_ms": 200.0,
        "p95_duration_ms": 290.0,
        "total_tokens": 20,
    }
    assert [item["runs"] for item in result["series"]] == [2]
    assert result["distributions"]["agent"] == [{"name": "security-agent", "value": 1}]
    assert result["recent_failures"][0]["trace_id"] == "failed-1"
    assert result["snapshots"] == {"memories": 3}
    assert "audit" not in result


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
            "total": 4,
            "items": [
                {"passed": True},
                {"passed": False},
                {"passed": None},
            ],
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
        result = await overview.get_overview(range_name="7d", timezone="Asia/Shanghai", user=actor("u1"))
    assert result == {"range": "7d"}
    assert mocked.await_args.args[0].id == "u1"
    assert mocked.await_args.kwargs == {"range_name": "7d", "timezone": "Asia/Shanghai"}


@pytest.mark.asyncio
async def test_overview_rejects_invalid_timezone():
    with pytest.raises(ValueError):
        await overview_service.get_runtime_overview(actor("u1"), timezone="not/a-timezone")
