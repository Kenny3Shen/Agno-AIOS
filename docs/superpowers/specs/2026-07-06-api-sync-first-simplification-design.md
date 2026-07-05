# API Sync-First Simplification Design

Date: 2026-07-06

## Context

Agno AIOS currently has two overlapping async design pressures:

- Agno Runtime, app-owned database access, streaming, HTTP clients, and ASGI
  integrations need native async APIs.
- Some local control-plane utilities became async only because their callers are
  async, even when the work is pure validation, projection, small JSON config
  access, or local file metadata parsing.

The goal of this design is to simplify the code by removing async surfaces that
do not carry real asynchronous behavior, while avoiding event-loop blocking
regressions when a removed adapter previously isolated expensive synchronous
work.

This supersedes any local convention that file-backed config routes must use an
async wrapper. Local config and local metadata services should be sync-first
unless they are on a proven hot path or perform unbounded blocking work inside an
async-only runtime path.

## Decision

Use a sync-first API model for AIOS local logic.

Keep `async def` only when a function directly awaits native async work or is
part of a framework/runtime contract that must be async. Do not preserve public
async service wrappers merely to make callers uniform.

Async adapters such as `to_thread.run_sync(...)` are not a default service
pattern. They are allowed only as a narrow event-loop blocking isolation at the
boundary where expensive synchronous work still has to run from an async call
path. If the boundary can be moved to a synchronous endpoint, startup phase,
cache refresh, or background job, prefer moving the boundary over keeping an
async service adapter.

## Goals

- Reduce unnecessary coroutine wrappers in AIOS services and routes.
- Make pure logic visibly synchronous and easier to test.
- Keep Agno Runtime and AIOS database paths correctly async.
- Avoid blocking FastAPI, streaming, WebSocket, and Agent runtime event loops.
- Remove tests that force local file-backed configuration through async wrappers.
- Keep the implementation incremental and behavior-preserving.

## Non-Goals

- Do not convert Agno Runtime APIs to sync.
- Do not introduce a new allowlist system for fake async functions.
- Do not replace async SQLAlchemy persistence with sync SQLAlchemy.
- Do not remove blocking isolation where removal would move large sync work onto
  the event loop.
- Do not redesign the UI or product API shapes in this cleanup.

## Async Boundary Rules

### Must Remain Async

These paths keep async APIs:

- Agno Agent, Knowledge, AgentOS, scheduler, approval, trace, memory, and eval
  runtime calls that expose async methods.
- App-owned database persistence through async SQLAlchemy.
- HTTP clients using `httpx.AsyncClient`.
- Streaming responses, async generators, WebSockets, and ASGI mounts.
- FastMCP runtime paths.
- FastAPI Users or framework hooks only when the framework requires async.

### Should Become Sync

These paths should use normal synchronous functions:

- Permission checks that only inspect the current user permissions.
- Request-independent constants, redirects, health responses, and settings
  projections when they do not await I/O.
- Pydantic/value normalization, masking, DTO projection, and validation.
- Manifest parsing and configuration flag derivation.
- Small bounded local JSON/TOML config reads and writes used by low-frequency
  admin endpoints.
- Agent eval suite/case value builders that only shape data before persistence.

### Needs Boundary Review Before Adapter Removal

These paths can block or scale with input size, so adapter removal is unsafe
unless the execution boundary moves:

- Skill archive validation, zip extraction, and file moves.
- Recursive Skill discovery or third-party Skill loader construction on hot
  Agent paths.
- Large CVE file transforms, CSV/Parquet/Polars processing, or bulk imports.
- Local model/embedding/rerank calls if they are synchronous.
- Any sync operation performed during chat streaming, WebSocket handling, or
  per-request Agent construction.

## Adapter Removal Risk Model

Every async adapter removal is classified by call context and blocking cost.

### Direct Removal

Use direct removal when the function is pure CPU-light logic or bounded local
configuration work.

Examples:

- `api.auth.permissions.require_permission(...)` generated dependency.
- `api.routes.os_control` module permission dependency helpers.
- `api.mcp.config._legacy_mcp_config_file()`.
- `api.mcp.config.services_from_config_async(data)` when `data` is already
  loaded.
- Model config projection and secret masking.

Expected result:

- Function becomes synchronous.
- Callers stop awaiting it.
- Routes become synchronous only when their whole call path no longer awaits
  native async work.

### Boundary Move

Use boundary move when the work is synchronous and potentially expensive, but the
product flow does not require an async request path.

Examples:

- Skill upload and installation can become a synchronous management operation if
  audit and response behavior are also moved to a synchronous-compatible
  boundary.
- Startup-only local cache construction can run before serving traffic.
- Low-frequency maintenance tasks can run as background jobs with status
  polling.

Expected result:

- The expensive synchronous work does not run on the main event loop.
- The service API remains synchronous.
- Any async coordination happens outside the service, not as a generic service
  wrapper.

### Keep Local Blocking Isolation

Keep a local `to_thread` or equivalent only when all are true:

1. The caller is in an async-only path.
2. The work is large enough to block the event loop.
3. Moving the boundary would change product semantics or require a larger
   feature redesign.

Examples:

- Skill zip installation if the route must remain async because it immediately
  writes async audit records.
- LocalSkills construction inside Agent runtime until enabled Skill directories
  are cached or loaded outside the run path.

Expected result:

- The sync core remains a normal synchronous function.
- The isolation is at the call site, close to the async boundary.
- The adapter is documented as event-loop protection, not as the public service
  API style.

## Component Plan

### Permissions

Convert permission dependency functions that only inspect `User.permissions` to
synchronous functions.

Affected areas:

- `api/auth/permissions.py`
- `api/routes/os_control.py`

Routes using these dependencies should not change behavior or permission names.

### Model Config Service

Convert local model config APIs to sync-first names:

- `load_model_config_store()`
- `load_model_config()`
- `public_model_config()`
- `save_model_config(...)`
- `get_model_for_run(...)`

The JSON file is small, app-local, and used by low-frequency admin/runtime
configuration paths. This does not justify a public async service facade.

Routes and runtime code should call the sync functions directly unless they are
inside a hot async path where repeated file access should instead be replaced by
cache or dependency injection.

### MCP Config Service

Keep MCP token database operations async because they use app-owned async
persistence.

Convert local config operations to sync where they only read/write JSON/TOML or
derive flags:

- config file path helpers
- legacy TOML migration helper
- config normalization
- service flag projection
- MCP upload manifest parsing

For routes that both update local config and write async audit events, the route
may remain async, but the local config call itself should be sync.

### Skill Service

Keep the core Skill operations synchronous:

- list Skill directories and metadata
- parse `SKILL.md`
- list scripts
- update Skill enabled config
- validate and install uploaded zip archives

For large blocking work, do not hide the cost behind a public async service
wrapper. Choose one boundary:

- synchronous route if the whole endpoint can be synchronous,
- background job if immediate installation is not required,
- or route-local blocking isolation if async audit and immediate response must
  remain unchanged.

Agent runtime should avoid loading Skill directories on every run if possible.
The preferred follow-up is a cache invalidated by Skill config changes.

### Settings Routes

Convert no-await settings and health-style handlers to sync where their whole
call path is sync.

Keep async only for:

- model connectivity testing through `httpx.AsyncClient`,
- audit writes through async persistence,
- any future operation that awaits real async I/O.

### Agent Eval Service

Keep persistence functions async because they use async SQLAlchemy.

Move pure suite/case command construction, normalization, and projection into
synchronous helpers that are unit-tested without `pytest.mark.asyncio`.

This reduces async noise without changing the database boundary.

### Security Runtime

Do not block Agent streaming paths with sync file scans or zip work.

Allowed cleanup:

- use sync model config lookup only if it is cached or demonstrably bounded,
  otherwise introduce a cache instead of adding async wrappers;
- keep local blocking isolation for LocalSkills construction until Skill loading
  is moved to startup or an invalidated cache.

## Test Updates

Remove tests that assert local file-backed config must use async wrappers.

Replace them with tests that assert the intended boundaries:

- local config services expose sync functions;
- route handlers do not await sync config projection helpers;
- async SQLAlchemy persistence remains async;
- Agno Runtime paths do not use sync DB APIs;
- large blocking sync work is not run directly inside async streaming/runtime
  paths.

Existing tests that protect Agno-owned async contracts should stay.

## Migration Order

1. Update tests that currently enforce async wrappers around local config.
2. Convert permission dependency helpers to sync.
3. Convert model config local file APIs to sync and update callers.
4. Convert MCP local config helpers to sync while keeping token DB async.
5. Convert Skill service public local-file APIs to sync; decide per route whether
   the execution boundary can move or must keep local blocking isolation.
6. Extract sync builders from agent eval services while keeping persistence
   async.
7. Review security runtime hot paths for repeated local file scans and replace
   them with cache or retained local blocking isolation.
8. Run backend validation and type/lint checks.

## Acceptance Criteria

- No public service function is async unless it awaits native async work or is a
  required async framework/runtime contract.
- Local config, permission, parsing, projection, and small metadata operations
  are synchronous.
- Removing an async adapter never causes large synchronous work to run directly
  on an event loop.
- Any remaining `to_thread` usage is local to an async boundary and justified by
  blocking cost.
- Agno Runtime and app-owned database paths remain async.
- Tests no longer encode "file-backed config must be async" as a rule.
- `uv run pytest api/tests`, `uv run ruff check .`, and `uv run ty check .`
  pass after implementation.
