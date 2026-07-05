# Agno Async API Contract Design

Date: 2026-07-05

## Context

Agno AIOS is migrating runtime persistence and Knowledge flows toward asynchronous APIs for high-concurrency FastAPI routes, MCP middleware, Agent streaming, and background workflows.

The migration should prioritize Agno-owned contracts instead of replacing them with local table ownership. The relevant Agno documentation establishes two key baselines:

- `AsyncPostgresDb` is the async storage class for Agent, Team, Workflow, and AgentOS runtime data, using `postgresql+psycopg_async://...` URLs.
- PgVector async usage is expressed through Agno `Knowledge` and `Agent` async methods such as `ainsert()`, `aload()`, `asearch()`, and `aprint_response()` with `PgVector(...)` as the vector database.

## Decision

Agno-owned runtime and Knowledge behavior must use Agno official async APIs as the default path.

AIOS should not maintain a default local replacement for Agno-owned table contracts. Local async SQLAlchemy remains appropriate for AIOS-owned control-plane data. Local thread isolation remains appropriate for non-DB synchronous work such as model inference, zip extraction, CSV processing, or third-party loaders that Agno exposes only synchronously.

## Architecture

### Agno-Owned Runtime Storage

`api.services.postgres_store` is the single module responsible for constructing Agno `AsyncPostgresDb` instances and PostgreSQL URL/schema settings.

Agent, session, memory, trace, schedule, and AgentOS runtime storage must use `AsyncPostgresDb` or higher-level Agno async APIs. Business modules should not create synchronous `PostgresDb` instances or build synchronous DB connections for Agno-owned runtime data.

### Knowledge And PgVector

Knowledge runtime should follow Agno's documented shape:

- Use `agno.vectordb.pgvector.PgVector`.
- Use `agno.knowledge.knowledge.Knowledge`.
- Use `Knowledge.ainsert()`, `Knowledge.aload()`, `Knowledge.asearch()`, and related Agno async methods from services.
- Use `Agent.arun()` or `Agent.aprint_response()` from Agent runtime paths.

Any local `AsyncPgVector` adapter is a transitional workaround, not the default design. Migration should remove it from the primary runtime path unless a separately approved Agno API gap requires a temporary fallback.

### AIOS-Owned Control Plane

AIOS-owned tables remain under AIOS persistence:

- `app.audit_logs`
- `app.cves`
- `mcp.mcp_tokens`

These tables should continue to use async SQLAlchemy Core/ORM helpers because they represent AIOS product behavior, not Agno runtime state.

## Component Boundaries

### `postgres_store.py`

Responsibilities:

- Build `AsyncPostgresDb` instances.
- Normalize async PostgreSQL URLs.
- Centralize schema and table naming settings.
- Own narrow bootstrap helpers where required.

Non-responsibilities:

- Business-specific direct queries.
- Synchronous Agno DB construction.

### `knowledge_runtime_service.py` And `knowledge_service.py`

Responsibilities:

- Build Agno `Knowledge` with Agno `PgVector`.
- Expose async lifecycle methods for ingest, load, search, list, status, delete, and clear.
- Add AIOS metadata, ownership checks, and presentation projection.

Default behavior:

- Ingest/load/search use Agno Knowledge async methods.
- Contents catalog uses Agno async contents DB.
- Vector index uses Agno PgVector contract.

Exception behavior:

- Delete or clear may keep a narrow async projection only if Agno lacks an async API that preserves AIOS product semantics.
- Any such helper must be internal, documented as an Agno API gap, and covered by tests.

### `security_run_runtime.py`

Responsibilities:

- Build Agents with async model config, prompt loading, MCP tools, Knowledge, Skills, and `AsyncPostgresDb`.
- Stream with `agent.arun(..., stream=True)` or another Agno async execution method.
- Use fallback Agent paths that also avoid synchronous DB I/O.

Non-DB synchronous boundaries:

- Agno `LocalSkills` / `Skills` loading can be isolated with `to_thread.run_sync` if Agno exposes only synchronous file loading.
- This is a filesystem boundary, not a DB contract.

### `chat_session_service.py`, `scheduler_service.py`, `tracing_service.py`, `os_control_service.py`

Responsibilities:

- Prefer `AsyncPostgresDb` convenience APIs for sessions, runs, memory, schedules, traces, and runtime records.
- Keep route layers free of direct Agno table SQL.
- Restrict unavoidable projections to service internals.

Projection rule:

- If Agno async APIs do not expose a required field, filter, or aggregation, an internal async projection may remain.
- The projection must use async DB access, name the Agno API gap, and have tests preventing sync DB regression.

## Data Flow

### Chat And Agent Runtime

1. FastAPI route receives the request.
2. `security_run_runtime` asynchronously reads model config, prompts, MCP config, and enabled skills.
3. Runtime builds an Agno `Agent` with `db=AsyncPostgresDb(...)` and `knowledge=Knowledge(...)`.
4. Runtime executes the Agent through Agno async execution APIs.
5. Agno writes sessions, memory, traces, and related runtime data through async storage.
6. AIOS facades read runtime data through Agno async APIs first, using internal async projections only for documented gaps.

### Knowledge Runtime

1. Ingest routes call Agno Knowledge async load/insert methods.
2. Search routes call Agno Knowledge async search methods.
3. Agent RAG uses Agno Agent async execution, which triggers Knowledge retrieval.
4. AIOS adds user metadata, permissions, and result shaping around the Agno contract.
5. AIOS does not redefine PgVector schema or make a local PgVector implementation the default path.

## Exception Policy

Local implementation is allowed only in these cases:

1. Agno async API does not cover product semantics.
   - Example: AIOS soft archive marker, owner metadata filters, or dashboard aggregation not exposed by Agno APIs.
   - Required shape: async DB access, internal helper, documented gap, regression tests.

2. Non-DB synchronous work.
   - Example: local embedding/rerank, Skill loader file reads, zip extraction, Polars CSV parsing.
   - Required shape: thread isolation or awaitable file APIs, with tests for event-loop safety when practical.

3. CLI, one-off migration, or bootstrap.
   - `asyncio.run()` and setup SQL are acceptable in command-line or startup boundaries.
   - These boundaries must not be called from FastAPI request handlers, MCP middleware, or Agent streaming paths.

Not allowed:

- App-owned shadow tables for Agno-owned runtime state.
- Route-level direct SQL against Agno-owned tables.
- Default local replacement adapters for PgVector.
- Treating an async method name as sufficient proof; runtime behavior and call paths must be verified.

## Testing Strategy

### Static Guards

Extend or preserve static tests that prevent:

- Runtime services or routes importing synchronous `PostgresDb`.
- Agno-owned runtime paths using sync PostgreSQL URLs.
- Route layers directly querying Agno-owned tables.
- Reintroducing app-owned shadow tables for Agno runtime concerns.

Allowed exceptions should be explicit and narrow.

### Contract Tests

Add or preserve tests proving that:

- Chat session facades use Agno async session APIs.
- Scheduler uses `AsyncPostgresDb` schedule APIs.
- Knowledge ingest/search uses Agno `Knowledge` async methods.
- Agent runtime uses Agno async execution APIs.

### Event-Loop Blocking Tests

For known synchronous non-DB boundaries, add tests that show work is isolated from the event loop:

- local embedding/rerank
- Skill loading
- zip extraction
- CSV parsing or large file transforms

### Integration Verification

Stage-level verification remains:

- `uv run ruff check .`
- `uv run ty check .`
- `uv run pytest api/tests`
- frontend shell/auth/build scripts
- uvicorn preprod smoke
- Playwright title and console smoke

## Migration Order

1. Replace Knowledge default runtime path with Agno `PgVector` plus `Knowledge` async methods.
2. Remove or demote local `AsyncPgVector` from the primary path.
3. Audit `chat_session_service`, `scheduler_service`, `tracing_service`, and `os_control_service` for direct Agno table projections that can become `AsyncPostgresDb` calls.
4. Isolate any remaining synchronous non-DB boundaries with thread isolation.
5. Tighten static guard tests around Agno-owned contracts.
6. Update ADR, architecture, and table documentation to match the code.

## Acceptance Criteria

The migration is complete only when:

- Agno-owned runtime and Knowledge paths use Agno official async APIs by default.
- App-owned tables use async SQLAlchemy.
- Every direct Agno-owned projection has a documented Agno API gap and async implementation.
- No FastAPI route, MCP middleware, or Agent streaming path performs synchronous DB I/O.
- PgVector uses Agno `PgVector` and Agno Knowledge async methods as the default path.
- Local adapters are absent from the default path or explicitly documented as temporary gap workarounds.
- Tests and documentation agree with the implementation.
