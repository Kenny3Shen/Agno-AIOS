# Security-First Multi-User RBAC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved security-first slice: multi-user isolation, RBAC, Session/Trace authorization, audit logging, authenticated frontend API calls, Trace filter/copy fixes, and the first Chat/control-plane UI improvements.

**Architecture:** Backend identity is derived only from `current_active_user`; frontend `user_id` is never authoritative. RBAC is centralized in `api/auth/permissions.py`, audit writes live in `api/services/audit_service.py`, and resource services receive an explicit actor/effective owner filter. Frontend routes all API calls through an authenticated helper, shares clipboard fallback logic, and keeps UI visibility secondary to backend enforcement.

**Tech Stack:** FastAPI, fastapi-users, SQLAlchemy, psycopg, Agno PostgresDb, Vue 3, TypeScript, Element Plus, markdown-it, highlight.js, Mermaid lazy import, uv, ruff, ty, Node tests, Playwright.

## Global Constraints

- Use WSL2 Ubuntu 24.04 conventions.
- Python tooling is `uv + ruff + ty`.
- Run `uv run ruff check .` after Python changes.
- Run `uv run ty check .` after Python changes.
- Use Playwright CLI after frontend/backend changes and fix observed errors.
- Keep `frontend` Vue/Vite as the active frontend; do not migrate to `frontend-react`.
- No frontend-provided `user_id` can authorize access.
- Non-admin inaccessible Session/Trace resources return `404`.
- Route code must use central RBAC helpers instead of scattered role checks.
- Do not broaden P1 cleanup into this P0 slice beyond docs updates needed for the security model.

---

## File Structure

Create:

- `api/auth/permissions.py`: role constants, permission policy, dependency helpers, resource ownership helpers.
- `api/services/audit_service.py`: audit table creation and best-effort event recording.
- `api/tests/test_rbac_permissions.py`: policy tests for admin/user/guest.
- `api/tests/test_chat_session_permissions.py`: Session ownership and guest write denial tests using monkeypatched service boundaries.
- `api/tests/test_trace_permissions.py`: Trace ownership filter/detail tests using monkeypatched tracing service boundaries.
- `frontend/src/lib/apiClient.ts`: authenticated fetch helper.
- `frontend/src/lib/clipboard.ts`: clipboard primary and fallback implementation.
- `frontend/src/lib/clipboard.test.mjs`: clipboard fallback tests.

Modify:

- `api/auth/models.py`: add `role` column.
- `api/auth/schemas.py`: expose `role` in reads while keeping self-update safe.
- `api/auth/users.py`: record login audit from callback.
- `api/auth/router.py`: add audited logout wrapper endpoint.
- `api/services/postgres_store.py`: create audit table/indexes.
- `api/services/llm_service.py`: owner filtering and ownership checks for sessions.
- `api/services/tracing_service.py`: effective owner filtering and trace detail ownership check support.
- `api/routes/chat.py`: authenticated actor, no request-authoritative `user_id`, session permissions.
- `api/routes/trace.py`: authenticated actor, effective trace filters, detail permissions.
- `api/routes/knowledge.py`: read/write permissions and audits.
- `api/routes/mcp.py`: read/write permissions and audits.
- `api/routes/skills.py`: read/write permissions and audits.
- `api/routes/settings.py`: read/write permissions and audits.
- `frontend/src/composables/useApi.ts`: use `apiClient`, remove user id parameters, preserve Trace filters.
- `frontend/src/lib/authClient.ts`: call audited logout wrapper and expose role-aware user data.
- `frontend/src/types/index.ts`: add user role and chat metadata types.
- `frontend/src/App.vue`: remove panel explanatory copy, hide role-inaccessible actions, update logout path.
- `frontend/src/components/Trace.vue`: copy fallback, clearer filter state/errors, no verbose middle copy.
- `frontend/src/components/MCP.vue`: copy fallback, right panel tone/copy cleanup.
- `frontend/src/components/Skills.vue`: light border and control-plane tone.
- `frontend/src/components/Chat.vue`: streaming, skeleton, code copy, Mermaid, image zoom, source/thinking collapse, tool timeline.
- `frontend/package.json`: add Mermaid dependency only if needed by implementation.
- `README.md`: document security model and verification commands.
- `docs/agent-os-control-plane.md`: document RBAC/audit behavior.
- `AGENTS.md`: create if missing; include repository instructions from the user prompt.

---

### Task 1: RBAC And Audit Tests

**Files:**
- Create: `api/tests/test_rbac_permissions.py`
- Create: `api/tests/test_chat_session_permissions.py`
- Create: `api/tests/test_trace_permissions.py`

**Interfaces:**
- Consumes: planned `api.auth.permissions.actor_role`, `has_permission`, `can_access_owned_resource`.
- Produces: failing tests that define the backend security contract.

- [ ] **Step 1: Write RBAC policy tests**

Create `api/tests/test_rbac_permissions.py` with:

```python
from types import SimpleNamespace

from api.auth.permissions import actor_role, has_permission


def user(role: str = "user", is_superuser: bool = False):
    return SimpleNamespace(role=role, is_superuser=is_superuser)


def test_superuser_is_admin():
    assert actor_role(user("guest", is_superuser=True)) == "admin"
    assert has_permission(user("guest", is_superuser=True), "trace:read:any")


def test_admin_can_read_and_write_all_supported_resources():
    actor = user("admin")
    for permission in (
        "session:read:any",
        "session:write:any",
        "trace:read:any",
        "knowledge:write",
        "mcp:write",
        "skill:write",
        "settings:write",
        "audit:read",
    ):
        assert has_permission(actor, permission)


def test_user_is_own_resource_only_and_not_config_writer():
    actor = user("user")
    assert has_permission(actor, "session:read:own")
    assert has_permission(actor, "session:write:own")
    assert has_permission(actor, "trace:read:own")
    assert not has_permission(actor, "session:read:any")
    assert not has_permission(actor, "mcp:write")
    assert not has_permission(actor, "settings:write")


def test_guest_is_read_only_for_owned_resources():
    actor = user("guest")
    assert has_permission(actor, "session:read:own")
    assert has_permission(actor, "trace:read:own")
    assert has_permission(actor, "knowledge:read")
    assert not has_permission(actor, "session:write:own")
    assert not has_permission(actor, "knowledge:write")
```

- [ ] **Step 2: Write Chat/Session ownership tests**

Create tests that monkeypatch route/service boundaries so no real database is needed:

```python
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.auth.permissions import assert_owned_resource


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


def test_owned_resource_allows_owner():
    assert_owned_resource(actor("u1"), owner_user_id="u1", resource_name="Session")


def test_owned_resource_hides_foreign_resource():
    with pytest.raises(HTTPException) as exc:
        assert_owned_resource(actor("u1"), owner_user_id="u2", resource_name="Session")
    assert exc.value.status_code == 404


def test_admin_can_access_foreign_resource():
    admin = SimpleNamespace(id="admin", role="admin", is_superuser=False)
    assert_owned_resource(admin, owner_user_id="u2", resource_name="Session")
```

- [ ] **Step 3: Write Trace effective filter tests**

Create `api/tests/test_trace_permissions.py`:

```python
from types import SimpleNamespace

from api.routes.trace import effective_trace_user_filter


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


def test_user_trace_filter_forces_current_user():
    assert effective_trace_user_filter(actor("u1"), requested_user_id="u2") == "u1"


def test_guest_trace_filter_forces_current_user():
    assert effective_trace_user_filter(actor("g1", "guest"), requested_user_id=None) == "g1"


def test_admin_trace_filter_honors_requested_user_or_all():
    admin = actor("a1", "admin")
    assert effective_trace_user_filter(admin, requested_user_id="u2") == "u2"
    assert effective_trace_user_filter(admin, requested_user_id=None) is None
```

- [ ] **Step 4: Run tests and verify red**

Run:

```bash
uv run pytest api/tests/test_rbac_permissions.py api/tests/test_chat_session_permissions.py api/tests/test_trace_permissions.py -q
```

Expected: tests fail because `api.auth.permissions` and `effective_trace_user_filter` do not exist yet.

---

### Task 2: Auth Model, RBAC Helpers, Audit Service

**Files:**
- Modify: `api/auth/models.py`
- Modify: `api/auth/schemas.py`
- Create: `api/auth/permissions.py`
- Create: `api/services/audit_service.py`
- Modify: `api/services/postgres_store.py`
- Modify: `api/auth/users.py`
- Modify: `api/auth/router.py`

**Interfaces:**
- Produces: `actor_role(user) -> str`, `has_permission(user, permission) -> bool`, `require_permission(permission)`, `assert_owned_resource(actor, owner_user_id, resource_name)`, `record_audit_event(...)`.
- Consumes: `api.auth.users.current_active_user`.

- [ ] **Step 1: Add role to auth model and schemas**

In `api/auth/models.py`, add a mapped role column:

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class User(SQLAlchemyBaseUserTableUUID, AuthBase):
    if TYPE_CHECKING:
        id: UUID

    role: Mapped[str] = mapped_column(String(length=32), nullable=False, default="user", server_default="user")
```

In `api/auth/schemas.py`, add:

```python
class UserRead(schemas.BaseUser[UUID]):
    role: str = "user"


class UserUpdate(schemas.BaseUserUpdate):
    pass
```

- [ ] **Step 2: Implement centralized permissions**

Create `api/auth/permissions.py` with role policy sets and helpers:

```python
from collections.abc import Callable
from typing import Any, Literal

from fastapi import Depends, HTTPException, status

from api.auth.models import User
from api.auth.users import current_active_user

Role = Literal["admin", "user", "guest"]

ROLE_PERMISSIONS: dict[Role, set[str]] = {
    "admin": {"*"},
    "user": {
        "session:read:own",
        "session:write:own",
        "trace:read:own",
        "knowledge:read",
    },
    "guest": {
        "session:read:own",
        "trace:read:own",
        "knowledge:read",
    },
}


def actor_id(user: User | Any) -> str:
    return str(getattr(user, "id", ""))


def actor_role(user: User | Any) -> Role:
    if bool(getattr(user, "is_superuser", False)):
        return "admin"
    role = str(getattr(user, "role", "user") or "user").lower()
    return role if role in {"admin", "user", "guest"} else "user"


def has_permission(user: User | Any, permission: str) -> bool:
    permissions = ROLE_PERMISSIONS[actor_role(user)]
    return "*" in permissions or permission in permissions


def require_permission(permission: str) -> Callable[[User], User]:
    async def dependency(user: User = Depends(current_active_user)) -> User:
        if not has_permission(user, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return user

    return dependency


def assert_owned_resource(actor: User | Any, *, owner_user_id: str | None, resource_name: str) -> None:
    if has_permission(actor, f"{resource_name.lower()}:read:any") or actor_role(actor) == "admin":
        return
    if owner_user_id and str(owner_user_id) == actor_id(actor):
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{resource_name} 不存在")
```

- [ ] **Step 3: Implement audit service**

Create `api/services/audit_service.py` with table creation and best-effort writes:

```python
from typing import Any

from loguru import logger
from psycopg import sql

from api.auth.permissions import actor_id, actor_role
from api.services.postgres_store import app_schema, postgres_connect


def ensure_audit_log_table() -> None:
    with postgres_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(app_schema())))
            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {} (
                        id BIGSERIAL PRIMARY KEY,
                        actor_user_id TEXT NOT NULL,
                        actor_email TEXT NOT NULL DEFAULT '',
                        actor_role TEXT NOT NULL,
                        action TEXT NOT NULL,
                        resource_type TEXT NOT NULL,
                        resource_id TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'success',
                        ip_address TEXT NOT NULL DEFAULT '',
                        user_agent TEXT NOT NULL DEFAULT '',
                        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                ).format(sql.Identifier(app_schema(), "audit_logs"))
            )


def record_audit_event(actor: Any, *, action: str, resource_type: str, resource_id: str = "", status: str = "success", metadata: dict[str, Any] | None = None, ip_address: str = "", user_agent: str = "") -> None:
    try:
        ensure_audit_log_table()
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL(
                        """
                        INSERT INTO {} (
                            actor_user_id, actor_email, actor_role, action, resource_type,
                            resource_id, status, ip_address, user_agent, metadata
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """
                    ).format(sql.Identifier(app_schema(), "audit_logs")),
                    (
                        actor_id(actor),
                        str(getattr(actor, "email", "") or ""),
                        actor_role(actor),
                        action,
                        resource_type,
                        resource_id,
                        status,
                        ip_address,
                        user_agent,
                        metadata or {},
                    ),
                )
    except Exception as exc:
        logger.warning("审计日志写入失败: {}", exc)
```

- [ ] **Step 4: Wire audit table creation**

In `api/services/postgres_store.py`, call `ensure_audit_log_table` indirectly from app table setup without circular import by adding the SQL block directly or exposing a helper. Add indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_time ON app.audit_logs (actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action_time ON app.audit_logs (action, created_at DESC);
```

- [ ] **Step 5: Audit login/logout**

In `api/auth/users.py`, update `on_after_login`:

```python
from api.services.audit_service import record_audit_event

record_audit_event(user, action="auth.login", resource_type="auth", ip_address=request.client.host if request and request.client else "", user_agent=request.headers.get("user-agent", "") if request else "")
```

In `api/auth/router.py`, add:

```python
from fastapi import Depends, Request
from api.auth.users import current_active_user
from api.services.audit_service import record_audit_event


@router.post("/logout")
async def audited_logout(request: Request, user: User = Depends(current_active_user)) -> dict[str, bool]:
    record_audit_event(
        user,
        action="auth.logout",
        resource_type="auth",
        ip_address=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", ""),
    )
    return {"success": True}
```

- [ ] **Step 6: Run RBAC tests green**

Run:

```bash
uv run pytest api/tests/test_rbac_permissions.py -q
```

Expected: pass.

---

### Task 3: Chat And Session Isolation

**Files:**
- Modify: `api/routes/chat.py`
- Modify: `api/services/llm_service.py`
- Modify: `api/services/os_control_service.py`
- Modify: `api/tests/test_chat_session_permissions.py`

**Interfaces:**
- Consumes: `actor_id`, `actor_role`, `has_permission`, `assert_owned_resource`, `record_audit_event`.
- Produces: session APIs scoped to current actor.

- [ ] **Step 1: Remove request-authoritative user id from Chat route**

Change `ChatRequest`:

```python
class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    model_id: str | None = None
```

Add `user: User = Depends(current_active_user)` to `chat_agent`, `list_sessions`, `get_session`, and `remove_session`.

- [ ] **Step 2: Deny guest Chat writes**

In `chat_agent`, before streaming:

```python
if not has_permission(user, "session:write:own"):
    raise HTTPException(status_code=403, detail="访客账号只读")
```

- [ ] **Step 3: Pass canonical actor id into stream**

Call:

```python
_event_generator(request.message, request.session_id, request.model_id, actor_id(user))
```

Keep `_event_generator(..., user_id: str)` internal only.

- [ ] **Step 4: Add owner filters to session service**

Change signatures:

```python
def get_all_sessions(*, include_archived: bool = False, owner_user_id: str | None = None) -> list[dict]:
def get_session_owner(session_id: str) -> str | None:
def get_session_messages(session_id: str, *, actor: Any) -> list[dict]:
def archive_session(session_id: str, *, actor: Any) -> bool:
```

SQL additions:

```sql
AND (%s IS NULL OR s.user_id = %s)
```

Ownership check:

```python
owner = get_session_owner(session_id)
if owner is None:
    return []  # or False for archive
assert_owned_resource(actor, owner_user_id=owner, resource_name="Session")
```

- [ ] **Step 5: Audit archive**

After a successful archive:

```python
record_audit_event(actor, action="session.archive", resource_type="session", resource_id=session_id)
```

- [ ] **Step 6: Update os_control service admin behavior**

Where `get_all_sessions(include_archived=True)` is used, keep the dashboard/admin payload explicit. If the route later becomes user-scoped, pass actor-aware owner filters there too.

- [ ] **Step 7: Run Chat/Session tests**

Run:

```bash
uv run pytest api/tests/test_chat_session_archive.py api/tests/test_chat_session_permissions.py -q
```

Expected: pass after adapting the existing archive test to the new signatures.

---

### Task 4: Trace Authorization And Filter Fix

**Files:**
- Modify: `api/routes/trace.py`
- Modify: `api/services/tracing_service.py`
- Modify: `api/tests/test_trace_permissions.py`

**Interfaces:**
- Produces: `effective_trace_user_filter(actor, requested_user_id)`.
- Consumes: `list_traces(..., user_id=effective_user_id)` and detail owner checks.

- [ ] **Step 1: Add effective filter helper**

In `api/routes/trace.py`:

```python
def effective_trace_user_filter(actor: User, requested_user_id: str | None) -> str | None:
    if has_permission(actor, "trace:read:any"):
        return requested_user_id
    return actor_id(actor)
```

- [ ] **Step 2: Require auth for Trace list**

Add `user: User = Depends(current_active_user)` to `api_list_traces`, compute:

```python
effective_user_id = effective_trace_user_filter(user, user_id)
```

Pass `effective_user_id` to service.

- [ ] **Step 3: Require auth for Trace detail**

Add `user: User = Depends(current_active_user)` to `api_get_trace` and call:

```python
data = await get_trace_detail(trace_id, actor=user)
```

- [ ] **Step 4: Check trace ownership in service**

Change signature:

```python
async def get_trace_detail(trace_id: str, actor: Any | None = None) -> dict[str, Any] | None:
```

After fetching trace:

```python
trace_dict = jsonable_encoder(trace.to_dict())
if actor is not None:
    assert_owned_resource(actor, owner_user_id=str(trace_dict.get("user_id") or ""), resource_name="Trace")
```

- [ ] **Step 5: Preserve filters**

Keep current list filters:

```python
run_id=run_id,
session_id=session_id,
agent_id=agent_id,
team_id=team_id,
workflow_id=workflow_id,
status=status,
start_time=st,
end_time=et,
```

- [ ] **Step 6: Run Trace tests**

Run:

```bash
uv run pytest api/tests/test_trace_permissions.py api/tests/test_tracing_parser.py -q
```

Expected: pass.

---

### Task 5: Protect Knowledge, MCP, Skills, Settings Mutations

**Files:**
- Modify: `api/routes/knowledge.py`
- Modify: `api/routes/mcp.py`
- Modify: `api/routes/skills.py`
- Modify: `api/routes/settings.py`

**Interfaces:**
- Consumes: `require_permission`, `record_audit_event`.
- Produces: backend enforcement for read/write capability surfaces.

- [ ] **Step 1: Add read dependencies to GET/search endpoints**

For knowledge read/search, MCP read, skills read, settings read:

```python
user: User = Depends(require_permission("knowledge:read"))
```

Use resource-specific permissions for each route.

- [ ] **Step 2: Add write dependencies to mutation endpoints**

Examples:

```python
user: User = Depends(require_permission("mcp:write"))
```

Apply to MCP config/tokens/hiagent, skill toggle, settings/model updates, knowledge create/delete/clear.

- [ ] **Step 3: Add audit events after successful mutations**

Examples:

```python
record_audit_event(user, action="mcp.token_issue", resource_type="mcp_token", resource_id=body.name)
record_audit_event(user, action="skill.toggle", resource_type="skill", resource_id=name, metadata={"enabled": enabled})
```

- [ ] **Step 4: Run route import checks**

Run:

```bash
uv run python -m compileall api/routes api/auth api/services
```

Expected: no syntax errors.

---

### Task 6: Frontend Authenticated API Client And Clipboard Fallback

**Files:**
- Create: `frontend/src/lib/apiClient.ts`
- Create: `frontend/src/lib/clipboard.ts`
- Create: `frontend/src/lib/clipboard.test.mjs`
- Modify: `frontend/src/lib/authClient.ts`
- Modify: `frontend/src/composables/useApi.ts`
- Modify: `frontend/src/types/index.ts`

**Interfaces:**
- Produces: `apiFetch(path, init)`, `copyToClipboard(text)`.
- Consumes: `getStoredAuthToken`.

- [ ] **Step 1: Add authenticated API client**

Create `frontend/src/lib/apiClient.ts`:

```ts
import { clearStoredAuthToken, getStoredAuthToken } from './authClient'

export const API_BASE = '/api'

export const apiFetch = async (path: string, init: RequestInit = {}) => {
  const headers = new Headers(init.headers)
  const token = getStoredAuthToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(path.startsWith('/api') ? path : `${API_BASE}${path}`, {
    ...init,
    headers,
  })
  if (response.status === 401) clearStoredAuthToken()
  return response
}
```

- [ ] **Step 2: Replace raw `/api` fetches in `useApi.ts`**

Import `apiFetch` and replace:

```ts
fetch(`${API_BASE}/chat`, ...)
```

with:

```ts
apiFetch('/chat', ...)
```

Remove `userId` from:

```ts
sendMessageStream(message, sessionId, modelId, onChunk)
archiveSession(sessionId)
```

- [ ] **Step 3: Update logout client**

In `authClient.ts`, call:

```ts
authUrl('/auth/logout', options.baseUrl)
```

before clearing storage. Keep the generated JWT logout as fallback if the wrapper fails.

- [ ] **Step 4: Add clipboard helper**

Create `frontend/src/lib/clipboard.ts`:

```ts
export const copyToClipboard = async (text: string): Promise<boolean> => {
  const value = String(text ?? '')
  if (!value) return false
  try {
    if (navigator.clipboard?.writeText && window.isSecureContext) {
      await navigator.clipboard.writeText(value)
      return true
    }
  } catch {
    // fall through
  }
  const textarea = document.createElement('textarea')
  textarea.value = value
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  try {
    return document.execCommand('copy')
  } finally {
    document.body.removeChild(textarea)
  }
}
```

- [ ] **Step 5: Add clipboard tests**

Create a Node test that imports compiled TS only if project test setup supports it; otherwise add source-level assertions to `frontend/src/uiShell.test.mjs` for `execCommand` fallback. Run:

```bash
cd frontend && npm run test:shell
```

Expected: pass.

---

### Task 7: Trace And Copy UI Fixes

**Files:**
- Modify: `frontend/src/components/Trace.vue`
- Modify: `frontend/src/components/MCP.vue`
- Modify: `frontend/src/components/Collect.vue`
- Modify: `frontend/src/composables/useApi.ts`

**Interfaces:**
- Consumes: `copyToClipboard`.
- Produces: reliable copy and complete trace filters.

- [ ] **Step 1: Use clipboard helper in Trace**

Replace:

```ts
await navigator.clipboard.writeText(t)
```

with:

```ts
if (await copyToClipboard(t)) ElMessage.success("已复制")
else ElMessage.warning("复制失败")
```

- [ ] **Step 2: Use clipboard helper in MCP and Collect**

Apply the same helper to MCP token/URL copy and Collect markdown copy.

- [ ] **Step 3: Preserve all Trace filters in API type**

Extend `listTraces` params in `useApi.ts`:

```ts
team_id?: string
workflow_id?: string
user_id?: string
```

Keep query construction:

```ts
if (params.team_id) qs.set('team_id', params.team_id)
if (params.workflow_id) qs.set('workflow_id', params.workflow_id)
if (params.user_id) qs.set('user_id', params.user_id)
```

- [ ] **Step 4: Verify Trace UI source assertions**

Run:

```bash
cd frontend && npm run test:shell
```

Expected: pass.

---

### Task 8: Chat Experience Upgrade

**Files:**
- Modify: `frontend/src/components/Chat.vue`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/package.json` if Mermaid is added.

**Interfaces:**
- Consumes: `copyToClipboard`.
- Produces: auto-scroll, token streaming, skeleton, code copy, Mermaid, image zoom, source/thinking collapse, tool-call timeline.

- [ ] **Step 1: Add render helpers and state**

Add refs:

```ts
const zoomedImage = ref<string | null>(null)
const collapsedSources = reactive(new Set<number>())
const collapsedThinking = reactive(new Set<number>())
```

- [ ] **Step 2: Add streaming skeleton and cursor**

Template behavior:

```vue
<div v-if="msg.role === 'assistant' && !msg.final && !msg.content" class="markdown-skeleton">...</div>
<span v-if="msg.role === 'assistant' && !msg.final" class="stream-cursor" />
```

- [ ] **Step 3: Add code block copy**

After each render/update, decorate code blocks:

```ts
const enhanceRenderedMarkdown = async () => {
  await nextTick()
  document.querySelectorAll('.agent-chat pre code').forEach((code) => {
    const pre = code.parentElement
    if (!pre || pre.querySelector('.code-copy')) return
    const button = document.createElement('button')
    button.className = 'code-copy'
    button.textContent = 'Copy'
    button.addEventListener('click', async () => {
      await copyToClipboard(code.textContent || '')
    })
    pre.appendChild(button)
  })
}
```

Call it after history load and stream chunks.

- [ ] **Step 4: Add Mermaid support**

Use lazy dynamic import:

```ts
const renderMermaidBlocks = async () => {
  const mermaid = await import('mermaid')
  mermaid.default.initialize({ startOnLoad: false, theme: document.documentElement.classList.contains('dark') ? 'dark' : 'default' })
}
```

If dependency is missing, run:

```bash
cd frontend && npm install mermaid
```

- [ ] **Step 5: Add image zoom**

Attach click handlers to rendered markdown images and show a modal/lightbox bound to `zoomedImage`.

- [ ] **Step 6: Add source/thinking/tool timeline parsing**

Implement conservative text parsers:

```ts
const hasThinking = (content: string) => /<think>|思考过程|Thinking/i.test(content)
const hasSources = (content: string) => /(?:来源|Sources?|References?)[:：]/i.test(content)
const toolEvents = (content: string) => content.split('\n').filter(line => /tool|工具调用|MCP/i.test(line))
```

Render these as collapsible sections around the main markdown without deleting original content.

- [ ] **Step 7: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: build passes.

---

### Task 9: Control-Plane Panel Tone And Copy Cleanup

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/components/MCP.vue`
- Modify: `frontend/src/components/Trace.vue`
- Modify: `frontend/src/components/Skills.vue`
- Modify: `frontend/src/components/Chat.vue`
- Modify: `frontend/src/style.css`

**Interfaces:**
- Produces: consistent background, border, radius, padding, and shadow for target pages.

- [ ] **Step 1: Remove middle explanatory copy**

Remove or shorten visible strings:

```text
MCP 工具中枢
基于 FastMCP 的服务控制、访问 Token 与外部 Hi-Agent 接入
TRACE CONSOLE
Agent 观测中心
会话记录、Trace 队列、Span 瀑布与错误上下文统一查看
```

Keep top-level labels from navigation metadata, such as `Skills（安全 Skills 模块开关）`.

- [ ] **Step 2: Add shared panel tokens**

In `style.css`, add reusable classes or variables:

```css
:root {
  --ag-panel-bg: #ffffff;
  --ag-panel-border: #cbd6e2;
  --ag-panel-shadow: 0 14px 34px rgba(15, 23, 42, 0.08);
}

.dark {
  --ag-panel-bg: #0a151b;
  --ag-panel-border: #22313a;
  --ag-panel-shadow: 0 18px 42px rgba(0, 0, 0, 0.28);
}
```

- [ ] **Step 3: Fix Skills light border**

Ensure the Skills content surface has:

```css
border: 1px solid var(--ag-panel-border);
background: var(--ag-panel-bg);
```

- [ ] **Step 4: Run shell tests**

Run:

```bash
cd frontend && npm run test:shell
```

Expected: pass.

---

### Task 10: Documentation And Repository Instructions

**Files:**
- Modify: `README.md`
- Modify: `docs/agent-os-control-plane.md`
- Create or modify: `AGENTS.md`

**Interfaces:**
- Produces: documented roles, audit log, verification workflow, and WSL2/uv/ruff/ty/playwright instructions.

- [ ] **Step 1: Update README security section**

Add:

```markdown
### Security model

Agno AIOS uses authenticated FastAPI users with `admin`, `user`, and `guest` roles. Backend APIs derive ownership from the JWT-authenticated user and do not trust frontend-provided `user_id` values. Sessions and traces are scoped to the current user unless the actor is an admin.
```

- [ ] **Step 2: Update AgentOS control-plane docs**

Document:

```markdown
- Session and Trace APIs enforce backend ownership checks.
- Audit logs are stored in `app.audit_logs`.
- Guest users are read-only.
```

- [ ] **Step 3: Add root AGENTS.md if missing**

Create `AGENTS.md` with the user's project instructions:

```markdown
# AGENTS.md

环境为 WSL2 (Ubuntu24.04)。

Python 开发使用 uv + ruff + ty。

完成任务后运行：

- `uv run ruff check .`
- `uv run ty check .`

前后端修改后使用 playwright-cli 测试并修复错误。
```

---

### Task 11: Verification

**Files:**
- No planned code edits.

**Interfaces:**
- Consumes: all completed tasks.
- Produces: evidence that the slice is complete enough to continue P1 work.

- [ ] **Step 1: Run Python unit tests**

Run:

```bash
uv run pytest api/tests/test_rbac_permissions.py api/tests/test_chat_session_archive.py api/tests/test_chat_session_permissions.py api/tests/test_trace_permissions.py api/tests/test_tracing_parser.py -q
```

- [ ] **Step 2: Run required Python checks**

Run:

```bash
uv run ruff check .
uv run ty check .
```

- [ ] **Step 3: Run frontend tests and build**

Run:

```bash
cd frontend && npm run test:shell
cd frontend && npm run test:auth
cd frontend && npm run build
```

- [ ] **Step 4: Start app for browser validation**

Run backend or frontend dev server depending on the current packaging state:

```bash
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000
```

If port 8000 is occupied, use an available port and note it.

- [ ] **Step 5: Use Playwright CLI**

Validate:

- Login screen renders.
- Authenticated shell renders after mocked or real auth.
- Trace filter form includes `session_id` and request URLs include the filter.
- Copy buttons show success when clipboard permission is unavailable.
- Chat scrolls to the newest streamed message.
- Skills light mode panel has a visible border.

- [ ] **Step 6: Final audit**

Check:

```bash
git status --short
rg -n "user_id" frontend/src api/routes api/services | sed -n '1,220p'
rg -n "navigator.clipboard.writeText" frontend/src
```

Expected:

- Any remaining frontend `user_id` use is display-only, not authorization.
- Raw clipboard calls are replaced by `copyToClipboard` except inside the helper.
- Worktree only contains intended changes.
