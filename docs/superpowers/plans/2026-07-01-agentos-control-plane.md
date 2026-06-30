# AgentOS Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Agno OS aligned navigation and missing AgentOS-style control-plane modules to Agno AIOS.

**Architecture:** Backend adds one focused `os_control_service` and one router for lightweight AgentOS-style data. Frontend adds one shared `AgentOSControl.vue` panel and routes the missing nav entries to it. Trace scrolling is fixed at the container height chain rather than by adding page-level hacks.

**Tech Stack:** FastAPI, Agno `PostgresDb`, FastMCP, Vue 3, TypeScript, Element Plus, Node test runner, uv, ruff, ty, playwright-cli.

---

### Task 1: Navigation Contract Test

**Files:**
- Modify: `frontend/src/uiShell.test.mjs`

- [ ] **Step 1: Add failing nav order assertions**

Add assertions that `App.vue` contains `dashboardItem`, `primaryNavItems`, and all missing AgentOS page labels. Assert `navItems` places `chat`, `skills`, `mcp`, `knowledge`, and `trace` in that order.

- [ ] **Step 2: Run the test and verify red**

Run: `cd frontend && npm run test:shell`

Expected: failure mentioning `dashboardItem` or missing AgentOS page labels.

### Task 2: Backend Control Service

**Files:**
- Create: `api/services/os_control_service.py`
- Create: `api/routes/os_control.py`
- Modify: `api/main.py`

- [ ] **Step 1: Implement service functions**

Create functions `get_sessions_payload`, `get_studio_payload`, `get_memory_payload`, `get_metrics_payload`, `get_evaluation_payload`, `get_approvals_payload`, and `get_scheduler_payload`. Use existing Agno PostgreSQL tables when present and return explicit empty scaffolding when registry tables are empty.

- [ ] **Step 2: Implement router**

Expose GET routes under `/api/os/*` for each payload.

- [ ] **Step 3: Register router**

Include the router in `api/main.py` before static file mounting.

### Task 3: Chat User Isolation

**Files:**
- Modify: `api/routes/chat.py`
- Modify: `api/services/llm_service.py`

- [ ] **Step 1: Add `user_id` to chat request**

Extend `ChatRequest` with `user_id: str | None = None`.

- [ ] **Step 2: Pass user_id through streaming**

Update `_event_generator` and `stream_chat_with_agent` to accept `user_id`.

- [ ] **Step 3: Pass user_id to Agno**

Call `security_agent.arun(message, user_id=user_id or "anonymous", session_id=session_id, stream=True)`.

### Task 4: FastMCP Runtime Hardening

**Files:**
- Modify: `api/mcp/server.py`

- [ ] **Step 1: Add optional middleware imports**

Import FastMCP middleware classes inside a helper so older installed versions do not break startup.

- [ ] **Step 2: Attach middleware to parent server**

Add error handling, rate limiting, timing, and response limiting middleware when available.

- [ ] **Step 3: Preserve token wrapper**

Keep `AuthenticatedMcpApp` unchanged so Bearer and query-token clients still work.

### Task 5: Frontend Control API Types

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/composables/useApi.ts`

- [ ] **Step 1: Add shared types**

Add `OsControlModule`, `OsControlMetric`, `OsControlRecord`, and `OsControlResponse`.

- [ ] **Step 2: Add API composable**

Add `useOsControlApi()` with `fetchModule(module: OsControlModule)`.

### Task 6: Shared AgentOS Control Page

**Files:**
- Create: `frontend/src/components/AgentOSControl.vue`

- [ ] **Step 1: Render summary metrics**

Use the shared response `metrics` array to render compact cards.

- [ ] **Step 2: Render records**

Render records as a stable table-like list with monospaced IDs and status chips.

- [ ] **Step 3: Render empty and error states**

Show a clear empty state when the backend returns no records.

### Task 7: Navigation Implementation

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Import icons and control component**

Import icons for Sessions, Studio, Memory, Metrics, Evaluation, Approvals, and Scheduler.

- [ ] **Step 2: Extend module types and component map**

Add new module ids and map them to `AgentOSControl`.

- [ ] **Step 3: Put Dashboard under Home**

Render `dashboardItem` directly after Home and before the divider.

- [ ] **Step 4: Reorder middle nav**

Set primary nav order to Chat, Skills, MCP, Knowledge, Trace, Sessions, Studio, Memory, Metrics, Evaluation, Approvals, Scheduler, CVE, Assets, Collect.

### Task 8: Trace Waterfall Scroll Fix

**Files:**
- Modify: `frontend/src/components/Trace.vue`

- [ ] **Step 1: Fix height chain**

Set `.trace-detail-main` to `min-height: 0`, `.trace-panel-scroll` to a block scroll container, and `.trace-waterfall-list` to allow independent horizontal overflow when needed.

- [ ] **Step 2: Preserve mobile layout**

Keep mobile breakpoints using visible overflow only after the whole trace console becomes page-scrollable.

### Task 8.1: Chat Session Soft Archive

**Files:**
- Modify: `api/services/llm_service.py`
- Modify: `api/routes/chat.py`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/composables/useApi.ts`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add backend contract test**

Run: `uv run python -m unittest api.tests.test_chat_session_archive`

Expected before implementation: failure because `archive_session` does not exist and the route still calls hard delete.

- [ ] **Step 2: Implement archive overlay**

Create `app.chat_session_archives`, mark `agno_sessions.metadata.agno_aios_archived=true`, and hide archived sessions from `GET /api/chat/sessions` by default.

- [ ] **Step 3: Add sidebar archive affordance**

Add a small archive/delete icon button to each Chat session row. The action calls `DELETE /api/chat/sessions/{session_id}` but treats it as archive, not hard delete.

### Task 8.2: Trace Queue Navigation And Dashboard Metrics

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/components/Trace.vue`
- Modify: `frontend/src/components/Dashboard.vue`
- Modify: `frontend/src/style.css`
- Modify: `frontend/src/uiShell.test.mjs`

- [ ] **Step 1: Move Trace Queue into left navigation**

Render a `Trace Queue` panel under the `Trace` nav item, matching the Chat session expandable pattern.

- [ ] **Step 2: Remove Trace page summary metrics**

Delete the Trace page summary card grid and keep the page focused on selected Trace detail, Span Waterfall, Span Tree, and diagnostics.

- [ ] **Step 3: Add Dashboard chart surfaces**

Add native SVG/CSS charts for latency trend, hourly heatmap, Agent load radar, and Span/Error distribution.

### Task 9: Documentation Updates

**Files:**
- Modify: `README.md`
- Modify: `docs/agent-os-control-plane.md`

- [ ] **Step 1: Update README capabilities**

Document AgentOS-style Sessions, Studio, Memory, Metrics, Evaluation, Approvals, and Scheduler.

- [ ] **Step 2: Document remaining limitations**

Call out that approvals, schedules, and evaluations are registry scaffolds until execution backends are connected.

### Task 10: Verification

**Files:**
- No code edits.

- [ ] **Step 1: Run frontend shell test**

Run: `cd frontend && npm run test:shell`

- [ ] **Step 2: Run frontend build**

Run: `cd frontend && npm run build`

- [ ] **Step 3: Run Python checks**

Run: `uv run ruff check .`

Run: `uv run ty check .`

- [ ] **Step 4: Run Playwright validation**

Start backend or frontend dev server as needed, then use `playwright-cli` to confirm navigation order and Trace scroll behavior.
