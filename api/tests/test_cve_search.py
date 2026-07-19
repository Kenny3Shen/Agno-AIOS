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


@pytest.mark.asyncio
async def test_cve_delete_is_scoped_to_its_source_membership():
    class Result:
        rowcount = 1

    class Connection:
        def __init__(self) -> None:
            self.statements: list[object] = []

        async def __aenter__(self) -> "Connection":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def execute(self, statement: object) -> Result:
            self.statements.append(statement)
            return Result()

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
        deleted = await cves.delete_cve_rows(
            [
                {
                    "cve_id": "CVE-2026-0001",
                    "github_url": "https://github.com/example/poc",
                    "source": "github",
                }
            ]
        )

    assert deleted == 1
    sql = str(
        cast(Any, connection.statements[0]).compile(dialect=postgresql.dialect())
    )
    assert "cves.source" in sql
    assert "'github'" not in sql  # parameterized, never concatenated into SQL


@pytest.mark.asyncio
async def test_cve_upsert_uses_source_as_part_of_reference_identity():
    class Result:
        rowcount = 1

    class Connection:
        def __init__(self) -> None:
            self.statements: list[object] = []

        async def __aenter__(self) -> "Connection":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def execute(self, statement: object) -> Result:
            self.statements.append(statement)
            return Result()

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
        written = await cves.insert_new_cve_rows(
            [
                {
                    "cve_id": "cve-2026-0001",
                    "github_url": "https://github.com/example/poc",
                    "description": "corrected",
                    "source": "github",
                }
            ]
        )

    assert written == 1
    sql = str(
        cast(Any, connection.statements[0]).compile(dialect=postgresql.dialect())
    )
    assert "ON CONFLICT (cve_id, github_url, source) DO UPDATE" in sql


@pytest.mark.asyncio
async def test_find_missing_cve_source_keys_uses_source_ownership_identity():
    class Result:
        def all(self) -> list[tuple[str, str, str]]:
            return [
                (
                    "CVE-2026-0001",
                    "https://github.com/example/poc",
                    "github",
                )
            ]

    class Connection:
        def __init__(self) -> None:
            self.statements: list[object] = []

        async def __aenter__(self) -> "Connection":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def execute(self, statement: object) -> Result:
            self.statements.append(statement)
            return Result()

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
        missing = await cves.find_missing_cve_source_keys(
            [
                {
                    "cve_id": "CVE-2026-0001",
                    "github_url": "https://github.com/example/poc",
                    "source": "github",
                },
                {
                    "cve_id": "CVE-2026-0001",
                    "github_url": "https://github.com/example/poc",
                    "source": "exploit-db",
                },
            ]
        )

    assert missing == {
        ("CVE-2026-0001", "https://github.com/example/poc", "exploit-db")
    }
    sql = str(
        cast(Any, connection.statements[0]).compile(dialect=postgresql.dialect())
    )
    assert "cves.source" in sql
