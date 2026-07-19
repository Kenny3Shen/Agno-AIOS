from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from api.persistence import migrations
from api.utils.async_once import AsyncOnce


class _RevisionConnection:
    def __init__(self, result: str | None | BaseException) -> None:
        self.result = result
        self.statements: list[str] = []

    async def scalar(self, statement: object) -> str | None:
        self.statements.append(str(statement))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class _RevisionConnectionContext:
    def __init__(self, connection: _RevisionConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _RevisionConnection:
        return self.connection

    async def __aexit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        return None


class _RevisionEngine:
    def __init__(self, result: str | None | BaseException) -> None:
        self.connection = _RevisionConnection(result)

    def connect(self) -> _RevisionConnectionContext:
        return _RevisionConnectionContext(self.connection)


@pytest.mark.asyncio
async def test_control_plane_current_revision_reads_alembic_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _RevisionEngine("20260720_0002")
    monkeypatch.setattr(migrations, "get_async_control_plane_engine", lambda: engine)

    assert await migrations.control_plane_current_revision() == "20260720_0002"
    assert engine.connection.statements == ["SELECT version_num FROM alembic_version"]


@pytest.mark.asyncio
async def test_control_plane_current_revision_returns_none_when_alembic_not_initialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _RevisionEngine(SQLAlchemyError("alembic_version does not exist"))
    monkeypatch.setattr(migrations, "get_async_control_plane_engine", lambda: engine)

    assert await migrations.control_plane_current_revision() is None


@pytest.mark.asyncio
async def test_assert_control_plane_schema_current_requires_exact_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(migrations, "control_plane_head_revision", lambda: "expected")
    current = AsyncMock(return_value="expected")
    monkeypatch.setattr(migrations, "control_plane_current_revision", current)

    await migrations.assert_control_plane_schema_current()
    current.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_assert_control_plane_schema_current_fails_closed_for_missing_or_stale_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(migrations, "control_plane_head_revision", lambda: "expected")

    for current in (None, "previous"):
        monkeypatch.setattr(
            migrations,
            "control_plane_current_revision",
            AsyncMock(return_value=current),
        )
        with pytest.raises(migrations.ControlPlaneSchemaOutdatedError) as error:
            await migrations.assert_control_plane_schema_current()

        assert f"database={current or 'none'}, expected=expected" in str(error.value)
        assert "uv run alembic upgrade head" in str(error.value)


@pytest.mark.asyncio
async def test_schema_current_check_is_serialized_and_cached_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked = AsyncMock()
    monkeypatch.setattr(migrations, "_schema_checked_once", AsyncOnce())
    monkeypatch.setattr(migrations, "assert_control_plane_schema_current", checked)

    await asyncio.gather(
        migrations.ensure_control_plane_schema_current(),
        migrations.ensure_control_plane_schema_current(),
    )

    checked.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_schema_current_check_retries_after_a_failed_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked = AsyncMock(
        side_effect=[
            migrations.ControlPlaneSchemaOutdatedError("migration required"),
            None,
        ]
    )
    monkeypatch.setattr(migrations, "_schema_checked_once", AsyncOnce())
    monkeypatch.setattr(migrations, "assert_control_plane_schema_current", checked)

    with pytest.raises(migrations.ControlPlaneSchemaOutdatedError):
        await migrations.ensure_control_plane_schema_current()
    await migrations.ensure_control_plane_schema_current()

    assert checked.await_count == 2


@pytest.mark.asyncio
async def test_schema_current_readiness_check_returns_false_for_outdated_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        migrations,
        "assert_control_plane_schema_current",
        AsyncMock(side_effect=migrations.ControlPlaneSchemaOutdatedError("stale")),
    )

    assert await migrations.control_plane_schema_is_current() is False
