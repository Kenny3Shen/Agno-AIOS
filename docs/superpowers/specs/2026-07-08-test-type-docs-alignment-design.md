# Test, Type, and Documentation Alignment Design

## Goal

Reduce test-file bulk, remove avoidable `Any` annotations, and update current documentation so it describes the repository as implemented.

## Current Findings

- `frontend/src/uiShell.test.mjs` is the largest test file at about 2,780 lines and mixes shell contracts, module smoke imports, i18n checks, source scanning, and visibility assertions.
- `api/tests/test_knowledge_pipeline.py` is the largest backend test file at about 900 lines and mixes ingest profiles, runtime construction, projection helpers, search, document lifecycle, and delete/clear behavior.
- `Any` usage is concentrated in `api/services/knowledge_service.py`, agent eval service/persistence modules, OS control helpers, and tests. Some `Any` is legitimate at framework or JSON boundaries, but local actor/content/document shapes can be typed more precisely.
- Current factual docs lag the code in small but important places: verification port conventions, `api/tasks/` scope, AgentOS/Scheduler boundary, Knowledge visibility/lifecycle behavior, and FastMCP mounting/lifespan guidance.
- The working tree already contains active Knowledge, Skills, Trace, frontend, and test changes. This work must preserve those changes and build on them in place.

## Scope

### In Scope

- Split oversized tests into focused files without reducing behavioral coverage.
- Extract shared test fakes/helpers when the same fake supports multiple focused test files.
- Replace high-value local `Any` annotations with protocols, typed aliases, or concrete mappings where the runtime shape is known.
- Keep unavoidable `Any` at third-party framework escape hatches, raw JSON adapters, SQLAlchemy row boundaries, and Agno objects that are not practically typed by the public API.
- Update current factual docs: `README.md`, `docs/architecture.md`, `docs/development.md`, `docs/operations.md`, `docs/security.md`, `docs/database-tables.md`, and `docs/agentos-api-migration.md`.
- Use Agno docs for AgentOS, scopes, AsyncPostgresDb, Knowledge/PgVector async behavior, and FastMCP docs for FastAPI ASGI mounting/lifespan claims.

### Out of Scope

- Rewriting historical implementation plans/specs under `docs/superpowers/` unless a current factual document links to an obsolete statement.
- Replacing every `Any` in the repository.
- Changing product behavior, authorization semantics, or UI layout beyond what is required to keep tests and docs aligned.
- Refactoring app-owned persistence boundaries unrelated to the current test/type/doc goal.

## Design

### Test Structure

Backend Knowledge tests will move from one broad file to focused files:

- `api/tests/knowledge_fakes.py`: shared `FakeEmbedder`, strict async Knowledge fake, and simple namespace helpers.
- `api/tests/test_knowledge_ingest_runtime.py`: suffix profiles, reader selection, runtime settings, embedder/reranker construction, RAG settings, and status.
- `api/tests/test_knowledge_projection.py`: metadata compaction, owner/visibility filtering, status/chunk count, and search result projection.
- `api/tests/test_knowledge_lifecycle.py`: async insert/search/list/update/rebuild/delete/clear lifecycle behavior.

The original `test_knowledge_pipeline.py` should either be removed or reduced to a thin compatibility import-free file only if needed for pytest discovery. The preferred result is no monolithic Knowledge pipeline test file.

Frontend shell tests will move source-contract assertions out of `frontend/src/uiShell.test.mjs` into focused module test files while preserving the `bun run test:shell` entry point:

- The entry point keeps importing all shell/module tests.
- Long source scans for shell layout, i18n, visibility controls, and Knowledge/Skills/MCP contracts move to smaller files under `frontend/src/modules/`.
- Shared source readers/assertion helpers should be local to tests and not shipped into runtime bundles.

### Type Reduction

Use narrow typing where it improves local contracts:

- Add actor/user protocols for code that only needs `id`, `role`, or `is_superuser`.
- Add metadata and JSON aliases for dictionary payloads that are JSON-like but not arbitrary Python objects.
- Add Knowledge content/document protocols for projection helpers that currently access known attributes through `getattr`.
- Tighten test fakes so `ty` can validate fake interfaces without broad `Any`.

Do not force unstable third-party objects into inaccurate local models. Framework boundaries may keep `Any` when the public API itself exposes dynamic objects.

### Documentation Alignment

Docs should describe current behavior only:

- README remains the project entry point and quick command index.
- `docs/development.md` must reflect WSL2, `uv + ruff + ty`, Bun dependency rules, port `8001` for preflight smoke, and screenshot-backed frontend verification.
- `docs/architecture.md` must reflect AgentOS on the FastAPI base app, integrated FastMCP endpoint, Knowledge async lifecycle, visibility metadata, and Scheduler native AgentOS route boundary.
- `docs/operations.md` must align startup commands, runtime file locations, MCP token behavior, and current tasks.
- `docs/security.md` must align FastAPI Users, AgentOS scopes, backend-only enforcement, resource ownership, and audit requirements.
- `docs/database-tables.md` must keep Agno-owned vs AIOS-owned table boundaries current.
- `docs/agentos-api-migration.md` must distinguish migrated Scheduler behavior from retained AIOS facades.

## Verification

- `uv run ruff check <changed python files>`
- `uv run ty check <changed python files>`
- Targeted `uv run pytest` for split backend tests after each test move.
- Final `uv run pytest api/tests`.
- `cd frontend && /home/shenss/.bun/bin/bun run test:shell`
- `cd frontend && /home/shenss/.bun/bin/bun run test:auth`
- `cd frontend && /home/shenss/.bun/bin/bun run build`
- `uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8001` plus relevant smoke checks when runtime/docs changes touch app startup or frontend behavior.
- For UI-visible changes, use Playwright screenshot checks at desktop and narrow widths before claiming completion.

## Review Gate

After implementation and verification, request code review using the `requesting-code-review` workflow. Critical and important findings must be fixed or explicitly rebutted with code/test evidence before the goal can be considered complete.
