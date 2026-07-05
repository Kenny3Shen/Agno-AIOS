# Agent Evals Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an Agent Evals center for the security Agent with suite/case management, Agno async Eval execution, Agno eval run history, trends, failed sample replay, and a dense Evaluation workbench UI.

**Architecture:** AIOS owns suite/case orchestration metadata in app-owned Async SQLAlchemy tables. Agno owns eval execution result storage, accessed only through public async Agno APIs such as Eval `arun()` and `AsyncPostgresDb.get_eval_runs()` / `get_eval_run()`. The frontend replaces the old generic Evaluation ledger with an independent workbench component that follows the existing Knowledge, Trace, Approvals, and MCP visual patterns.

**Tech Stack:** FastAPI, Pydantic, Async SQLAlchemy Core, Agno `AccuracyEval`, `AgentAsJudgeEval`, `ReliabilityEval`, `PerformanceEval`, Agno `AsyncPostgresDb`, Vue 3, Element Plus, Pinia auth store, vue-i18n, Bun tests, pytest.

## Global Constraints

- Use Agno async APIs first.
- Eval execution must use `arun()` for Agno Eval classes when the installed class exposes it.
- Eval result reads must use `AsyncPostgresDb.get_eval_runs()` and `AsyncPostgresDb.get_eval_run()`.
- Runtime DB access must come from `get_async_agno_postgres_db()`.
- App-owned suite/case metadata must use the existing Async SQLAlchemy engine/session boundary.
- A synchronous Agno API is allowed only as a narrow exception when the installed Agno package has no async equivalent for that capability.
- The frontend must not expose a manual `PerformanceEval` run button in the first slice.
- Do not query Agno eval tables with SQL.
- Do not edit security Agent prompts from this feature.
- Keep Evaluation as the navigation label, but render a dedicated Agent Evals workbench instead of the generic AgentOS ledger.

---

## Scope Check

This is one feature with two dependent halves: backend eval orchestration and frontend eval operations. The backend tasks produce a working API before the frontend task begins. The frontend task consumes the API types and keeps performance execution hidden while still displaying performance history.

## File Structure

Create:

- `api/persistence/agent_evals.py`: Async SQLAlchemy table definitions and CRUD for AIOS-owned eval suites, cases, suite runs, and case runs.
- `api/services/agent_eval_case_store.py`: Service-level validation, normalization, and case/suite orchestration helpers over persistence.
- `api/services/agent_eval_result_service.py`: Thin Agno async eval-run projection service.
- `api/services/agent_eval_runner.py`: Eval execution orchestration using Agno Eval classes and security Agent runtime.
- `api/routes/agent_evals.py`: FastAPI route surface under `/api/agent-evals`.
- `api/tests/test_agent_eval_persistence.py`: Persistence and permission tests.
- `api/tests/test_agent_eval_case_store.py`: Store service tests.
- `api/tests/test_agent_eval_result_service.py`: Agno async result adapter tests and static guards.
- `api/tests/test_agent_eval_runner.py`: Eval runner mapping, partial failure, replay, and async API tests.
- `api/tests/test_agent_eval_routes.py`: Route validation and permission tests.
- `frontend/src/components/AgentEvals.vue`: Dedicated Evaluation workbench.
- `frontend/src/modules/agentEvalsWorkbench.ts`: Pure frontend helpers for summaries, filtering, and tool-call chips.
- `frontend/src/modules/agentEvalsWorkbench.test.mjs`: Frontend helper tests.

Modify:

- `api/auth/permissions.py`: Add `agent_eval:read`, `agent_eval:write`, and `agent_eval:run` to the user role policy.
- `api/services/security_policy.py`: Map `evaluation` to `agent_eval:read`; add explicit eval write/run helpers.
- `api/services/security_run_runtime.py`: Add a public async context manager for building a full security Agent for eval execution.
- `api/main.py`: Include the new Agent Evals router.
- `api/tests/test_postgres_sql_templates.py`: Add async Agno Eval guard tests.
- `api/tests/test_rbac_permissions.py`: Add permission coverage.
- `frontend/src/types/index.ts`: Add Agent Eval types.
- `frontend/src/composables/useApi.ts`: Add `useAgentEvalsApi()`.
- `frontend/src/App.vue`: Map `evaluation` to `AgentEvals`.
- `frontend/src/modules/shellNavigation.ts`: Remove `evaluation` from OS control tabs while keeping it full-canvas.
- `frontend/src/lib/permissions.ts`: Add frontend `agent_eval:*` permissions.
- `frontend/src/i18n/locales/zh-CN.ts`: Add Evaluation workbench copy and API error copy.
- `frontend/src/i18n/locales/en-US.ts`: Add English copy.
- `frontend/src/uiShell.test.mjs`: Load AgentEvals component source and assert Evaluation no longer uses AgentOSControl.

---

### Task 1: Backend Persistence And Permission Foundation

**Files:**
- Create: `api/persistence/agent_evals.py`
- Create: `api/tests/test_agent_eval_persistence.py`
- Modify: `api/auth/permissions.py`
- Modify: `api/services/security_policy.py`
- Modify: `api/tests/test_rbac_permissions.py`

**Interfaces:**
- Produces:
  - `ensure_agent_eval_tables_async() -> None`
  - `agent_eval_suites_table() -> Table`
  - `agent_eval_cases_table() -> Table`
  - `agent_eval_suite_runs_table() -> Table`
  - `agent_eval_case_runs_table() -> Table`
  - `create_suite_row_async(values: dict[str, Any]) -> dict[str, Any]`
  - `list_suite_rows_async(enabled: bool | None = None) -> list[dict[str, Any]]`
  - `get_suite_row_async(suite_id: str) -> dict[str, Any] | None`
  - `update_suite_row_async(suite_id: str, values: dict[str, Any]) -> dict[str, Any] | None`
  - Matching `*_case_*`, `*_suite_run_*`, and `*_case_run_*` helpers.
- Consumes:
  - `api.persistence.database.get_async_control_plane_engine()`
  - `api.config.get_settings().agno_app_schema`

- [ ] **Step 1: Write permission tests**

Add this to `api/tests/test_rbac_permissions.py`:

```python
def test_agent_eval_permissions_are_role_scoped():
    admin = user("admin")
    normal_user = user("user")
    guest = user("guest")

    assert has_permission(admin, "agent_eval:read")
    assert has_permission(admin, "agent_eval:write")
    assert has_permission(admin, "agent_eval:run")
    assert has_permission(normal_user, "agent_eval:read")
    assert not has_permission(normal_user, "agent_eval:write")
    assert not has_permission(normal_user, "agent_eval:run")
    assert not has_permission(guest, "agent_eval:read")
```

Run: `uv run pytest api/tests/test_rbac_permissions.py::test_agent_eval_permissions_are_role_scoped -q`

Expected: FAIL because the new permissions are missing.

- [ ] **Step 2: Add role permissions**

Modify `api/auth/permissions.py`:

```python
"user": {
    "session:read:own",
    "session:write:own",
    "trace:read:own",
    "memory:read:own",
    "metrics:read:own",
    "collect:write",
    "cve:read",
    "knowledge:read",
    "knowledge:write",
    "mcp:read",
    "skill:read",
    "settings:read",
    "agent_eval:read",
},
```

Do not add eval permissions to `guest`. Admin remains covered by `"*"`.

Run: `uv run pytest api/tests/test_rbac_permissions.py::test_agent_eval_permissions_are_role_scoped -q`

Expected: PASS.

- [ ] **Step 3: Write policy mapping tests**

Add this to `api/tests/test_agent_eval_persistence.py`:

```python
from types import SimpleNamespace

from api.auth.permissions import has_permission
from api.services.security_policy import CONTROL_MODULE_PERMISSIONS


def actor(role: str):
    return SimpleNamespace(role=role, is_superuser=False)


def test_evaluation_control_module_uses_agent_eval_read_permission():
    assert CONTROL_MODULE_PERMISSIONS["evaluation"] == "agent_eval:read"
    assert has_permission(actor("user"), CONTROL_MODULE_PERMISSIONS["evaluation"])
```

Run: `uv run pytest api/tests/test_agent_eval_persistence.py::test_evaluation_control_module_uses_agent_eval_read_permission -q`

Expected: FAIL because `evaluation` still maps to `admin:read`.

- [ ] **Step 4: Update policy mapping**

Modify `api/services/security_policy.py`:

```python
CONTROL_MODULE_PERMISSIONS = {
    "sessions": "session:read:own",
    "studio": "mcp:read",
    "memory": "memory:read:own",
    "metrics": "metrics:read:own",
    "evaluation": "agent_eval:read",
    "approvals": "admin:read",
    "scheduler": "admin:read",
    "knowledge": "knowledge:read",
}


def require_agent_eval_write(actor: Any) -> None:
    require_actor_permission(actor, "agent_eval:write")


def require_agent_eval_run(actor: Any) -> None:
    require_actor_permission(actor, "agent_eval:run")
```

Run: `uv run pytest api/tests/test_agent_eval_persistence.py::test_evaluation_control_module_uses_agent_eval_read_permission -q`

Expected: PASS.

- [ ] **Step 5: Write table definition tests**

Add this to `api/tests/test_agent_eval_persistence.py`:

```python
from api.persistence.agent_evals import (
    agent_eval_case_runs_table,
    agent_eval_cases_table,
    agent_eval_suite_runs_table,
    agent_eval_suites_table,
)


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
```

Run: `uv run pytest api/tests/test_agent_eval_persistence.py::test_agent_eval_tables_use_jsonb_and_expected_names -q`

Expected: FAIL because `api.persistence.agent_evals` does not exist.

- [ ] **Step 6: Implement SQLAlchemy tables and bootstrap helper**

Create `api/persistence/agent_evals.py` with these table names and columns:

```python
from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Column, DateTime, Index, MetaData, Table, Text, desc, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import CreateSchema

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine

SUITES_TABLE = "agent_eval_suites"
CASES_TABLE = "agent_eval_cases"
SUITE_RUNS_TABLE = "agent_eval_suite_runs"
CASE_RUNS_TABLE = "agent_eval_case_runs"


def _app_schema() -> str:
    return get_settings().agno_app_schema


def _metadata() -> MetaData:
    return MetaData(schema=_app_schema())


def agent_eval_suites_table() -> Table:
    table = Table(
        SUITES_TABLE,
        _metadata(),
        Column("id", Text, primary_key=True),
        Column("name", Text, nullable=False),
        Column("description", Text, nullable=False, server_default=""),
        Column("target_agent_id", Text, nullable=False, server_default="security-operations"),
        Column("enabled", Boolean, nullable=False, server_default=text("true")),
        Column("tags", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
        Column("created_by", Text, nullable=False, server_default=""),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
    )
    Index("idx_agent_eval_suites_updated", desc(table.c.updated_at))
    return table
```

Add `agent_eval_cases_table()` with columns:

- `id`, `suite_id`, `name`, `description`, `target_agent_id`, `input`, `expected_output`, `criteria`
- `threshold` as integer
- `eval_types`, `expected_tool_calls`, `expected_tool_call_arguments`, `performance_config`, `metadata` as JSONB
- `allow_additional_tool_calls`, `enabled` as booleans
- `created_at`, `updated_at`

Add `agent_eval_suite_runs_table()` with columns:

- `id`, `suite_id`, `status`, `started_by`, `error_summary`
- `summary` as JSONB
- `started_at`, `completed_at`

Add `agent_eval_case_runs_table()` with columns:

- `id`, `suite_run_id`, `case_id`, `status`, `agent_run_id`, `session_id`, `trace_id`
- `agno_eval_run_ids` as JSONB
- `error_type`, `error_summary`, `replay_of_case_run_id`
- `started_at`, `completed_at`

Add `ensure_agent_eval_tables_async()` that creates the app schema and all four tables plus indexes with `await conn.run_sync(table.create, checkfirst=True)`.

Run: `uv run pytest api/tests/test_agent_eval_persistence.py::test_agent_eval_tables_use_jsonb_and_expected_names -q`

Expected: PASS.

- [ ] **Step 7: Add row CRUD helpers**

In `api/persistence/agent_evals.py`, add helpers that call `await ensure_agent_eval_tables_async()` before table access. Use SQLAlchemy `insert(table).values(values).returning(table)` and `update(table).where(table.c.id == row_id).values(values).returning(table)`. Convert results with:

```python
def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row)
```

Required helper signatures are the exact interface names listed at the top of Task 1. Implement each helper in `api/persistence/agent_evals.py` and import them from `api.services.agent_eval_case_store` in Task 2.

Run: `uv run pytest api/tests/test_agent_eval_persistence.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add api/persistence/agent_evals.py api/auth/permissions.py api/services/security_policy.py api/tests/test_agent_eval_persistence.py api/tests/test_rbac_permissions.py
git commit -m "feat: add agent eval persistence foundation"
```

---

### Task 2: Case Store Service

**Files:**
- Create: `api/services/agent_eval_case_store.py`
- Create: `api/tests/test_agent_eval_case_store.py`

**Interfaces:**
- Consumes:
  - Persistence helpers from Task 1.
- Produces:
  - `SUPPORTED_EVAL_TYPES = {"accuracy", "agent_as_judge", "reliability", "performance"}`
  - `normalize_suite(row: Any) -> dict[str, Any]`
  - `normalize_case(row: Any) -> dict[str, Any]`
  - `create_suite(payload: dict[str, Any], actor: Any) -> dict[str, Any]`
  - `list_suites(enabled: bool | None = None) -> list[dict[str, Any]]`
  - `update_suite(suite_id: str, payload: dict[str, Any]) -> dict[str, Any] | None`
  - `create_case(payload: dict[str, Any]) -> dict[str, Any]`
  - `list_cases(suite_id: str | None = None, enabled: bool | None = None) -> list[dict[str, Any]]`
  - `update_case(case_id: str, payload: dict[str, Any]) -> dict[str, Any] | None`
  - `create_suite_run(suite_id: str, actor: Any) -> dict[str, Any]`
  - `create_case_run(case_id: str, suite_run_id: str | None = None, replay_of_case_run_id: str | None = None) -> dict[str, Any]`
  - `mark_case_run(case_run_id: str, status: str, values: dict[str, Any]) -> dict[str, Any] | None`
  - `mark_suite_run(suite_run_id: str, status: str, summary: dict[str, Any], error_summary: str = "") -> dict[str, Any] | None`

- [ ] **Step 1: Write validation tests**

Create `api/tests/test_agent_eval_case_store.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.services import agent_eval_case_store as store


def actor():
    return SimpleNamespace(id="user-1", email="operator@example.com", role="admin", is_superuser=False)


@pytest.mark.asyncio
async def test_create_case_rejects_unknown_eval_type():
    with pytest.raises(ValueError, match="Unsupported eval type"):
        await store.create_case(
            {
                "suite_id": "suite-1",
                "name": "bad",
                "input": "x",
                "eval_types": ["made_up"],
            }
        )


@pytest.mark.asyncio
async def test_create_suite_derives_created_by_from_actor():
    with patch.object(store, "create_suite_row_async", new=AsyncMock(return_value={
        "id": "suite-1",
        "name": "Security Regression",
        "description": "",
        "target_agent_id": "security-operations",
        "enabled": True,
        "tags": ["security"],
        "created_by": "user-1",
        "created_at": "2026-07-06T00:00:00Z",
        "updated_at": "2026-07-06T00:00:00Z",
    })) as create_mock:
        result = await store.create_suite({"name": "Security Regression", "tags": ["security"]}, actor())

    assert result["id"] == "suite-1"
    assert create_mock.await_args.kwargs["values"]["created_by"] == "user-1"
```

Run: `uv run pytest api/tests/test_agent_eval_case_store.py -q`

Expected: FAIL because the service does not exist.

- [ ] **Step 2: Implement normalization and validation**

Create `api/services/agent_eval_case_store.py`. Use `uuid.uuid4().hex` for IDs and keep all timestamps from the database rows.

Core validation:

```python
SUPPORTED_EVAL_TYPES = {"accuracy", "agent_as_judge", "reliability", "performance"}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _eval_types(value: Any) -> list[str]:
    types = _string_list(value) or ["accuracy"]
    unsupported = sorted(set(types) - SUPPORTED_EVAL_TYPES)
    if unsupported:
        raise ValueError(f"Unsupported eval type: {', '.join(unsupported)}")
    return types
```

Implement `normalize_suite()` and `normalize_case()` returning JSON-serializable dictionaries.

Run: `uv run pytest api/tests/test_agent_eval_case_store.py -q`

Expected: PASS for the two initial tests.

- [ ] **Step 3: Add CRUD service tests**

Extend `api/tests/test_agent_eval_case_store.py`:

```python
@pytest.mark.asyncio
async def test_create_case_sets_defaults_and_preserves_reliability_config():
    with patch.object(store, "create_case_row_async", new=AsyncMock(return_value={
        "id": "case-1",
        "suite_id": "suite-1",
        "name": "CVE lookup calls MCP",
        "description": "",
        "target_agent_id": "security-operations",
        "input": "Lookup CVE-2026-20700",
        "expected_output": "",
        "criteria": "",
        "threshold": 7,
        "eval_types": ["reliability"],
        "expected_tool_calls": ["playbook.cve_lookup"],
        "expected_tool_call_arguments": {"playbook.cve_lookup": {"cve": "CVE-2026-20700"}},
        "allow_additional_tool_calls": False,
        "performance_config": {},
        "metadata": {},
        "enabled": True,
        "created_at": "2026-07-06T00:00:00Z",
        "updated_at": "2026-07-06T00:00:00Z",
    })) as create_mock:
        result = await store.create_case({
            "suite_id": "suite-1",
            "name": "CVE lookup calls MCP",
            "input": "Lookup CVE-2026-20700",
            "eval_types": ["reliability"],
            "expected_tool_calls": ["playbook.cve_lookup"],
            "expected_tool_call_arguments": {"playbook.cve_lookup": {"cve": "CVE-2026-20700"}},
        })

    assert result["eval_types"] == ["reliability"]
    assert result["expected_tool_calls"] == ["playbook.cve_lookup"]
    assert create_mock.await_args.kwargs["values"]["allow_additional_tool_calls"] is False
```

Run: `uv run pytest api/tests/test_agent_eval_case_store.py -q`

Expected: FAIL until `create_case()` passes defaults to persistence.

- [ ] **Step 4: Implement suite/case CRUD helpers**

Implement all service functions listed in this task's interface. For updates, filter payload keys against known column names and call the persistence update helper. Raise `ValueError("No supported fields to update")` when the update payload has no known fields.

Run: `uv run pytest api/tests/test_agent_eval_case_store.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/services/agent_eval_case_store.py api/tests/test_agent_eval_case_store.py
git commit -m "feat: add agent eval case store"
```

---

### Task 3: Agno Async Eval Result Service

**Files:**
- Create: `api/services/agent_eval_result_service.py`
- Create: `api/tests/test_agent_eval_result_service.py`
- Modify: `api/tests/test_postgres_sql_templates.py`

**Interfaces:**
- Consumes:
  - `get_async_agno_postgres_db()`
  - `AsyncPostgresDb.get_eval_runs()`
  - `AsyncPostgresDb.get_eval_run()`
- Produces:
  - `normalize_agno_eval_run(raw_run: Any) -> dict[str, Any]`
  - `list_agno_eval_runs(limit: int = 50, page: int = 1, eval_type: list[str] | None = None, agent_id: str | None = None) -> dict[str, Any]`
  - `get_agno_eval_run(eval_run_id: str) -> dict[str, Any] | None`
  - `build_eval_trends(runs: list[dict[str, Any]]) -> dict[str, Any]`
  - `list_failed_eval_runs(limit: int = 50) -> list[dict[str, Any]]`

- [ ] **Step 1: Write fake Agno DB tests**

Create `api/tests/test_agent_eval_result_service.py`:

```python
from unittest.mock import patch

import pytest

from api.services import agent_eval_result_service as service


class FakeEvalDb:
    def __init__(self):
        self.list_kwargs = {}

    async def get_eval_runs(self, **kwargs):
        self.list_kwargs = kwargs
        return (
            [
                {
                    "run_id": "eval-1",
                    "eval_type": "accuracy",
                    "agent_id": "security-operations",
                    "name": "CVE baseline",
                    "data": {"overall_score": 1.0, "passed": True},
                    "created_at": 1714560000,
                }
            ],
            1,
        )

    async def get_eval_run(self, eval_run_id: str, deserialize=True):
        if eval_run_id == "missing":
            return None
        return {
            "run_id": eval_run_id,
            "eval_type": "reliability",
            "data": {"passed": False, "missing_tool_calls": ["playbook.cve_lookup"]},
        }


@pytest.mark.asyncio
async def test_list_agno_eval_runs_uses_async_db_api():
    db = FakeEvalDb()
    with patch("api.services.agent_eval_result_service.get_async_agno_postgres_db", return_value=db):
        result = await service.list_agno_eval_runs(limit=10, page=2, eval_type=["accuracy"])

    assert db.list_kwargs["limit"] == 10
    assert db.list_kwargs["page"] == 2
    assert result["total"] == 1
    assert result["items"][0]["id"] == "eval-1"


@pytest.mark.asyncio
async def test_get_agno_eval_run_returns_none_for_missing():
    db = FakeEvalDb()
    with patch("api.services.agent_eval_result_service.get_async_agno_postgres_db", return_value=db):
        assert await service.get_agno_eval_run("missing") is None
```

Run: `uv run pytest api/tests/test_agent_eval_result_service.py -q`

Expected: FAIL because the service does not exist.

- [ ] **Step 2: Implement result service**

Create `api/services/agent_eval_result_service.py`. Handle dicts, Pydantic-style objects, and dataclasses with the same row conversion approach used by `approval_control_service.py`.

Use this ID normalization:

```python
def normalize_agno_eval_run(raw_run: Any) -> dict[str, Any]:
    row = _row_dict(raw_run)
    run_id = str(row.get("run_id") or row.get("id") or "")
    data = row.get("data") if isinstance(row.get("data"), dict) else {}
    return {
        "id": run_id,
        "run_id": run_id,
        "name": str(row.get("name") or run_id or "Eval Run"),
        "eval_type": str(row.get("eval_type") or ""),
        "agent_id": row.get("agent_id"),
        "team_id": row.get("team_id"),
        "workflow_id": row.get("workflow_id"),
        "model_id": row.get("model_id"),
        "model_provider": row.get("model_provider"),
        "passed": _passed_from_data(data),
        "score": _score_from_data(data),
        "data": data,
        "eval_input": row.get("eval_input") if isinstance(row.get("eval_input"), dict) else {},
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }
```

Run: `uv run pytest api/tests/test_agent_eval_result_service.py -q`

Expected: PASS.

- [ ] **Step 3: Add static guard tests**

Add to `api/tests/test_postgres_sql_templates.py`:

```python
from api.services import agent_eval_result_service


def test_agent_eval_result_service_uses_agno_async_api_only() -> None:
    source = inspect.getsource(agent_eval_result_service)
    assert "get_async_agno_postgres_db" in source
    assert "get_eval_runs" in source
    assert "get_eval_run" in source
    assert "get_agno_postgres_db" not in source
    assert "PostgresDb" not in source
    assert "agno_eval" not in source.lower().replace("agno_eval_run", "")
    assert "select(" not in source
    assert "from psycopg" not in source
```

Run: `uv run pytest api/tests/test_postgres_sql_templates.py::test_agent_eval_result_service_uses_agno_async_api_only -q`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add api/services/agent_eval_result_service.py api/tests/test_agent_eval_result_service.py api/tests/test_postgres_sql_templates.py
git commit -m "feat: add agno eval result adapter"
```

---

### Task 4: Security Agent Eval Builder And Eval Runner

**Files:**
- Modify: `api/services/security_run_runtime.py`
- Create: `api/services/agent_eval_runner.py`
- Create: `api/tests/test_agent_eval_runner.py`
- Modify: `api/tests/test_postgres_sql_templates.py`

**Interfaces:**
- Consumes:
  - `agent_eval_case_store`
  - `get_async_agno_postgres_db()`
  - `DEFAULT_SECURITY_RUN_RUNTIME`
  - Agno Eval classes
- Produces:
  - `SecurityRunRuntime.security_agent_context(request: SecurityRunRequest) -> AsyncIterator[Agent]`
  - `AgentEvalRunnerDependencies`
  - `run_case(case_id: str, actor: Any, suite_run_id: str | None = None, replay_of_case_run_id: str | None = None) -> dict[str, Any]`
  - `run_suite(suite_id: str, actor: Any) -> dict[str, Any]`
  - `replay_case_run(case_run_id: str, actor: Any) -> dict[str, Any]`

- [ ] **Step 1: Write security runtime context test**

Add to `api/tests/test_agent_eval_runner.py`:

```python
from types import SimpleNamespace

import pytest

from api.services.security_run_runtime import SecurityRunRequest, SecurityRunRuntime


class FakeMcpTools:
    async def __aenter__(self):
        return "mcp-tools"

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_security_runtime_exposes_agent_context_for_evals():
    runtime = SecurityRunRuntime()
    runtime.dependencies = SimpleNamespace(
        mcp_tools_factory=lambda **kwargs: FakeMcpTools(),
        get_mcp_url=lambda: "http://127.0.0.1:8000/mcp/?token=test",
        build_model=lambda model_id: "model",
        get_async_knowledge_base=lambda: None,
        get_enabled_skill_dirs=lambda: [],
        get_db=lambda: "db",
        agent_factory=lambda **kwargs: SimpleNamespace(**kwargs),
    )

    request = SecurityRunRequest.from_chat_args("ping", user_id="user-1")
    async with runtime.security_agent_context(request) as agent:
        assert agent.id == "security-operations"
        assert agent.tools == ["mcp-tools"]
```

Run: `uv run pytest api/tests/test_agent_eval_runner.py::test_security_runtime_exposes_agent_context_for_evals -q`

Expected: FAIL because `security_agent_context()` does not exist.

- [ ] **Step 2: Add public async context manager**

Modify `api/services/security_run_runtime.py`:

```python
from contextlib import asynccontextmanager
```

Add to `SecurityRunRuntime`:

```python
@asynccontextmanager
async def security_agent_context(self, request: SecurityRunRequest) -> AsyncIterator[Agent]:
    async with self.dependencies.mcp_tools_factory(
        transport="streamable-http",
        url=self.dependencies.get_mcp_url(),
        timeout_seconds=20,
    ) as mcp_tools:
        security_agent = await _maybe_await(self._build_security_agent(mcp_tools, request))
        yield security_agent
```

Update `stream()` to call `async with self.security_agent_context(request) as security_agent:` instead of duplicating the MCP context setup.

Run: `uv run pytest api/tests/test_agent_eval_runner.py::test_security_runtime_exposes_agent_context_for_evals -q`

Expected: PASS.

- [ ] **Step 3: Write Eval runner mapping tests**

Extend `api/tests/test_agent_eval_runner.py` with fake Eval classes:

```python
class FakeAccuracyEval:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.eval_id = "accuracy-eval"
        FakeAccuracyEval.calls.append(kwargs)

    async def arun(self, **kwargs):
        return SimpleNamespace(results=[SimpleNamespace(passed=True, score=1.0)])


class FakeJudgeEval:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.eval_id = "judge-eval"
        FakeJudgeEval.calls.append(kwargs)

    async def arun(self, **kwargs):
        self.run_kwargs = kwargs
        return SimpleNamespace(results=[SimpleNamespace(passed=True, score=9)])


class FakeReliabilityEval:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.eval_id = "reliability-eval"
        FakeReliabilityEval.calls.append(kwargs)

    async def arun(self, **kwargs):
        return SimpleNamespace(results=[SimpleNamespace(passed=True)])


class FakePerformanceEval:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.eval_id = "performance-eval"
        FakePerformanceEval.calls.append(kwargs)

    async def arun(self, **kwargs):
        return SimpleNamespace(stats={"mean_runtime": 0.1})
```

Add:

```python
@pytest.mark.asyncio
async def test_run_case_maps_all_eval_types_to_agno_arun(monkeypatch):
    from api.services import agent_eval_runner as runner

    case = {
        "id": "case-1",
        "suite_id": "suite-1",
        "name": "all dims",
        "target_agent_id": "security-operations",
        "input": "Assess CVE-2026-20700",
        "expected_output": "High risk",
        "criteria": "Refuses destructive action without approval",
        "threshold": 8,
        "eval_types": ["accuracy", "agent_as_judge", "reliability", "performance"],
        "expected_tool_calls": ["playbook.cve_lookup"],
        "expected_tool_call_arguments": {"playbook.cve_lookup": {"cve": "CVE-2026-20700"}},
        "allow_additional_tool_calls": False,
        "performance_config": {"warmup_runs": 1, "num_iterations": 2, "measure_runtime": True, "measure_memory": False},
        "enabled": True,
    }

    monkeypatch.setattr(runner.case_store, "get_case", AsyncMock(return_value=case))
    monkeypatch.setattr(runner.case_store, "create_case_run", AsyncMock(return_value={"id": "case-run-1"}))
    monkeypatch.setattr(runner.case_store, "mark_case_run", AsyncMock(return_value={"id": "case-run-1", "status": "passed"}))

    class Runtime:
        def security_agent_context(self, request):
            class Ctx:
                async def __aenter__(self):
                    return SimpleNamespace(
                        id="security-operations",
                        name="Security Agent",
                        model=SimpleNamespace(id="model-1", provider="openai"),
                        arun=AsyncMock(return_value=SimpleNamespace(content="High risk", metrics=None)),
                    )
                async def __aexit__(self, exc_type, exc, tb):
                    return False
            return Ctx()

    deps = runner.AgentEvalRunnerDependencies(
        security_runtime=Runtime(),
        get_eval_db=lambda: "agno-db",
        accuracy_eval_cls=FakeAccuracyEval,
        judge_eval_cls=FakeJudgeEval,
        reliability_eval_cls=FakeReliabilityEval,
        performance_eval_cls=FakePerformanceEval,
    )

    result = await runner.run_case("case-1", actor=SimpleNamespace(id="user-1"), dependencies=deps)

    assert result["status"] == "passed"
    assert FakeAccuracyEval.calls[0]["db"] == "agno-db"
    assert FakeJudgeEval.calls[0]["criteria"] == "Refuses destructive action without approval"
    assert FakeReliabilityEval.calls[0]["expected_tool_calls"] == ["playbook.cve_lookup"]
    assert FakePerformanceEval.calls[0]["num_iterations"] == 2
```

Run: `uv run pytest api/tests/test_agent_eval_runner.py::test_run_case_maps_all_eval_types_to_agno_arun -q`

Expected: FAIL because `agent_eval_runner.py` does not exist.

- [ ] **Step 4: Implement Eval runner**

Create `api/services/agent_eval_runner.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable

from agno.eval.accuracy import AccuracyEval
from agno.eval.agent_as_judge import AgentAsJudgeEval
from agno.eval.performance import PerformanceEval
from agno.eval.reliability import ReliabilityEval

from api.auth.permissions import actor_id
from api.services import agent_eval_case_store as case_store
from api.services.postgres_store import get_async_agno_postgres_db
from api.services.security_run_runtime import DEFAULT_SECURITY_RUN_RUNTIME, SecurityRunRequest, SecurityRunRuntime


@dataclass(frozen=True)
class AgentEvalRunnerDependencies:
    security_runtime: SecurityRunRuntime = DEFAULT_SECURITY_RUN_RUNTIME
    get_eval_db: Callable[[], Any] = get_async_agno_postgres_db
    accuracy_eval_cls: Any = AccuracyEval
    judge_eval_cls: Any = AgentAsJudgeEval
    reliability_eval_cls: Any = ReliabilityEval
    performance_eval_cls: Any = PerformanceEval
```

Implement `run_case()` so it:

- Loads the case.
- Rejects missing or disabled cases with `ValueError`.
- Creates a case-run row.
- Opens `security_runtime.security_agent_context()`.
- Uses `AccuracyEval(input=case["input"], expected_output=case["expected_output"], agent=agent, name=case["name"], db=eval_db).arun(print_summary=False, print_results=False)` when `accuracy` is enabled.
- Captures one `agent.arun(input, session_id=f"eval_{case_run_id}", user_id=actor_id(actor), stream=False)` for judge/reliability when either is enabled.
- Uses `AgentAsJudgeEval(criteria=case["criteria"], threshold=case["threshold"], name=case["name"], db=eval_db).arun(input=case["input"], output=str(response.content), print_summary=False, print_results=False)`.
- Uses `ReliabilityEval(name=case["name"], db=eval_db, agent_response=response, expected_tool_calls=case["expected_tool_calls"], expected_tool_call_arguments=case["expected_tool_call_arguments"], allow_additional_tool_calls=case["allow_additional_tool_calls"]).arun(print_results=False)`.
- Uses `PerformanceEval(func=performance_func, name=case["name"], db=eval_db, warmup_runs=performance_config["warmup_runs"], num_iterations=performance_config["num_iterations"], measure_runtime=performance_config["measure_runtime"], measure_memory=performance_config["measure_memory"]).arun(print_summary=False, print_results=False)` when `performance` is enabled.
- Stores `agno_eval_run_ids` from Eval instances' `eval_id` attributes.
- Marks case run as `passed` only if all enabled dimensions complete without exception.
- Marks case run as `failed` when an exception occurs and records `error_type` and `error_summary`.

Run: `uv run pytest api/tests/test_agent_eval_runner.py::test_run_case_maps_all_eval_types_to_agno_arun -q`

Expected: PASS.

- [ ] **Step 5: Add partial suite failure and replay tests**

Add these tests:

```python
@pytest.mark.asyncio
async def test_run_suite_keeps_running_after_case_failure():
    from api.services import agent_eval_runner as runner

    actor = SimpleNamespace(id="user-1")
    cases = [
        {"id": "case-1", "enabled": True},
        {"id": "case-2", "enabled": True},
    ]

    async def fake_run_case(case_id, actor, suite_run_id=None, replay_of_case_run_id=None, dependencies=None):
        if case_id == "case-1":
            return {"id": "case-run-1", "status": "failed"}
        return {"id": "case-run-2", "status": "passed"}

    with (
        patch.object(runner.case_store, "get_suite", new=AsyncMock(return_value={"id": "suite-1", "enabled": True})),
        patch.object(runner.case_store, "list_cases", new=AsyncMock(return_value=cases)),
        patch.object(runner.case_store, "create_suite_run", new=AsyncMock(return_value={"id": "suite-run-1"})),
        patch.object(runner.case_store, "mark_suite_run", new=AsyncMock(return_value={"id": "suite-run-1", "status": "failed"})) as mark_suite,
        patch.object(runner, "run_case", side_effect=fake_run_case),
    ):
        result = await runner.run_suite("suite-1", actor=actor)

    assert result["status"] == "failed"
    assert mark_suite.await_args.kwargs["summary"] == {"passed": 1, "failed": 1, "errored": 0, "skipped": 0}


@pytest.mark.asyncio
async def test_replay_case_run_links_new_run_to_failed_source():
    from api.services import agent_eval_runner as runner

    with (
        patch.object(runner.case_store, "get_case_run", new=AsyncMock(return_value={"id": "case-run-old", "case_id": "case-1", "status": "failed"})),
        patch.object(runner, "run_case", new=AsyncMock(return_value={"id": "case-run-new", "replay_of_case_run_id": "case-run-old"})) as run_case,
    ):
        result = await runner.replay_case_run("case-run-old", actor=SimpleNamespace(id="user-1"))

    assert result["id"] == "case-run-new"
    run_case.assert_awaited_once_with("case-1", actor=SimpleNamespace(id="user-1"), replay_of_case_run_id="case-run-old", dependencies=None)
```

Use `AsyncMock` on `case_store.list_cases`, `case_store.create_suite_run`, `case_store.mark_suite_run`, `case_store.get_case_run`, and `run_case`.

Run: `uv run pytest api/tests/test_agent_eval_runner.py -q`

Expected: PASS after implementing `run_suite()` and `replay_case_run()`.

- [ ] **Step 6: Add async API static guards**

Extend `api/tests/test_postgres_sql_templates.py`:

```python
from api.services import agent_eval_runner


def test_agent_eval_runner_prefers_agno_async_eval_api() -> None:
    source = inspect.getsource(agent_eval_runner)
    assert ".arun(" in source
    assert ".run(" not in source
    assert "get_async_agno_postgres_db" in source
    assert "get_agno_postgres_db" not in source
    assert "PostgresDb" not in source
```

Run: `uv run pytest api/tests/test_postgres_sql_templates.py::test_agent_eval_runner_prefers_agno_async_eval_api -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add api/services/security_run_runtime.py api/services/agent_eval_runner.py api/tests/test_agent_eval_runner.py api/tests/test_postgres_sql_templates.py
git commit -m "feat: add agent eval runner"
```

---

### Task 5: Agent Evals API Routes

**Files:**
- Create: `api/routes/agent_evals.py`
- Create: `api/tests/test_agent_eval_routes.py`
- Modify: `api/main.py`

**Interfaces:**
- Consumes:
  - Task 2 case store functions.
  - Task 3 result service functions.
  - Task 4 runner functions.
  - `require_agent_eval_write()` and `require_agent_eval_run()`.
- Produces:
  - `/api/agent-evals/suites`
  - `/api/agent-evals/suites/{suite_id}`
  - `/api/agent-evals/cases`
  - `/api/agent-evals/cases/{case_id}`
  - `/api/agent-evals/suites/{suite_id}/runs`
  - `/api/agent-evals/cases/{case_id}/runs`
  - `/api/agent-evals/case-runs/{case_run_id}/replay`
  - `/api/agent-evals/agno-runs`
  - `/api/agent-evals/agno-runs/{eval_run_id}`
  - `/api/agent-evals/trends`
  - `/api/agent-evals/failures`

- [ ] **Step 1: Write route tests**

Create `api/tests/test_agent_eval_routes.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.routes import agent_evals


def actor(role: str = "admin"):
    return SimpleNamespace(id="user-1", email="operator@example.com", role=role, is_superuser=False)


@pytest.mark.asyncio
async def test_create_suite_route_derives_actor_and_calls_store():
    with patch.object(agent_evals.case_store, "create_suite", new=AsyncMock(return_value={"id": "suite-1"})) as create_mock:
        result = await agent_evals.create_eval_suite(
            agent_evals.EvalSuiteCreateRequest(name="Security Regression", tags=["security"]),
            user=actor(),
        )

    assert result == {"id": "suite-1"}
    assert create_mock.await_args.args[1].email == "operator@example.com"


@pytest.mark.asyncio
async def test_run_case_route_requires_run_permission():
    with pytest.raises(HTTPException) as exc:
        await agent_evals.require_agent_eval_run_permission(user=actor("user"))
    assert exc.value.status_code == 403
```

Run: `uv run pytest api/tests/test_agent_eval_routes.py -q`

Expected: FAIL because the route does not exist.

- [ ] **Step 2: Implement route models and handlers**

Create `api/routes/agent_evals.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field

from api.auth.models import User
from api.auth.users import current_active_user
from api.services import agent_eval_case_store as case_store
from api.services import agent_eval_result_service as result_service
from api.services import agent_eval_runner
from api.services.security_policy import require_agent_eval_run, require_agent_eval_write

router = APIRouter(prefix="/api/agent-evals", tags=["Agent Evals"])
```

Add Pydantic models:

```python
EvalType = Literal["accuracy", "agent_as_judge", "reliability", "performance"]


class EvalSuiteCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    target_agent_id: str = "security-operations"
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)


class EvalCaseCreateRequest(BaseModel):
    suite_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    target_agent_id: str = "security-operations"
    input: str = Field(min_length=1)
    expected_output: str = ""
    criteria: str = ""
    threshold: int = Field(default=7, ge=1, le=10)
    eval_types: list[EvalType] = Field(default_factory=lambda: ["accuracy"])
    expected_tool_calls: list[str] = Field(default_factory=list)
    expected_tool_call_arguments: dict[str, Any] = Field(default_factory=dict)
    allow_additional_tool_calls: bool = False
    performance_config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
```

For dependencies:

```python
async def require_agent_eval_read_permission(user: User = Depends(current_active_user)) -> User:
    from api.auth.permissions import has_permission
    if not has_permission(user, "agent_eval:read"):
        raise HTTPException(status_code=403, detail="权限不足")
    return user
```

Use `require_agent_eval_write()` and `require_agent_eval_run()` for write/run dependencies.

Run: `uv run pytest api/tests/test_agent_eval_routes.py -q`

Expected: PASS.

- [ ] **Step 3: Include router in app**

Modify `api/main.py` imports:

```python
from api.routes import (
    agent_evals,
    audit,
    chat,
    collect,
    cve,
    knowledge,
    mcp as mcp_routes,
    os_control,
    settings,
    skills,
    trace,
)
```

Add before `os_control.router`:

```python
app.include_router(agent_evals.router)
```

Add test:

```python
def test_agent_evals_router_is_included() -> None:
    main_source = inspect.getsource(api_main)
    assert "agent_evals" in main_source
    assert "app.include_router(agent_evals.router)" in main_source
```

Run: `uv run pytest api/tests/test_postgres_sql_templates.py::test_agent_evals_router_is_included -q`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add api/routes/agent_evals.py api/main.py api/tests/test_agent_eval_routes.py api/tests/test_postgres_sql_templates.py
git commit -m "feat: expose agent eval routes"
```

---

### Task 6: Frontend API Types And Pure Workbench Helpers

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/composables/useApi.ts`
- Modify: `frontend/src/lib/permissions.ts`
- Create: `frontend/src/modules/agentEvalsWorkbench.ts`
- Create: `frontend/src/modules/agentEvalsWorkbench.test.mjs`
- Modify: `frontend/src/uiShell.test.mjs`

**Interfaces:**
- Produces frontend types:
  - `AgentEvalType`
  - `AgentEvalSuite`
  - `AgentEvalCase`
  - `AgentEvalSuiteRun`
  - `AgentEvalCaseRun`
  - `AgentEvalAgnoRun`
  - `AgentEvalTrendResponse`
  - `AgentEvalFailureResponse`
  - `AgentEvalSuiteCreateRequest`
  - `AgentEvalCaseCreateRequest`
- Produces API composable:
  - `useAgentEvalsApi()`
  - `listSuites()`
  - `createSuite(payload)`
  - `listCases(params)`
  - `createCase(payload)`
  - `runSuite(id)`
  - `runCase(id)`
  - `replayCaseRun(id)`
  - `listAgnoRuns(params)`
  - `getAgnoRun(id)`
  - `getTrends(params)`
  - `listFailures(params)`

- [ ] **Step 1: Add frontend permissions test**

Extend `frontend/src/uiShell.test.mjs`:

```js
assert.match(
  permissions,
  /agent_eval:read/,
  "frontend permissions must include Agent Eval read permission",
)

assert.match(
  permissions,
  /agent_eval:write/,
  "frontend permissions must include Agent Eval write permission",
)

assert.match(
  permissions,
  /agent_eval:run/,
  "frontend permissions must include Agent Eval run permission",
)
```

Run: `cd frontend && /home/shenss/.bun/bin/bun run test:shell`

Expected: FAIL because frontend permissions are missing.

- [ ] **Step 2: Add frontend permissions**

Modify `frontend/src/lib/permissions.ts` user role:

```typescript
"agent_eval:read",
```

Admin remains `"*"`. Do not add eval permissions to guest. Add write/run only to admin by relying on `"*"`.

Run: `cd frontend && /home/shenss/.bun/bin/bun run test:shell`

Expected: PASS for the permission assertions.

- [ ] **Step 3: Write workbench helper tests**

Create `frontend/src/modules/agentEvalsWorkbench.test.mjs`:

```js
import assert from "node:assert/strict"
import {
  buildEvalSummaryCards,
  filterEvalCases,
  toolCallTone,
} from "./agentEvalsWorkbench.ts"

const cases = [
  { id: "case-1", name: "CVE accuracy", enabled: true, eval_types: ["accuracy"], tags: ["cve"], latest_status: "passed" },
  { id: "case-2", name: "MCP reliability", enabled: true, eval_types: ["reliability"], tags: ["mcp"], latest_status: "failed" },
]

assert.deepEqual(
  filterEvalCases(cases, { keyword: "mcp", evalType: "reliability", status: "failed", tag: "" }).map((item) => item.id),
  ["case-2"],
  "eval case filters should combine keyword, type, and latest status",
)

assert.equal(toolCallTone("missing"), "red", "missing expected tools should be red")
assert.equal(toolCallTone("called"), "green", "called expected tools should be green")

assert.deepEqual(
  buildEvalSummaryCards({ suiteCount: 1, caseCount: 2, passed: 1, failed: 1, latestRun: "2026-07-06", performanceSamples: 0 }),
  [
    { label: "Suites", value: 1, hint: "Active regression suites", tone: "blue" },
    { label: "Cases", value: 2, hint: "Enabled and disabled cases", tone: "green" },
    { label: "Pass Rate", value: "50%", hint: "1 passed / 1 failed", tone: "yellow" },
    { label: "Failures", value: 1, hint: "Failed samples available for replay", tone: "red" },
    { label: "Performance", value: 0, hint: "Historical samples only", tone: "blue" },
  ],
  "summary cards should be deterministic and copy-light",
)
```

Modify `frontend/src/uiShell.test.mjs` to import it:

```js
import "./modules/agentEvalsWorkbench.test.mjs"
```

Run: `cd frontend && /home/shenss/.bun/bin/bun run test:shell`

Expected: FAIL because the helper module does not exist.

- [ ] **Step 4: Implement helper module**

Create `frontend/src/modules/agentEvalsWorkbench.ts`:

```typescript
export type EvalCaseFilter = {
  keyword: string
  evalType: string
  status: string
  tag: string
}

export const filterEvalCases = <T extends {
  name?: string
  eval_types?: string[]
  tags?: string[]
  latest_status?: string
}>(cases: T[], filters: EvalCaseFilter): T[] => {
  const keyword = filters.keyword.trim().toLowerCase()
  return cases.filter((item) => {
    const matchesKeyword = !keyword || String(item.name || "").toLowerCase().includes(keyword)
    const matchesType = !filters.evalType || filters.evalType === "all" || (item.eval_types || []).includes(filters.evalType)
    const matchesStatus = !filters.status || filters.status === "all" || item.latest_status === filters.status
    const matchesTag = !filters.tag || filters.tag === "all" || (item.tags || []).includes(filters.tag)
    return matchesKeyword && matchesType && matchesStatus && matchesTag
  })
}

export const toolCallTone = (status: string) => {
  if (status === "missing" || status === "unexpected") return "red"
  if (status === "called" || status === "expected") return "green"
  return "blue"
}
```

Add `buildEvalSummaryCards()` with the exact expected output from the test.

Run: `cd frontend && /home/shenss/.bun/bin/bun run test:shell`

Expected: PASS for the helper tests.

- [ ] **Step 5: Add API types and composable**

Modify `frontend/src/types/index.ts` and `frontend/src/composables/useApi.ts` with the interfaces and `useAgentEvalsApi()` functions listed in this task's interface. Add `agentEvalsRequestFailed` to `ApiFallbackKey`.

Use the same `apiFetch`, `messageFromResponse`, and `messageFromUnknown` pattern already used by `useOsControlApi()`.

Run: `cd frontend && /home/shenss/.bun/bin/bun run test:shell`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/composables/useApi.ts frontend/src/lib/permissions.ts frontend/src/modules/agentEvalsWorkbench.ts frontend/src/modules/agentEvalsWorkbench.test.mjs frontend/src/uiShell.test.mjs
git commit -m "feat: add agent eval frontend API model"
```

---

### Task 7: Evaluation Workbench UI

**Files:**
- Create: `frontend/src/components/AgentEvals.vue`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/modules/shellNavigation.ts`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`
- Modify: `frontend/src/uiShell.test.mjs`

**Interfaces:**
- Consumes:
  - `useAgentEvalsApi()`
  - `filterEvalCases()`
  - `buildEvalSummaryCards()`
  - `toolCallTone()`
- Produces:
  - Dedicated Evaluation screen with KPI strip, filters, case table, run/failure list, detail drawer, and replay action.

- [ ] **Step 1: Write shell mapping tests**

Extend `frontend/src/uiShell.test.mjs`:

```js
const agentEvals = readOptionalSource("components/AgentEvals.vue")

assert.match(
  app,
  /const AgentEvals = defineAsyncComponent\(\(\) => import\("\.\/components\/AgentEvals\.vue"\)\)/,
  "Evaluation must load the dedicated AgentEvals workbench",
)

assert.match(
  app,
  /evaluation:\s*AgentEvals/,
  "Evaluation nav must map to AgentEvals instead of AgentOSControl",
)

assert.doesNotMatch(
  shellNavigation,
  /osControlTabs[\s\S]*"evaluation"/,
  "Evaluation must not remain an OS control tab",
)

assert.match(
  agentEvals,
  /PerformanceEval/,
  "AgentEvals should display the PerformanceEval dimension",
)

assert.doesNotMatch(
  agentEvals,
  /runPerformance|performanceRunButton|@click="[^"]*performance/i,
  "AgentEvals must not expose a manual PerformanceEval run action",
)
```

Run: `cd frontend && /home/shenss/.bun/bin/bun run test:shell`

Expected: FAIL because the component and mapping do not exist.

- [ ] **Step 2: Update navigation mapping**

Modify `frontend/src/App.vue`:

```typescript
const AgentEvals = defineAsyncComponent(() => import("./components/AgentEvals.vue"))
```

Change `componentMap`:

```typescript
evaluation: AgentEvals,
```

Modify `frontend/src/modules/shellNavigation.ts`:

```typescript
export const osControlTabs = new Set<ActiveOsControlModule>([
  "sessions",
  "studio",
  "memory",
  "approvals",
  "scheduler",
])

export const fullCanvasTabs = new Set<ModuleNavId>([
  "dashboard",
  "chat",
  "trace",
  "workflow",
  "mcp",
  "evaluation",
  "sessions",
  "studio",
  "memory",
  "approvals",
  "scheduler",
])
```

Run: `cd frontend && /home/shenss/.bun/bin/bun run test:shell`

Expected: FAIL only because `AgentEvals.vue` is not created.

- [ ] **Step 3: Add i18n copy**

Add `agentEvals` sections to both locale files. The Chinese labels should include:

```typescript
agentEvals: {
  title: "Agent Evals 评测中心",
  subtitle: "安全 Agent regression suite、Agno Eval 历史与失败回放。",
  actions: {
    refresh: "刷新",
    newSuite: "新增 Suite",
    newCase: "新增 Case",
    runSuite: "运行 Suite",
    runCase: "运行 Case",
    replay: "回放",
  },
  tabs: {
    cases: "用例",
    runs: "运行",
    failures: "失败样本",
    trends: "趋势",
  },
  performance: {
    label: "PerformanceEval",
    hiddenRun: "手动运行暂不开放",
  },
}
```

Run: `cd frontend && /home/shenss/.bun/bin/bun run test:shell`

Expected: still FAIL until component exists, with i18n available.

- [ ] **Step 4: Create AgentEvals component**

Create `frontend/src/components/AgentEvals.vue` with:

- KPI strip using existing `ag-stat-strip` / `ag-stat-chip` classes.
- Filter row for suite, eval type, status, keyword.
- Tabs for cases, runs, failures, trends.
- Cases table with name, suite, eval types, latest status, target Agent, tags, actions.
- Failure list and detail drawer.
- Buttons for suite/case run and replay gated by `authStore.hasPermission("agent_eval:run")`.
- Create/edit actions gated by `authStore.hasPermission("agent_eval:write")`.
- A visible PerformanceEval chip with disabled status text, but no click handler that starts performance execution.

Use Element Plus icons from `@element-plus/icons-vue`; use text buttons only for clear commands and icon buttons for compact table actions.

Run: `cd frontend && /home/shenss/.bun/bin/bun run test:shell`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AgentEvals.vue frontend/src/App.vue frontend/src/modules/shellNavigation.ts frontend/src/i18n/locales/zh-CN.ts frontend/src/i18n/locales/en-US.ts frontend/src/uiShell.test.mjs
git commit -m "feat: add agent eval workbench UI"
```

---

### Task 8: End-To-End Verification And Cleanup

**Files:**
- Modify only files needed to fix verification failures from previous tasks.

**Interfaces:**
- Consumes all previous tasks.
- Produces a verified, working feature branch with no dirty unrelated files.

- [ ] **Step 1: Run backend formatting and type checks**

Run:

```bash
uv run ruff check .
uv run ty check .
```

Expected: both commands exit 0.

- [ ] **Step 2: Run backend tests**

Run:

```bash
uv run pytest api/tests
```

Expected: all backend tests pass.

- [ ] **Step 3: Run frontend tests and build**

Run:

```bash
cd frontend && /home/shenss/.bun/bin/bun run test:shell
cd frontend && /home/shenss/.bun/bin/bun run test:auth
cd frontend && /home/shenss/.bun/bin/bun run build
```

Expected: all commands exit 0. If build regenerates tracked `source/` assets, inspect them and include them only if they are intended production output.

- [ ] **Step 4: Start preflight API**

Run:

```bash
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
```

Expected: server reaches `Application startup complete`.

- [ ] **Step 5: Browser smoke**

In another shell, run frontend dev server:

```bash
cd frontend && /home/shenss/.bun/bin/bun run dev -- --host 0.0.0.0 --port 5173
```

Use Playwright:

```bash
playwright-cli open http://localhost:5173/
playwright-cli snapshot
playwright-cli screenshot --filename=/tmp/agno-aios-agent-evals.png
```

Expected:

- Login screen loads.
- With an authenticated admin session, Evaluation opens `Agent Evals 评测中心`.
- The page shows KPI strip, filters, cases/runs/failures/trends tabs.
- PerformanceEval is visible as a dimension, with no manual performance run button.
- No overlapping text on desktop viewport.

- [ ] **Step 6: Stop dev servers**

Stop both `uvicorn` and `vite` sessions with Ctrl-C. Confirm no required command sessions are still running.

- [ ] **Step 7: Final status and commit**

Run:

```bash
git status --short
```

If only intended files are dirty, commit:

```bash
git add api frontend source docs
git commit -m "feat: add agent evals center"
```

Expected: feature implementation is committed with tests and generated frontend output if build changed tracked production assets.
