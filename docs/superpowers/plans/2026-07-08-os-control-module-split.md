# OS Control Module Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split OS control into functional backend route/service modules and frontend composables without keeping the old aggregate compatibility layer.

**Architecture:** Backend route modules own permission dependencies and call focused service modules. Shared payload formatting is isolated in a helper module. Frontend components import memory, approvals, scheduler, and generic control composables directly.

**Tech Stack:** FastAPI, Agno AsyncPostgresDb, SQLAlchemy async, Vue 3 Composition API, TypeScript, Bun source-contract tests, pytest.

## Global Constraints

- Do not preserve `api.services.os_control_service` or `useOsControlApi()` as compatibility aggregators.
- Keep permission dependencies at route boundaries.
- Keep memory mutation audit events and user scoping.
- Keep scheduler calls on direct AgentOS `/schedules` APIs.
- Do not add empty modules; every module must own real route or service logic.

---

### Task 1: Backend Red Tests

**Files:**
- Modify: `api/tests/test_os_control_permissions.py`
- Modify: `api/tests/test_approval_control_service.py`
- Modify: `api/tests/test_postgres_sql_templates.py`
- Modify: `api/tests/test_rbac_permissions.py`

**Interfaces:**
- Produces: failing tests for removed aggregate service and new route/service module imports.

- [x] **Step 1: Rewrite tests to import functional route and service modules**

Use imports such as `api.routes.os_memory_control`, `api.routes.os_approvals_control`, `api.services.os_memory_control`, `api.services.os_sessions_control`, and `api.services.os_metrics_control`.

- [x] **Step 2: Add aggregate removal assertion**

Assert `importlib.util.find_spec("api.services.os_control_service") is None`.

- [x] **Step 3: Run focused tests and confirm failure**

Run: `uv run pytest api/tests/test_os_control_permissions.py api/tests/test_approval_control_service.py api/tests/test_postgres_sql_templates.py api/tests/test_rbac_permissions.py -q`

Expected: FAIL because the new modules do not exist and the old aggregate service still exists.

### Task 2: Backend Module Split

**Files:**
- Create: `api/services/os_control_payloads.py`
- Create: `api/services/os_control_identity.py`
- Create: `api/services/os_memory_control.py`
- Create: `api/services/os_sessions_control.py`
- Create: `api/services/os_metrics_control.py`
- Create: `api/services/os_evaluation_control.py`
- Create: `api/services/os_knowledge_control.py`
- Create: `api/routes/os_sessions_control.py`
- Create: `api/routes/os_memory_control.py`
- Create: `api/routes/os_metrics_control.py`
- Create: `api/routes/os_evaluation_control.py`
- Create: `api/routes/os_knowledge_control.py`
- Create: `api/routes/os_approvals_control.py`
- Modify: `api/main.py`
- Delete: `api/routes/os_control.py`
- Delete: `api/services/os_control_service.py`

**Interfaces:**
- Produces: route modules with explicit permission dependencies and focused service functions.

- [ ] **Step 1: Move payload helpers**

Move `OsMetric`, `OsRecord`, `OsPayload`, `_now`, `_iso`, `_compact`, `_metric`, `_record`, `_payload`, and `_row_dict`.

- [ ] **Step 2: Move identity helpers**

Move `_owner_user_id()` and `_scoped_requested_user_id()`.

- [ ] **Step 3: Move memory service**

Move memory payload, update, delete, exceptions, and memory-specific normalization.

- [ ] **Step 4: Move sessions, metrics, evaluation, and knowledge services**

Move each payload function into its focused module.

- [ ] **Step 5: Split route modules and update `api/main.py`**

Include all new route routers directly from `api/main.py`.

- [ ] **Step 6: Delete aggregate backend modules**

Remove `api/routes/os_control.py` and `api/services/os_control_service.py`.

### Task 3: Frontend Red Tests

**Files:**
- Modify: `frontend/src/modules/apiComposablesSourceContracts.test.mjs`
- Modify: `frontend/src/modules/testSource.mjs`
- Modify: frontend source-contract tests that reference `useControlPlaneApiSource`

**Interfaces:**
- Produces: source-contract expectations for direct functional composables.

- [ ] **Step 1: Assert old aggregate is gone**

Assert `useOsControlApi` is not exported by `useApi.ts` and does not appear in components.

- [ ] **Step 2: Assert new composables exist**

Assert memory, approvals, scheduler, and control payload composables own their endpoints.

### Task 4: Frontend Functional Split

**Files:**
- Create: `frontend/src/composables/useMemoryControlApi.ts`
- Create: `frontend/src/composables/useApprovalsApi.ts`
- Create: `frontend/src/composables/useSchedulerApi.ts`
- Modify: `frontend/src/composables/useControlPlaneApi.ts`
- Modify: `frontend/src/composables/useApi.ts`
- Modify: `frontend/src/components/MemoryControl.vue`
- Modify: `frontend/src/components/AgentOSControl.vue`
- Modify: `frontend/src/types/index.ts`

**Interfaces:**
- Produces: direct composable imports with no `useOsControlApi()`.

- [ ] **Step 1: Move memory calls**

Move `fetchMemory`, `deleteMemory`, and `updateMemory` to `useMemoryControlApi()`.

- [ ] **Step 2: Move approvals calls**

Move approval list/detail/resolve calls to `useApprovalsApi()`.

- [ ] **Step 3: Move scheduler calls**

Move direct AgentOS schedule calls to `useSchedulerApi()`.

- [ ] **Step 4: Keep generic control payload calls**

Keep `useControlPlaneApi()` for sessions, metrics, evaluation, and knowledge payload reads.

- [ ] **Step 5: Update component imports**

Components import only the functional composables they use.

### Task 5: Verification And Commit

**Files:**
- All files above.

**Interfaces:**
- Produces: verified and committed refactor.

- [ ] **Step 1: Backend focused tests**

Run: `uv run pytest api/tests/test_os_control_permissions.py api/tests/test_approval_control_service.py api/tests/test_postgres_sql_templates.py api/tests/test_rbac_permissions.py -q`

- [ ] **Step 2: Frontend tests and build**

Run:

```bash
cd frontend
/home/shenss/.bun/bin/bun run test:shell
/home/shenss/.bun/bin/bun run test:auth
/home/shenss/.bun/bin/bun run build
```

- [ ] **Step 3: Static checks**

Run:

```bash
uv run ruff check api/routes api/services api/tests
uv run ty check api/routes api/services api/tests
git diff --check
```

- [ ] **Step 4: Commit**

Commit message: `refactor: split os control modules`
