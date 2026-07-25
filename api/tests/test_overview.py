"""Critical business tests for runtime overview aggregation and scoping."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from sqlalchemy import BigInteger, Column, MetaData, String, Table, create_engine

from api.auth import claims
from api.routes import overview
from api.services import overview_service
from api.tests.route_fakes import route_dependency
from api.utils.ttl_cache import AsyncTtlCache


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


def trace_sql_table(*columns: str) -> Table:
    """Build only the columns needed to exercise overview SQL guards."""
    column_types = {
        "duration_ms": BigInteger,
    }
    return Table(
        "agno_traces",
        MetaData(),
        *(Column(column, column_types.get(column, String)) for column in columns),
    )


@pytest.mark.asyncio
async def test_overview_cache_coalesces_same_scope_request_and_copies_payload(monkeypatch):
    cache: AsyncTtlCache[object, dict[str, object]] = AsyncTtlCache(ttl_sec=5.0)
    monkeypatch.setattr(overview_service, "_OVERVIEW_CACHE", cache)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def build(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"metrics": {"total_runs": calls}}

    monkeypatch.setattr(overview_service, "_build_runtime_overview", build)
    current_actor = actor("u1")
    first = asyncio.create_task(
        overview_service.get_runtime_overview(current_actor, range_name="24h", timezone="UTC")
    )
    await started.wait()
    second = asyncio.create_task(
        overview_service.get_runtime_overview(current_actor, range_name="24h", timezone="UTC")
    )
    await asyncio.sleep(0)
    assert calls == 1

    release.set()
    first_result, second_result = await asyncio.gather(first, second)
    assert first_result == second_result == {"metrics": {"total_runs": 1}}
    assert first_result is not second_result
    first_result["metrics"]["total_runs"] = 999  # type: ignore[index]

    cached = await overview_service.get_runtime_overview(
        current_actor,
        range_name="24h",
        timezone="UTC",
    )
    assert cached == {"metrics": {"total_runs": 1}}
    assert calls == 1


@pytest.mark.asyncio
async def test_overview_cache_key_isolates_actor_range_and_timezone(monkeypatch):
    cache: AsyncTtlCache[object, dict[str, object]] = AsyncTtlCache(ttl_sec=5.0)
    monkeypatch.setattr(overview_service, "_OVERVIEW_CACHE", cache)
    calls: list[tuple[str, str, str]] = []

    async def build(current_actor, *, range_name, display_timezone, **_kwargs):
        calls.append((str(current_actor.id), range_name, str(display_timezone)))
        return {"call": len(calls)}

    monkeypatch.setattr(overview_service, "_build_runtime_overview", build)
    first_actor = actor("u1")
    second_actor = actor("u2")
    assert await overview_service.get_runtime_overview(first_actor) == {"call": 1}
    assert await overview_service.get_runtime_overview(second_actor) == {"call": 2}
    assert await overview_service.get_runtime_overview(first_actor, range_name="1h") == {"call": 3}
    assert (
        await overview_service.get_runtime_overview(
            first_actor,
            timezone="Asia/Shanghai",
        )
    ) == {"call": 4}
    assert len(calls) == 4


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("aggregate", "kwargs", "required_columns"),
    [
        (
            overview_service._sql_window_latency,
            {
                "start": datetime(2026, 7, 12, 11, tzinfo=UTC),
                "end": datetime(2026, 7, 12, 12, tzinfo=UTC),
                "user_id": "u1",
            },
            frozenset({"start_time", "end_time", "duration_ms", "user_id"}),
        ),
        (
            overview_service._sql_series,
            {
                "start": datetime(2026, 7, 12, 11, tzinfo=UTC),
                "end": datetime(2026, 7, 12, 12, tzinfo=UTC),
                "user_id": "u1",
                "range_name": "1h",
                "timezone": ZoneInfo("UTC"),
            },
            frozenset({"start_time", "end_time", "duration_ms", "status", "user_id"}),
        ),
        (
            overview_service._sql_distributions,
            {
                "start": datetime(2026, 7, 12, 11, tzinfo=UTC),
                "end": datetime(2026, 7, 12, 12, tzinfo=UTC),
                "user_id": "u1",
            },
            frozenset({"start_time", "agent_id", "workflow_id", "team_id", "user_id"}),
        ),
    ],
)
async def test_sql_aggregates_skip_incomplete_trace_reflection(
    aggregate, kwargs, required_columns
):
    db = MagicMock()
    db._get_table = AsyncMock(return_value=trace_sql_table("trace_id"))
    refresh = AsyncMock(return_value=trace_sql_table("trace_id"))

    with (
        patch.object(overview_service, "get_async_agno_postgres_db", return_value=db),
        patch.object(overview_service, "_refresh_trace_table_reflection", refresh),
    ):
        result = await aggregate(**kwargs)

    assert result is None
    refresh.assert_awaited_once_with(db, required_columns=required_columns)
    db.async_session_factory.assert_not_called()


@pytest.mark.asyncio
async def test_trace_table_for_sql_refreshes_a_stale_reflection_once():
    required_columns = frozenset({"start_time", "end_time", "duration_ms", "user_id"})
    stale = trace_sql_table("trace_id")
    refreshed = trace_sql_table(*required_columns)
    db = MagicMock()
    db._get_table = AsyncMock(return_value=stale)
    refresh = AsyncMock(return_value=refreshed)

    with (
        patch.object(overview_service, "get_async_agno_postgres_db", return_value=db),
        patch.object(overview_service, "_refresh_trace_table_reflection", refresh),
    ):
        result_db, table = await overview_service._trace_table_for_sql(
            required_columns=required_columns
        )

    assert result_db is db
    assert table is refreshed
    refresh.assert_awaited_once_with(db, required_columns=required_columns)


@pytest.mark.asyncio
async def test_trace_table_for_sql_keeps_a_complete_reflection():
    required_columns = frozenset({"start_time", "end_time", "duration_ms", "user_id"})
    table = trace_sql_table(*required_columns)
    db = MagicMock()
    db._get_table = AsyncMock(return_value=table)
    refresh = AsyncMock()

    with (
        patch.object(overview_service, "get_async_agno_postgres_db", return_value=db),
        patch.object(overview_service, "_refresh_trace_table_reflection", refresh),
    ):
        result_db, result_table = await overview_service._trace_table_for_sql(
            required_columns=required_columns
        )

    assert result_db is db
    assert result_table is table
    refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_trace_table_reflection_reloads_cached_metadata():
    engine = create_engine("sqlite://")
    physical_metadata = MetaData()
    Table(
        "agno_traces",
        physical_metadata,
        Column("trace_id", String),
        Column("start_time", String),
        Column("end_time", String),
        Column("duration_ms", BigInteger),
        Column("user_id", String),
    )
    physical_metadata.create_all(engine)

    stale_metadata = MetaData()
    stale = Table("agno_traces", stale_metadata, Column("trace_id", String))

    class AsyncConnection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def run_sync(self, callback):
            with engine.connect() as connection:
                return callback(connection)

    db = SimpleNamespace(
        db_schema=None,
        trace_table_name="agno_traces",
        metadata=stale_metadata,
        traces_table=stale,
        db_engine=SimpleNamespace(connect=AsyncConnection),
    )
    required_columns = frozenset({"start_time", "end_time", "duration_ms", "user_id"})

    try:
        refreshed = await overview_service._refresh_trace_table_reflection(
            db, required_columns=required_columns
        )
    finally:
        engine.dispose()

    assert refreshed is stale
    assert required_columns.issubset(refreshed.c.keys())
