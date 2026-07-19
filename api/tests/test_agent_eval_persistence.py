import asyncio

import pytest

from api.persistence import agent_evals as persistence
from api.utils.async_once import AsyncOnce


class FakeBootstrapConnection:
    def __init__(self, engine: "FakeBootstrapEngine"):
        self.engine = engine

    async def execute(self, statement: object) -> None:
        await asyncio.sleep(0)

    async def run_sync(self, _callback: object, **_kwargs: object) -> None:
        if self.engine.in_ddl:
            self.engine.concurrent_ddl_seen = True
        self.engine.in_ddl = True
        self.engine.run_sync_calls += 1
        await asyncio.sleep(0)
        self.engine.in_ddl = False


class FakeBootstrapBegin:
    def __init__(self, engine: "FakeBootstrapEngine"):
        self.engine = engine

    async def __aenter__(self) -> FakeBootstrapConnection:
        self.engine.begin_calls += 1
        return FakeBootstrapConnection(self.engine)

    async def __aexit__(self, *_args: object) -> None:
        return None


class FakeBootstrapEngine:
    def __init__(self):
        self.begin_calls = 0
        self.run_sync_calls = 0
        self.in_ddl = False
        self.concurrent_ddl_seen = False

    def begin(self) -> FakeBootstrapBegin:
        return FakeBootstrapBegin(self)

@pytest.mark.asyncio
async def test_ensure_agent_eval_tables_serializes_concurrent_bootstrap(monkeypatch: pytest.MonkeyPatch):
    engine = FakeBootstrapEngine()
    monkeypatch.setattr(persistence, "_agent_eval_tables_once", AsyncOnce())
    monkeypatch.setattr(persistence, "get_async_control_plane_engine", lambda: engine)

    await asyncio.gather(
        persistence.ensure_agent_eval_tables_async(),
        persistence.ensure_agent_eval_tables_async(),
    )

    assert engine.concurrent_ddl_seen is False
    assert engine.begin_calls == 1
    assert engine.run_sync_calls > 0
