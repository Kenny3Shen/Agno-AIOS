from types import SimpleNamespace

import pytest
from sqlalchemy import Column, MetaData, String, Table, create_engine

from api.services import tracing_service


@pytest.mark.asyncio
async def test_span_reflection_reuses_a_complete_cache() -> None:
    table = Table(
        "agno_spans",
        MetaData(),
        *(
            Column(column, String)
            for column in tracing_service._TRACE_QUERY_SPAN_COLUMNS
        ),
    )

    async def unexpected_table_lookup(*_args, **_kwargs):
        raise AssertionError("complete reflection should not be reloaded")

    db = SimpleNamespace(spans_table=table, _get_table=unexpected_table_lookup)

    assert await tracing_service._ensure_trace_span_reflection(db) is table


@pytest.mark.asyncio
async def test_span_reflection_reloads_stale_metadata() -> None:
    engine = create_engine("sqlite://")
    physical_metadata = MetaData()
    Table(
        "agno_spans",
        physical_metadata,
        *(
            Column(column, String)
            for column in tracing_service._TRACE_QUERY_SPAN_COLUMNS
        ),
    )
    physical_metadata.create_all(engine)

    stale_metadata = MetaData()
    stale = Table("agno_spans", stale_metadata, Column("trace_id", String))

    class AsyncConnection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def run_sync(self, callback):
            with engine.connect() as connection:
                return callback(connection)

    async def get_stale_table(*_args, **_kwargs):
        return stale

    db = SimpleNamespace(
        db_schema=None,
        span_table_name="agno_spans",
        metadata=stale_metadata,
        spans_table=stale,
        db_engine=SimpleNamespace(connect=AsyncConnection),
        _get_table=get_stale_table,
    )

    try:
        refreshed = await tracing_service._ensure_trace_span_reflection(db)
    finally:
        engine.dispose()

    assert refreshed is stale
    assert tracing_service._TRACE_QUERY_SPAN_COLUMNS.issubset(refreshed.c.keys())
