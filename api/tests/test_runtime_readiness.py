from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from api import main
from api.main import app, check_control_plane_database, is_application_ready


@pytest.mark.asyncio
async def test_control_plane_probe_uses_a_minimal_database_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements: list[str] = []

    class FakeConnection:
        async def execute(self, statement: object) -> None:
            statements.append(str(statement))

    class FakeConnectContext:
        async def __aenter__(self) -> FakeConnection:
            return FakeConnection()

        async def __aexit__(self, _exc_type, _exc, _traceback) -> None:
            return None

    class FakeEngine:
        def connect(self) -> FakeConnectContext:
            return FakeConnectContext()

    monkeypatch.setattr(main, "get_async_control_plane_engine", FakeEngine)

    assert await check_control_plane_database() is True
    assert statements == ["SELECT 1"]


@pytest.mark.asyncio
async def test_readiness_does_not_probe_before_startup_is_complete() -> None:
    application = FastAPI()
    application.state.is_ready = False
    was_called = False

    async def probe() -> bool:
        nonlocal was_called
        was_called = True
        return True

    application.state.readiness_probe = probe

    assert await is_application_ready(application) is False
    assert was_called is False


@pytest.mark.asyncio
async def test_readiness_uses_an_injectable_probe() -> None:
    application = FastAPI()
    application.state.is_ready = True

    async def available() -> bool:
        return True

    application.state.readiness_probe = available
    assert await is_application_ready(application) is True

    async def unavailable() -> bool:
        raise RuntimeError("database unavailable")

    application.state.readiness_probe = unavailable
    assert await is_application_ready(application) is False


@pytest.mark.asyncio
async def test_health_is_live_while_readiness_tracks_startup_and_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def available() -> bool:
        return True

    monkeypatch.setattr(app.state, "readiness_probe", available)
    monkeypatch.setattr(app.state, "is_ready", False)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        health = await client.get("/api/health")
        not_ready = await client.get("/api/ready")

        monkeypatch.setattr(app.state, "is_ready", True)
        ready = await client.get("/api/ready")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert not_ready.status_code == 503
    assert not_ready.json() == {"status": "not_ready"}
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
