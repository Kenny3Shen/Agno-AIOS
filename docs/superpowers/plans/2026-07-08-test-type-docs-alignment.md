# Test, Type, and Documentation Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split oversized tests, reduce avoidable `Any` annotations, and update current factual documentation to match the Agno AIOS codebase.

**Architecture:** Preserve the current active working tree and make scoped edits in place. Move large test contracts into smaller focused files without changing behavior, then tighten local typing at known actor/content/JSON boundaries. Update only current factual docs and verify against local code plus Agno/FastMCP documentation.

**Tech Stack:** Python 3.12, FastAPI, Agno, FastMCP, SQLAlchemy Async, Pydantic, Vue 3, TypeScript, Bun, `uv`, `ruff`, `ty`, `pytest`, Playwright.

## Global Constraints

- Preserve existing uncommitted Knowledge, Skills, Trace, frontend, and test changes.
- Do not reduce test coverage while splitting files.
- Keep unavoidable `Any` at third-party framework, raw JSON, SQLAlchemy row, and Agno dynamic object boundaries.
- Update current factual docs only; do not rewrite historical `docs/superpowers/` plans/specs except this active plan/spec.
- Use Agno docs for AgentOS, scopes, AsyncPostgresDb, Knowledge/PgVector async behavior, and FastMCP docs for FastAPI ASGI mounting/lifespan claims.
- Run targeted verification after each risky move and full verification before completion.

---

### Task 1: Split Backend Knowledge Tests

**Files:**
- Create: `api/tests/knowledge_fakes.py`
- Create: `api/tests/test_knowledge_ingest_runtime.py`
- Create: `api/tests/test_knowledge_projection.py`
- Create: `api/tests/test_knowledge_lifecycle.py`
- Modify/Delete: `api/tests/test_knowledge_pipeline.py`

**Interfaces:**
- Produces: `FakeEmbedder`
- Produces: `StrictAsyncKnowledge`
- Produces: focused pytest files that preserve every existing `test_knowledge_pipeline.py` test function.

- [ ] **Step 1: Capture current Knowledge test inventory**

Run:

```bash
rg -n "^(class|def|async def|@pytest)" api/tests/test_knowledge_pipeline.py
```

Expected: all existing fake classes and test functions are visible before moving code.

- [ ] **Step 2: Move shared fakes**

Create `api/tests/knowledge_fakes.py` containing `FakeEmbedder` and `StrictAsyncKnowledge` from the original file, with imports required by those fakes.

- [ ] **Step 3: Split tests by behavior group**

Move ingest/runtime tests into `test_knowledge_ingest_runtime.py`, projection tests into `test_knowledge_projection.py`, and async lifecycle tests into `test_knowledge_lifecycle.py`. Replace local fake definitions with:

```python
from api.tests.knowledge_fakes import FakeEmbedder, StrictAsyncKnowledge
```

- [ ] **Step 4: Verify split backend tests**

Run:

```bash
uv run pytest api/tests/test_knowledge_ingest_runtime.py api/tests/test_knowledge_projection.py api/tests/test_knowledge_lifecycle.py
```

Expected: pytest exits 0 and all moved Knowledge tests pass.

- [ ] **Step 5: Verify monolith removal**

Run:

```bash
wc -l api/tests/test_knowledge_pipeline.py api/tests/test_knowledge_ingest_runtime.py api/tests/test_knowledge_projection.py api/tests/test_knowledge_lifecycle.py api/tests/knowledge_fakes.py
```

Expected: `test_knowledge_pipeline.py` is removed or no longer the largest backend test file.

### Task 2: Split Frontend Shell Test Contracts

**Files:**
- Create: `frontend/src/modules/testSource.ts` or focused `.mjs` helper if TypeScript runtime loading is not needed
- Create/Modify: focused tests under `frontend/src/modules/`
- Modify: `frontend/src/uiShell.test.mjs`

**Interfaces:**
- Produces: `sourcePath(relativePath)`, `readSource(relativePath)`, `readOptionalSource(relativePath)`, and source assertion helpers for frontend shell tests.
- Preserves: `cd frontend && /home/shenss/.bun/bin/bun run test:shell`.

- [ ] **Step 1: Capture current shell test sections**

Run:

```bash
rg -n "assert\\.|assertTextOrder|assertNoPillStatChip|const [a-zA-Z].*= read" frontend/src/uiShell.test.mjs
```

Expected: large source-contract sections are identified before moving them.

- [ ] **Step 2: Move source readers/helpers**

Extract source reading and repeated assertion helpers from `uiShell.test.mjs` into a focused test helper under `frontend/src/modules/`.

- [ ] **Step 3: Move focused source contracts**

Move shell layout/i18n/visibility component assertions into smaller module tests. Keep `uiShell.test.mjs` as an entry point importing those tests and only retaining cross-module smoke checks that do not fit a smaller file.

- [ ] **Step 4: Verify shell tests**

Run:

```bash
cd frontend && /home/shenss/.bun/bin/bun run test:shell
```

Expected: Bun exits 0.

- [ ] **Step 5: Verify size reduction**

Run:

```bash
wc -l frontend/src/uiShell.test.mjs frontend/src/modules/*.test.mjs
```

Expected: `frontend/src/uiShell.test.mjs` is substantially smaller and focused.

### Task 3: Reduce Avoidable `Any` at Local Boundaries

**Files:**
- Modify: `api/auth/claims.py`
- Modify: `api/auth/visibility.py`
- Modify: `api/auth/ownership.py`
- Modify: `api/services/knowledge_document_service.py`
- Modify: `api/services/knowledge_service.py`
- Modify tests touched by the new typing.

**Interfaces:**
- Produces: local protocols or aliases for actor/user, JSON-like mappings, and Knowledge content/document projections.
- Preserves: existing route/service behavior.

- [ ] **Step 1: Add typed local actor/content shapes**

Add `Protocol` definitions or aliases only where local code reads known attributes such as `id`, `role`, `is_superuser`, `metadata`, `created_at`, and document projection fields.

- [ ] **Step 2: Replace safe `Any` occurrences**

Replace `Any` in auth helper signatures and Knowledge projection helpers where the protocol covers all accessed fields. Leave dynamic Agno and SQLAlchemy edges unchanged.

- [ ] **Step 3: Verify Python typing and tests**

Run:

```bash
uv run ruff check api/auth/claims.py api/auth/visibility.py api/auth/ownership.py api/services/knowledge_document_service.py api/services/knowledge_service.py api/tests/knowledge_fakes.py api/tests/test_knowledge_ingest_runtime.py api/tests/test_knowledge_projection.py api/tests/test_knowledge_lifecycle.py
uv run ty check api/auth/claims.py api/auth/visibility.py api/auth/ownership.py api/services/knowledge_document_service.py api/services/knowledge_service.py api/tests/knowledge_fakes.py api/tests/test_knowledge_ingest_runtime.py api/tests/test_knowledge_projection.py api/tests/test_knowledge_lifecycle.py
uv run pytest api/tests/test_knowledge_ingest_runtime.py api/tests/test_knowledge_projection.py api/tests/test_knowledge_lifecycle.py
```

Expected: all commands exit 0, or reported failures are fixed before moving on.

### Task 4: Update Current Factual Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/development.md`
- Modify: `docs/operations.md`
- Modify: `docs/security.md`
- Modify: `docs/database-tables.md`
- Modify: `docs/agentos-api-migration.md`

**Interfaces:**
- Produces: docs that match local code and the documented Agno/FastMCP integration facts.

- [ ] **Step 1: Reconcile docs against code**

Check route registration, task files, startup commands, runtime file locations, and frontend scripts using local files.

- [ ] **Step 2: Update stale statements**

Edit docs to reflect current facts: WSL2, `uv + ruff + ty`, Bun dependency handling, port `8001` preflight command, AgentOS native Scheduler route boundary, Knowledge async lifecycle/visibility metadata, and FastMCP ASGI mount/lifespan guidance.

- [ ] **Step 3: Verify docs references**

Run:

```bash
rg -n "scheduler_service|/api/os/scheduler|MySQL-to-Postgres|port 8000|npm install|TODO|TBD" README.md docs
```

Expected: any matches are either intentional historical context or corrected.

### Task 5: Final Verification and Review

**Files:**
- All changed files.

**Interfaces:**
- Produces: verification evidence and a code-review request.

- [ ] **Step 1: Run final backend verification**

Run:

```bash
uv run ruff check .
uv run ty check .
uv run pytest api/tests
```

Expected: all commands exit 0.

- [ ] **Step 2: Run final frontend verification**

Run:

```bash
cd frontend && /home/shenss/.bun/bin/bun run test:shell
cd frontend && /home/shenss/.bun/bin/bun run test:auth
cd frontend && /home/shenss/.bun/bin/bun run build
```

Expected: all commands exit 0.

- [ ] **Step 3: Run smoke where runtime behavior is affected**

Run:

```bash
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
```

Then check `/api/health` and any frontend page affected by source-contract moves with Playwright screenshots if UI-rendered code changed.

- [ ] **Step 4: Request code review**

Use `requesting-code-review` with the relevant base and head SHAs or current diff if the work remains uncommitted. Fix critical and important findings before completion.

## Self-Review

- Spec coverage: Tasks cover backend test split, frontend test split, `Any` reduction, docs alignment, verification, and requested code review.
- Placeholder scan: no `TBD`, `TODO`, or deferred implementation placeholders are required to execute the plan.
- Type consistency: helper names and commands match the files produced by earlier tasks.
