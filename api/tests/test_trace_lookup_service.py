from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Column, MetaData, String, Table

from api.services import trace_lookup_service


@pytest.mark.asyncio
async def test_batch_traces_by_run_ids_empty() -> None:
    assert await trace_lookup_service.batch_traces_by_run_ids([]) == {}
    assert await trace_lookup_service.batch_traces_by_run_ids(["", "  "]) == {}


@pytest.mark.asyncio
async def test_batch_traces_by_run_ids_queries_distinct_newest() -> None:
    mapping_rows = [
        {"run_id": "r1", "trace_id": "t1", "start_time": "2026-07-12T10:00:00+00:00"},
        {"run_id": "r2", "trace_id": "t2", "start_time": "2026-07-12T11:00:00+00:00"},
    ]

    class _Result:
        def mappings(self):
            return mapping_rows

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Result())
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    table = Table(
        "agno_traces",
        MetaData(),
        Column("run_id", String),
        Column("trace_id", String),
        Column("start_time", String),
    )

    db = MagicMock()
    db._get_table = AsyncMock(return_value=table)
    db.async_session_factory = MagicMock(return_value=session)

    with patch.object(trace_lookup_service, "get_async_agno_postgres_db", return_value=db):
        result = await trace_lookup_service.batch_traces_by_run_ids(["r1", "r2", "r1"])

    assert set(result) == {"r1", "r2"}
    assert result["r1"]["trace_id"] == "t1"
    session.execute.assert_awaited()


@pytest.mark.asyncio
async def test_batch_traces_by_run_ids_missing_table() -> None:
    db = MagicMock()
    db._get_table = AsyncMock(return_value=None)
    with patch.object(trace_lookup_service, "get_async_agno_postgres_db", return_value=db):
        assert await trace_lookup_service.batch_traces_by_run_ids(["r1"]) == {}
