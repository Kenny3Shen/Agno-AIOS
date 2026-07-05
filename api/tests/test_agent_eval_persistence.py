import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from api.persistence import agent_evals as persistence
from api.auth.permissions import has_permission
from api.persistence.agent_evals import (
    agent_eval_case_runs_table,
    agent_eval_cases_table,
    agent_eval_suite_runs_table,
    agent_eval_suites_table,
    case_run_by_agno_eval_run_id_statement,
    case_runs_by_agno_eval_run_ids_statement,
    create_case_row_async,
    create_case_run_row_async,
    create_suite_row_async,
    create_suite_run_row_async,
    get_case_row_async,
    get_case_run_by_agno_eval_run_id_row_async,
    get_case_run_row_async,
    list_case_runs_by_agno_eval_run_ids_rows_async,
    get_suite_row_async,
    get_suite_run_row_async,
    list_case_rows_async,
    list_case_run_rows_async,
    list_suite_rows_async,
    list_suite_run_rows_async,
    update_case_row_async,
    update_case_run_row_async,
    update_suite_row_async,
    update_suite_run_row_async,
)
from api.services.security_policy import CONTROL_MODULE_PERMISSIONS


class FakeBootstrapConnection:
    def __init__(self, engine: "FakeBootstrapEngine"):
        self.engine = engine

    async def execute(self, statement: object) -> None:
        await asyncio.sleep(0)

    async def run_sync(self, callback: object, **kwargs: object) -> None:
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

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class FakeBootstrapEngine:
    def __init__(self):
        self.begin_calls = 0
        self.run_sync_calls = 0
        self.in_ddl = False
        self.concurrent_ddl_seen = False

    def begin(self) -> FakeBootstrapBegin:
        return FakeBootstrapBegin(self)


def actor(role: str):
    return SimpleNamespace(role=role, is_superuser=False)


def test_evaluation_control_module_uses_agent_eval_read_permission():
    assert CONTROL_MODULE_PERMISSIONS["evaluation"] == "agent_eval:read"
    assert has_permission(actor("user"), CONTROL_MODULE_PERMISSIONS["evaluation"])


def test_agent_eval_tables_use_jsonb_and_expected_names():
    suites = agent_eval_suites_table()
    cases = agent_eval_cases_table()
    suite_runs = agent_eval_suite_runs_table()
    case_runs = agent_eval_case_runs_table()

    assert suites.name == "agent_eval_suites"
    assert cases.name == "agent_eval_cases"
    assert suite_runs.name == "agent_eval_suite_runs"
    assert case_runs.name == "agent_eval_case_runs"
    assert cases.c.eval_types.type.__class__.__name__ == "JSONB"
    assert cases.c.expected_tool_calls.type.__class__.__name__ == "JSONB"
    assert case_runs.c.agno_eval_run_ids.type.__class__.__name__ == "JSONB"


def test_agent_eval_crud_helpers_are_exported():
    assert create_suite_row_async
    assert list_suite_rows_async
    assert get_suite_row_async
    assert update_suite_row_async
    assert create_case_row_async
    assert list_case_rows_async
    assert get_case_row_async
    assert update_case_row_async
    assert create_suite_run_row_async
    assert list_suite_run_rows_async
    assert get_suite_run_row_async
    assert update_suite_run_row_async
    assert create_case_run_row_async
    assert list_case_run_rows_async
    assert list_case_runs_by_agno_eval_run_ids_rows_async
    assert get_case_run_row_async
    assert get_case_run_by_agno_eval_run_id_row_async
    assert update_case_run_row_async


def test_case_run_by_agno_eval_run_id_uses_jsonb_contains_query():
    stmt = case_run_by_agno_eval_run_id_statement("eval-1")
    compiled = str(stmt.compile(dialect=postgresql.dialect()))

    assert "agent_eval_case_runs" in compiled
    assert "agno_eval_run_ids" in compiled
    assert "@>" in compiled


def test_case_runs_by_agno_eval_run_ids_uses_single_jsonb_query():
    stmt = case_runs_by_agno_eval_run_ids_statement(["eval-1", "eval-2"])
    compiled = str(stmt.compile(dialect=postgresql.dialect()))

    assert "agent_eval_case_runs" in compiled
    assert "agno_eval_run_ids" in compiled
    assert compiled.count("@>") == 2
    assert " OR " in compiled


@pytest.mark.asyncio
async def test_ensure_agent_eval_tables_serializes_concurrent_bootstrap(monkeypatch: pytest.MonkeyPatch):
    engine = FakeBootstrapEngine()
    monkeypatch.setattr(persistence, "_agent_eval_tables_ready", False, raising=False)
    monkeypatch.setattr(persistence, "_agent_eval_tables_lock", asyncio.Lock(), raising=False)
    monkeypatch.setattr(persistence, "get_async_control_plane_engine", lambda: engine)

    await asyncio.gather(
        persistence.ensure_agent_eval_tables_async(),
        persistence.ensure_agent_eval_tables_async(),
    )

    assert engine.concurrent_ddl_seen is False
    assert engine.begin_calls == 1
    assert engine.run_sync_calls > 0
