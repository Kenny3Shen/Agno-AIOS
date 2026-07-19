from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from starlette.requests import Request

from api.auth.models import User
from api.models.schemas import CveSearchRequest
from api.persistence import cves
from api.routes import cve as cve_routes
from api.tasks.update_cve import CVEUpdateAlreadyRunningError


def test_cve_search_request_allows_an_empty_query_for_recent_entries():
    request = CveSearchRequest(query="   ")

    assert request.query == ""


@pytest.mark.asyncio
async def test_search_cve_rows_builds_ranked_full_text_query_for_keywords():
    class CountResult:
        def scalar_one(self) -> int:
            return 0

    class RowsResult:
        def mappings(self) -> "RowsResult":
            return self

        def all(self) -> list[object]:
            return []

    class Connection:
        def __init__(self) -> None:
            self.statements: list[object] = []

        async def __aenter__(self) -> "Connection":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def execute(self, statement: object) -> CountResult | RowsResult:
            self.statements.append(statement)
            return CountResult() if len(self.statements) == 1 else RowsResult()

    class Engine:
        def __init__(self, connection: Connection) -> None:
            self.connection = connection

        def begin(self) -> Connection:
            return self.connection

    connection = Connection()
    with (
        patch.object(cves, "ensure_cves_table", AsyncMock()),
        patch.object(cves, "get_async_control_plane_engine", return_value=Engine(connection)),
    ):
        rows, total = await cves.search_cve_rows(query="remote code execution")

    assert rows == []
    assert total == 0
    sql = str(cast(Any, connection.statements[1]).compile(dialect=postgresql.dialect()))
    assert "plainto_tsquery" in sql
    assert "ts_rank_cd" in sql
    assert " @@ " in sql


@pytest.mark.asyncio
async def test_cve_update_route_returns_409_when_an_update_is_already_running():
    request = Request({"type": "http", "method": "POST", "path": "/api/cve/update", "headers": []})

    with patch.object(
        cve_routes,
        "update_cve_main",
        AsyncMock(side_effect=CVEUpdateAlreadyRunningError("already running")),
    ):
        with pytest.raises(HTTPException) as exc:
            await cve_routes.update_cve_database(
                request,
                user=cast(User, SimpleNamespace()),
                stream=False,
            )

    assert exc.value.status_code == 409
