"""Critical business tests for runtime overview aggregation and scoping."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.auth import claims
from api.routes import overview
from api.services import overview_service
from api.tests.route_fakes import route_dependency


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


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
    failed_only = [trace for trace in traces if trace.get("status") == "ERROR"]
    with (
        patch.object(
            overview_service,
            "_fetch_traces",
            AsyncMock(
                return_value=(
                    traces,
                    {
                        "sample_size": len(traces),
                        "window_total": len(traces),
                        "truncated": False,
                    },
                )
            ),
        ) as fetch,
        patch.object(
            overview_service, "_safe_sql_window_latency", AsyncMock(return_value=None)
        ),
        patch.object(
            overview_service, "_safe_sql_series", AsyncMock(return_value=None)
        ),
        patch.object(
            overview_service, "_safe_sql_distributions", AsyncMock(return_value=None)
        ),
        patch.object(overview_service, "_count_traces", AsyncMock(return_value=1)),
        patch.object(
            overview_service, "_fetch_recent_failures", AsyncMock(return_value=failed_only)
        ),
        patch.object(
            overview_service, "_snapshots", AsyncMock(return_value={"memories": 3})
        ),
        patch.object(
            overview_service,
            "_fetch_span_token_counts",
            AsyncMock(
                return_value={
                    "ok-1": {
                        "input_tokens": 7,
                        "output_tokens": 5,
                        "total_tokens": 12,
                    },
                    "failed-1": {
                        "input_tokens": 3,
                        "output_tokens": 5,
                        "total_tokens": 8,
                    },
                }
            ),
        ),
    ):
        result = await overview_service.get_runtime_overview(
            actor("u1"),
            range_name="24h",
            timezone="UTC",
            now=datetime(2026, 7, 12, 12, tzinfo=UTC),
        )

    assert fetch.await_args is not None
    assert fetch.await_args.kwargs["user_id"] == "u1"
    assert result["health"] == {"status": "ready"}
    assert result["metrics"]["total_runs"] == 2
    assert result["metrics"]["failed_runs"] == 1
    assert result["metrics"]["input_tokens"] == 10
    assert result["metrics"]["total_tokens"] == 20
    assert result["distributions"]["agent"] == [
        {"name": "security-agent", "value": 1}
    ]
    assert result["recent_failures"][0]["trace_id"] == "failed-1"
    assert result["snapshots"] == {"memories": 3}


def test_overview_route_enforces_trace_scope(monkeypatch):
    monkeypatch.setitem(claims.ROLE_SCOPES, "user", set())
    with pytest.raises(HTTPException) as exc:
        route_dependency(overview.router, "get_overview")(user=actor("u1"))
    assert exc.value.status_code == 403


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
async def test_overview_rejects_invalid_custom_ranges(
    range_name, start_time, end_time, message
):
    with pytest.raises(ValueError, match=message):
        await overview_service.get_runtime_overview(
            actor("u1"),
            range_name=range_name,
            start_time=start_time,
            end_time=end_time,
        )


@pytest.mark.asyncio
async def test_overview_uses_window_error_count():
    sample = [
        {
            "trace_id": "ok-sample",
            "start_time": "2026-07-12T11:10:00+00:00",
            "status": "OK",
            "duration_ms": 100,
        },
    ]
    remote_failure = {
        "trace_id": "err-remote",
        "run_id": "run-x",
        "start_time": "2026-07-12T10:00:00+00:00",
        "status": "ERROR",
        "duration_ms": 50,
    }
    with (
        patch.object(
            overview_service,
            "_fetch_traces",
            AsyncMock(
                return_value=(
                    sample,
                    {"sample_size": 1, "window_total": 100, "truncated": True},
                )
            ),
        ),
        patch.object(
            overview_service, "_safe_sql_window_latency", AsyncMock(return_value=None)
        ),
        patch.object(
            overview_service, "_safe_sql_series", AsyncMock(return_value=None)
        ),
        patch.object(
            overview_service, "_safe_sql_distributions", AsyncMock(return_value=None)
        ),
        patch.object(
            overview_service, "_count_traces", AsyncMock(return_value=17)
        ) as count_errors,
        patch.object(
            overview_service,
            "_fetch_recent_failures",
            AsyncMock(return_value=[remote_failure]),
        ),
        patch.object(
            overview_service, "_fetch_span_token_counts", AsyncMock(return_value={})
        ),
        patch.object(overview_service, "_snapshots", AsyncMock(return_value={})),
    ):
        result = await overview_service.get_runtime_overview(
            actor("u1"),
            range_name="24h",
            timezone="UTC",
            now=datetime(2026, 7, 12, 12, tzinfo=UTC),
        )

    assert count_errors.await_args is not None
    assert count_errors.await_args.kwargs["status"] == "ERROR"
    assert result["metrics"]["total_runs"] == 100
    assert result["metrics"]["failed_runs"] == 17
    assert result["metrics"]["failure_rate"] == 0.17
    assert result["metrics"]["truncated"] is True
    assert result["recent_failures"][0]["trace_id"] == "err-remote"


@pytest.mark.asyncio
async def test_overview_token_sample_stops_at_first_page_when_window_exceeds_cap():
    calls: list[int] = []

    async def get_traces(**kwargs):
        calls.append(kwargs["page"])
        if kwargs["page"] == 1:
            return [{"trace_id": "first"}], 1_001
        return [{"trace_id": "second"}], 1_001

    with patch.object(
        overview_service.get_async_agno_postgres_db(), "get_traces", get_traces
    ):
        traces, meta = await overview_service._fetch_traces(
            start=datetime(2026, 7, 12, 11, tzinfo=UTC),
            end=datetime(2026, 7, 12, 12, tzinfo=UTC),
            user_id="u1",
        )

    assert calls == [1]
    assert [trace["trace_id"] for trace in traces] == ["first"]
    assert meta == {"sample_size": 1, "window_total": 1001, "truncated": True}
