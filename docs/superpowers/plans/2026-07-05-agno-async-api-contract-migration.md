# Agno Async API Contract Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Agno-owned runtime and Knowledge behavior back onto Agno's official async API contract by default, especially `Knowledge` + `agno.vectordb.pgvector.PgVector` with async methods such as `ainsert`, `aload`, `asearch`, and Agent `aprint_response` / `arun`, while keeping AIOS-owned tables on async SQLAlchemy.

**Architecture:** Agno-owned data stays behind Agno abstractions. `api.services.postgres_store` remains the single source for Agno `AsyncPostgresDb` construction and Postgres URLs. `api.services.knowledge_runtime_service` builds a standard Agno `Knowledge` using Agno `PgVector`; lifecycle code calls Knowledge async methods only. AIOS-owned projection, policy, audit, MCP token, CVE, and dashboard tables remain in explicit async SQLAlchemy repositories. Any direct projection over Agno-owned tables must be documented as an Agno API gap and implemented with non-blocking I/O.

**Tech Stack:** Python 3 with `uv`, FastAPI, Agno, Agno `AsyncPostgresDb`, Agno `Knowledge`, Agno `PgVector`, SQLAlchemy async for app-owned persistence, pytest, ruff, ty, Bun/Vite frontend.

## Global Constraints

- Prefer official Agno async APIs for Agno-owned runtime and Knowledge paths. The PgVector default runtime path must construct `agno.vectordb.pgvector.PgVector`, not `api.services.async_pgvector.AsyncPgVector`.
- Follow the Agno docs contract from `https://docs.agno.com/knowledge/vector-stores/pgvector/overview` and `https://docs.agno.com/knowledge/vector-stores/pgvector/usage/async-pgvector-db`: construct `PgVector(...)`, wrap it in `Knowledge(...)`, and call async Knowledge or Agent APIs for high-throughput non-blocking flows.
- App-owned tables continue to use async SQLAlchemy. Do not move `app.*`, `mcp.*`, CVE, audit, auth, or product-owned control-plane tables into Agno.
- If a route must read or mutate Agno-owned data directly because Agno has no async API for that product requirement, document it as an "Agno API gap projection" in `docs/architecture.md` and `docs/database-tables.md`.
- Keep synchronous CPU or third-party boundaries explicit. SentenceTransformer embedding, rerank, zip install, CSV parsing, dotenv loading, and logging setup may use `anyio.to_thread.run_sync`; do not use thread offloading to hide sync DB I/O in runtime routes.
- Use TDD for behavior changes: write or update the failing guard first, run the focused test to see it fail, implement, then rerun the focused test to see it pass.
- Use `apply_patch` for file edits. Do not revert unrelated dirty work.

---

## Task 1: Switch Knowledge Runtime To Agno PgVector

- [ ] Update `api/tests/test_knowledge_pipeline.py`.

  Rename `test_runtime_builds_async_pgvector_knowledge_with_small_interface` to `test_runtime_builds_agno_pgvector_knowledge_with_small_interface`.

  Change the fake class and patch target:

  ```python
  class FakePgVector:
      def __init__(self, **kwargs: Any) -> None:
          captured["vector"] = kwargs

  ...
  with (
      patch.object(knowledge_runtime_service, "PgVector", FakePgVector),
      patch.object(knowledge_runtime_service, "Knowledge", FakeKnowledge),
  ):
      ...
  ```

  Keep assertions for `table_name`, `schema`, `search_type`, `prefix_match`, `contents_db`, `max_results`, and `readers`. This test should fail before implementation because `knowledge_runtime_service` currently exposes `AsyncPgVector`, not `PgVector`.

- [ ] Run the focused red test:

  ```bash
  uv run pytest api/tests/test_knowledge_pipeline.py::test_runtime_builds_agno_pgvector_knowledge_with_small_interface
  ```

  Expected red output: pytest fails with an `AttributeError` for missing `PgVector` on `knowledge_runtime_service`, or the fake `PgVector` is not called.

- [ ] Update `api/services/knowledge_runtime_service.py`.

  Replace:

  ```python
  from api.services.async_pgvector import AsyncPgVector
  ```

  with:

  ```python
  from agno.vectordb.pgvector import PgVector
  ```

  Replace:

  ```python
  vector_db = AsyncPgVector(
  ```

  with:

  ```python
  vector_db = PgVector(
  ```

  Preserve the existing arguments: `table_name`, `schema`, `db_url`, `embedder`, `search_type`, `distance=Distance.cosine`, `prefix_match`, `vector_score_weight`, `content_language`, and `reranker`.

- [ ] Run the focused green test:

  ```bash
  uv run pytest api/tests/test_knowledge_pipeline.py::test_runtime_builds_agno_pgvector_knowledge_with_small_interface
  ```

- [ ] Commit:

  ```bash
  git add api/services/knowledge_runtime_service.py api/tests/test_knowledge_pipeline.py
  git commit -m "Use Agno PgVector for knowledge runtime"
  ```

## Task 2: Replace Static Guards That Protected Local AsyncPgVector

- [ ] Update `api/tests/test_postgres_sql_templates.py`.

  Replace `test_knowledge_runtime_uses_native_async_pgvector_adapter` with `test_knowledge_runtime_uses_agno_pgvector_contract`.

  The new test should assert:

  ```python
  runtime_source = inspect.getsource(knowledge_runtime_service)
  assert "from agno.vectordb.pgvector import PgVector" in runtime_source
  assert "vector_db = PgVector(" in runtime_source
  assert "AsyncPgVector" not in runtime_source
  ```

  Remove assertions that inspect `api.services.async_pgvector.AsyncPgVector` internals. Keep the rest of the static async lifecycle guards in the file unchanged.

- [ ] Run the focused test:

  ```bash
  uv run pytest api/tests/test_postgres_sql_templates.py::test_knowledge_runtime_uses_agno_pgvector_contract
  ```

- [ ] Search for runtime references:

  ```bash
  rg -n "AsyncPgVector|async_pgvector" api docs
  ```

  Expected after Task 1 and Task 2 edits: references remain only in docs describing the old state and possibly the module file itself.

- [ ] Delete `api/services/async_pgvector.py` if no production import remains:

  ```bash
  git rm api/services/async_pgvector.py
  ```

  If a production import remains, stop this task and migrate that caller to the Agno `PgVector` contract before deletion.

- [ ] Run:

  ```bash
  uv run pytest api/tests/test_postgres_sql_templates.py api/tests/test_knowledge_pipeline.py
  ```

- [ ] Commit:

  ```bash
  git add api/tests/test_postgres_sql_templates.py api/tests/test_knowledge_pipeline.py api/services/knowledge_runtime_service.py
  git add -u api/services/async_pgvector.py
  git commit -m "Retire local PgVector runtime adapter"
  ```

## Task 3: Lock Knowledge Lifecycle To Agno Async Methods

- [ ] Add or update contract tests in `api/tests/test_knowledge_pipeline.py` for `KnowledgeBaseLifecycle`.

  Ensure fake Knowledge objects record calls to:

  - `ainsert` for `add_text_document_async`
  - `ainsert` for `add_file_document_async`
  - `asearch` for `search_documents_async`
  - `aget_content`, `aget_content_by_id`, and the existing async deletion projection for list/delete/clear

  The tests must fail if lifecycle methods call `insert`, `search`, `load`, `get_content`, `get_content_by_id`, `remove_content_by_id`, or `remove_all_content`.

- [ ] Add static assertions to `api/tests/test_postgres_sql_templates.py::test_knowledge_async_lifecycle_uses_agno_async_api`:

  ```python
  assert ".insert(" not in source
  assert ".search(" not in source
  assert ".load(" not in source
  assert ".get_content(" not in source
  assert ".get_content_by_id(" not in source
  ```

  Keep the positive assertions for `await knowledge.ainsert`, `await knowledge.asearch`, and `await knowledge.aget_content`.

- [ ] Run focused tests:

  ```bash
  uv run pytest api/tests/test_knowledge_pipeline.py api/tests/test_postgres_sql_templates.py::test_knowledge_async_lifecycle_uses_agno_async_api
  ```

- [ ] If any lifecycle code violates the contract, update only `api/services/knowledge_service.py` to use the async Agno method already represented by the test. Preserve owner filtering, metadata shape, and current response payloads.

- [ ] Commit:

  ```bash
  git add api/services/knowledge_service.py api/tests/test_knowledge_pipeline.py api/tests/test_postgres_sql_templates.py
  git commit -m "Guard knowledge lifecycle async Agno contract"
  ```

## Task 4: Audit Agno-Owned Direct Projections

- [ ] Run:

  ```bash
  rg -n "async_pool|aget_|get_sessions|get_traces|get_all_sessions|DELETE FROM|SELECT .*agno|FROM .*agno|knowledge\\." api/services api/routes api/tasks
  ```

- [ ] Classify each hit:

  - Agno official async API: keep.
  - AIOS-owned async SQLAlchemy table: keep.
  - CLI/bootstrap/one-off migration: keep with comment only if the intent is unclear.
  - Agno API gap projection: keep only when it is async and documented.
  - Sync runtime DB I/O: migrate before continuing.

- [ ] Update docs for the current projection list:

  - `docs/architecture.md`: add a short "Agno API gap projections" paragraph under Knowledge/runtime architecture. Include vector-row delete/clear, chunk-count dashboard projection, content-id hydration, Agno tracing payload shaping, and AgentOS control payload where applicable.
  - `docs/database-tables.md`: update the "Table ownership" and "Runtime persistence migration status" sections so they say the default Knowledge vector runtime uses Agno `PgVector`, while the direct projections are narrow async product views over Agno-owned tables.
  - `docs/adr/0008-sqlalchemy-for-control-plane-data.md`: replace the local `AsyncPgVector` rationale with the accepted rule: prefer Agno `PgVector` + Knowledge async APIs; add async SQLAlchemy projections only for app-owned data or documented Agno API gaps.

- [ ] Run doc/static checks:

  ```bash
  uv run pytest api/tests/test_postgres_sql_templates.py
  ```

- [ ] Commit:

  ```bash
  git add docs/architecture.md docs/database-tables.md docs/adr/0008-sqlalchemy-for-control-plane-data.md api/tests/test_postgres_sql_templates.py
  git commit -m "Document Agno async API ownership boundaries"
  ```

## Task 5: Preserve Event-Loop Isolation For Non-DB Sync Boundaries

- [ ] Keep the existing BGE embedder async methods in `api/services/knowledge_service.py` thread-isolated:

  ```python
  return await to_thread.run_sync(self.get_embedding, text)
  return await to_thread.run_sync(self.get_embedding_and_usage, text)
  ```

- [ ] Keep the existing skill loader behavior in `api/services/security_run_runtime.py` thread-isolated:

  ```python
  return await to_thread.run_sync(_load_local_skills, enabled_dirs)
  ```

- [ ] Run focused tests:

  ```bash
  uv run pytest api/tests/test_knowledge_pipeline.py::test_bge_async_query_embedding_runs_sync_encoder_off_event_loop api/tests/test_security_run_runtime.py::test_enabled_skills_loads_sync_agno_skills_off_event_loop
  ```

- [ ] Add a static note to `docs/architecture.md` if missing: these thread boundaries are CPU/filesystem/third-party integration boundaries, not sync DB escape hatches.

- [ ] Commit only if code or docs changed:

  ```bash
  git add api/services/knowledge_service.py api/services/security_run_runtime.py api/tests/test_knowledge_pipeline.py api/tests/test_security_run_runtime.py docs/architecture.md
  git commit -m "Document non-DB async runtime boundaries"
  ```

## Task 6: Full Verification And Runtime Smoke

- [ ] Run backend static and unit checks:

  ```bash
  uv run ruff check .
  uv run ty check .
  uv run pytest api/tests
  ```

- [ ] Run frontend checks:

  ```bash
  cd frontend && bun run test:shell
  cd frontend && bun run test:auth
  cd frontend && bun run build
  ```

- [ ] Start preprod:

  ```bash
  uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
  ```

  If port 8000 is occupied, use port 8001 and record that in the final report.

- [ ] Use `playwright-cli` to smoke test:

  - `/api/health` returns 200.
  - `/api/auth/oauth/providers` returns 200.
  - The frontend loads and the page title remains `Agno AIOS 安全中台`.
  - Browser console has zero errors.

- [ ] Stop browser and uvicorn. Do not leave background sessions running.

- [ ] Final audit command:

  ```bash
  rg -n "AsyncPgVector|async_pgvector|knowledge\\.insert\\(|knowledge\\.search\\(|knowledge\\.load\\(|agent\\.print_response\\(" api docs
  ```

  Expected result: no production runtime references to `AsyncPgVector` or sync Knowledge/Agent methods. Historical docs should either be removed or explicitly describe the retired adapter as old state.

- [ ] Final commit if verification fixes changed files. First run:

  ```bash
  git status --short
  ```

  If the output is empty, no final verification commit is needed. If verification fixes changed files, review the exact paths from `git status --short`, stage only those paths, and commit:

  ```bash
  git commit -m "Verify Agno async API migration"
  ```
