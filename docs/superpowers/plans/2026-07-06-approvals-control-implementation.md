# Approvals Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first AgentOS approvals control slice over Agno-native `AsyncPostgresDb` approvals.

**Architecture:** Add a focused backend approval adapter that normalizes Agno approval dictionaries and resolves pending approvals with `expected_status="pending"`. Expose explicit `/api/os/approvals` sub-routes, then teach the existing AgentOS control frontend to list, inspect, approve, and reject Agno approval records.

**Tech Stack:** FastAPI, Pydantic, Agno `AsyncPostgresDb`, pytest/pytest-asyncio, Vue 3, Element Plus, TypeScript, existing shell tests.

## Global Constraints

- Agno runtime approvals must use Agno `AsyncPostgresDb` public methods.
- Do not create or depend on an AIOS-owned `os_approvals` runtime table.
- Do not directly query Agno approval tables from route handlers.
- Do not implement automatic paused-run continuation in this slice.
- Do not fold scheduler or MCP control-plane actions into this approval model.
- Use TDD: write failing tests, watch them fail, then implement.

---

### Task 1: Backend Approval Service And Routes

**Files:**
- Create: `api/services/approval_control_service.py`
- Modify: `api/routes/os_control.py`
- Modify: `api/services/os_control_service.py`
- Test: `api/tests/test_approval_control_service.py`

**Interfaces:**
- Produces: `ApprovalListParams`, `ApprovalResolveRequest`, `list_approvals_payload(params, actor)`, `get_approval_record(approval_id)`, `resolve_approval_record(approval_id, status, resolved_by, resolution_data)`.
- Consumes: `get_async_agno_postgres_db()`, Agno DB methods `get_approvals`, `get_approval`, `get_pending_approval_count`, `update_approval`.

- [x] **Step 1: Write backend RED tests**

Add tests for listing, dashboard projection, single lookup, resolving with `expected_status="pending"`, not found, double resolve, and actor-derived resolver.

Run:

```bash
uv run pytest api/tests/test_approval_control_service.py -q
```

Expected: fail with `ModuleNotFoundError` or missing approval service symbols.

- [x] **Step 2: Implement backend service**

Create `api/services/approval_control_service.py` with:

```python
class ApprovalResolveConflictError(Exception): ...

@dataclass(frozen=True)
class ApprovalListParams:
    status: str | None = None
    source_type: str | None = None
    approval_type: str | None = None
    pause_type: str | None = None
    agent_id: str | None = None
    team_id: str | None = None
    workflow_id: str | None = None
    user_id: str | None = None
    schedule_id: str | None = None
    run_id: str | None = None
    limit: int = 50
    page: int = 1
```

and async functions that call only Agno DB public methods.

- [x] **Step 3: Wire backend routes**

Add Pydantic request models and routes:

```python
@router.get("/approvals")
async def list_os_approvals(...): ...

@router.get("/approvals/{approval_id}")
async def get_os_approval(...): ...

@router.post("/approvals/{approval_id}/resolve")
async def resolve_os_approval(...): ...
```

Resolve route accepts only `approved` or `rejected`, derives `resolved_by` from the authenticated user, maps not found to 404, stale pending status to 409, and records a policy event.

- [x] **Step 4: Replace dashboard placeholder**

Update `get_approvals_payload()` to delegate to the new approval service, and remove any hot-path `os_approvals` dependency for runtime approvals.

- [x] **Step 5: Verify backend task**

Run:

```bash
uv run pytest api/tests/test_approval_control_service.py api/tests/test_os_control_permissions.py -q
```

Expected: all selected tests pass.

### Task 2: Frontend Approvals Types, API, And UI

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/composables/useApi.ts`
- Modify: `frontend/src/components/AgentOSControl.vue`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`
- Test: `frontend/src/uiShell.test.mjs`

**Interfaces:**
- Consumes: backend fields `approvals`, `approval_filters`, `approval_meta`, and resolve endpoint.
- Produces: `ApprovalRecord`, `ApprovalListParams`, `ApprovalResolveRequest`, `listApprovals`, `getApproval`, `resolveApproval`.

- [x] **Step 1: Write frontend RED tests**

Extend `uiShell.test.mjs` to assert the UI has approval action bindings and the API composable exposes approval methods.

Run:

```bash
cd frontend && bun run test:shell
```

Expected: fail because methods and UI action labels are missing.

- [x] **Step 2: Add frontend types and API methods**

Extend `frontend/src/types/index.ts` with approval record, filters, pagination, list params, and resolve request interfaces. Extend `useOsControlApi()` with:

```typescript
const listApprovals = async (params: ApprovalListParams = {}): Promise<ApprovalControlResponse> => { ... }
const getApproval = async (id: string): Promise<ApprovalRecord> => { ... }
const resolveApproval = async (id: string, payload: ApprovalResolveRequest): Promise<ApprovalRecord> => { ... }
```

- [x] **Step 3: Add approvals UI path**

In `AgentOSControl.vue`, render a dedicated approvals section when `props.osModule === "approvals"`. Show filters, list, detail JSON blocks, and approve/reject buttons only for pending records.

- [x] **Step 4: Add i18n copy**

Add concise Chinese and English strings under `agentOS.approvals.*` for filter labels, actions, statuses, empty state, and success/failure messages.

- [x] **Step 5: Verify frontend task**

Run:

```bash
cd frontend && bun run test:shell
```

Expected: shell tests pass.

### Task 3: Full Verification And Commit

**Files:**
- All files changed by Tasks 1 and 2.

**Interfaces:**
- Consumes: complete backend and frontend implementation.
- Produces: committed feature branch changes.

- [x] **Step 1: Run backend checks**

```bash
uv run ruff check .
uv run ty check .
uv run pytest api/tests
```

Expected: ruff and ty exit 0; pytest reports all backend tests passed.

- [x] **Step 2: Run frontend checks**

```bash
cd frontend && bun run test:shell
cd frontend && bun run test:auth
cd frontend && bun run build
```

Expected: all commands exit 0.

- [x] **Step 3: Run preprod smoke**

```bash
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
```

Expected: application startup completes; stop the server after confirming startup.

- [x] **Step 4: Review and commit**

```bash
git diff --check
git status --short
git add api/services/approval_control_service.py api/routes/os_control.py api/services/os_control_service.py api/tests/test_approval_control_service.py frontend/src/types/index.ts frontend/src/composables/useApi.ts frontend/src/components/AgentOSControl.vue frontend/src/i18n/locales/zh-CN.ts frontend/src/i18n/locales/en-US.ts frontend/src/uiShell.test.mjs docs/superpowers/plans/2026-07-06-approvals-control-implementation.md
git commit -m "feat: add agno approvals control"
```

Expected: commit includes only approvals control implementation, tests, and the plan file.
