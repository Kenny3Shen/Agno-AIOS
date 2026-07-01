# Security-First Multi-User RBAC Design

## Goal

Implement a security-first vertical slice for Agno AIOS so Chat sessions, Trace data, and privileged operations are isolated by authenticated user, governed through RBAC, and auditable before broader frontend polish and project cleanup continue.

## Product Context

Agno AIOS is a control plane for security operators and AgentOS runtime work. The current app already requires authentication, but the business data layer still allows shared Session, Chat, and Trace visibility. Some endpoints accept `user_id` from the frontend, which makes ownership spoofing possible. The first implementation milestone must replace that trust boundary with server-derived identity.

The design follows the Agno AgentOS control-plane direction from `docs.agno.com/agent-os/control-plane`: chat, traces, sessions, knowledge, authorization, and user management are treated as operational surfaces in one compact control console. The UI should remove verbose explanatory copy and show actionable state, while backend permissions remain authoritative.

## Scope

In scope for the first milestone:

- Add role data to authenticated users: `admin`, `user`, `guest`.
- Add centralized RBAC policy helpers so route code declares permissions instead of scattering role checks.
- Stop trusting frontend-provided `user_id` for Chat, Session, and Trace ownership.
- Bind Chat runs and Sessions to `current_user.id`.
- Enforce Session ownership for list, read, archive/delete, and any future mutation path.
- Enforce Trace visibility in both list and detail APIs.
- Add audit logs for login, logout, delete/archive, Knowledge, MCP, Skill, and admin operations.
- Update the Vue frontend API layer to send the auth token consistently and stop passing `user_id` as an authority source.
- Fix the Trace filter path as part of the secured Trace API contract.
- Fix clipboard copy failures with a browser-compatible fallback.
- Align Chat, MCP, Skills, and Trace right/content panel tones with the existing control-plane style.
- Remove middle explanatory copy from right/content panels while preserving top-level labels such as `Skills（安全 Skills 模块开关）`.
- Add the first Chat experience upgrades that are safe to implement within this slice: auto-scroll, streaming indicator, loading skeleton, code block copy, Mermaid rendering, image zoom, source collapse, thinking collapse, and tool-call timeline rendering.
- Update documentation and local agent instructions affected by the security workflow.

Out of scope for the first milestone:

- Full project dead-code cleanup.
- Full i18n migration.
- Broad dependency upgrades.
- Replacing the whole frontend state model.
- Custom role editor UI.
- Enterprise-style organization/team tenancy.

These out-of-scope items remain part of the larger goal, but they should be planned after the P0 security slice is verified.

## Roles And Permissions

Roles:

- `admin`: can read and mutate all supported resources, including all Sessions, Conversations, Traces, Knowledge, MCP, Skills, Settings, and Audit Logs.
- `user`: can read and mutate only resources owned by their user id. For shared configuration surfaces, mutations are denied unless a specific policy grants them.
- `guest`: can read only resources they own. Mutations are denied.

The existing `is_superuser` flag remains compatible: a superuser is treated as `admin` even if `role` is missing or different. New users default to `user` unless configuration or tests explicitly create a `guest`.

Permission names are resource/action based:

- `session:read:any`, `session:read:own`, `session:write:any`, `session:write:own`
- `trace:read:any`, `trace:read:own`
- `knowledge:read`, `knowledge:write`
- `mcp:read`, `mcp:write`
- `skill:read`, `skill:write`
- `settings:read`, `settings:write`
- `audit:read`
- `admin:operate`

Routes consume a helper such as `require_permission("session:read:own")` or a resource guard such as `ensure_session_access(session_id, actor, action="read")`. The implementation should keep the policy table in one file, not repeat `if role == "admin"` across routers.

## Data Ownership

Canonical user id:

- Use `str(current_user.id)` as the only authoritative owner id.
- Frontend `currentUserId`, request body `user_id`, and query `user_id` are not trusted for authorization.
- Where Agno tables already have `user_id`, normalize reads and writes to the canonical id.

Session ownership:

- New Chat messages call Agno with `user_id=str(current_user.id)`.
- Listing sessions filters by `user_id=current_user.id` for `user` and `guest`.
- Admin session listing may omit the owner filter.
- Reading or archiving a session first verifies the session exists and belongs to the actor unless the actor has `session:*:any`.
- Missing or owner-mismatched sessions return `404` to avoid confirming guessed session ids.

Trace ownership:

- Trace list always derives the effective `user_id` from the actor.
- Admin may pass `user_id` or omit it to see all traces.
- Non-admin users cannot override `user_id`; any supplied `user_id` is ignored or rejected consistently by the route.
- Trace detail verifies the trace owner before returning spans.
- Missing or owner-mismatched traces return `404` to reduce enumeration.

Chat history:

- Chat history is read from owned Agno session rows only.
- Archived sessions remain in Agno tables but are hidden from normal list queries.
- Archive metadata records actor id and timestamp.

## Audit Log

Create an app-owned audit table, for example `app.audit_logs`:

- `id BIGSERIAL PRIMARY KEY`
- `actor_user_id TEXT NOT NULL`
- `actor_email TEXT NOT NULL DEFAULT ''`
- `actor_role TEXT NOT NULL`
- `action TEXT NOT NULL`
- `resource_type TEXT NOT NULL`
- `resource_id TEXT NOT NULL DEFAULT ''`
- `status TEXT NOT NULL DEFAULT 'success'`
- `ip_address TEXT NOT NULL DEFAULT ''`
- `user_agent TEXT NOT NULL DEFAULT ''`
- `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Audit actions:

- `auth.login`
- `auth.logout`
- `session.archive`
- `knowledge.create`
- `knowledge.delete`
- `knowledge.clear`
- `mcp.config_update`
- `mcp.token_issue`
- `mcp.token_delete`
- `mcp.hiagent_add`
- `mcp.hiagent_update`
- `mcp.hiagent_delete`
- `skill.toggle`
- `settings.update`
- `admin.operation`

Login audit uses `UserManager.on_after_login` with the request data supplied by `fastapi-users`. Logout audit uses a new authenticated wrapper endpoint consumed by the frontend, while the generated `/api/auth/jwt/logout` route remains available for compatibility.

## Backend Architecture

Modify `api/auth/models.py`:

- Add a SQLAlchemy mapped `role` column with default `"user"`.

Modify `api/auth/schemas.py`:

- Expose `role` in `UserRead`.
- Allow safe role updates only for admin paths; normal self-update must not let users promote themselves.

Create `api/auth/permissions.py`:

- Define `Role`, permission constants, role policy mapping, `actor_role(user)`, `has_permission(user, permission)`, and FastAPI dependency helpers.
- Define ownership helpers that return `404` for inaccessible Session/Trace resources.

Create `api/services/audit_service.py`:

- Ensure the audit table exists.
- Provide `record_audit_event(...)`.
- Keep audit failures non-fatal for user workflows but log them.

Modify `api/services/postgres_store.py`:

- Add table creation support for audit logs and any indexes needed for owner filtering.

Modify `api/routes/chat.py` and `api/services/llm_service.py`:

- Depend on `current_active_user` for every Chat and Session endpoint.
- Remove request-authoritative `user_id`.
- Pass canonical owner id into `stream_chat_with_agent`.
- Add owner filtering to `get_all_sessions`.
- Add owner check to `get_session_messages` and `archive_session`.
- Audit archive/delete actions.

Modify `api/routes/trace.py` and `api/services/tracing_service.py`:

- Depend on `current_active_user`.
- Compute effective trace filters from RBAC.
- Keep `session_id`, `run_id`, `agent_id`, `status`, and time-range filters working after owner filtering.
- Add a detail access check before returning spans.

Modify `api/routes/knowledge.py`, `api/routes/mcp.py`, `api/routes/skills.py`, and `api/routes/settings.py`:

- Add read/write permissions appropriate to each endpoint.
- Record audit events for mutation endpoints.
- Return `403` for authenticated users lacking permission.

Modify `api/auth/users.py`:

- Preserve current JWT auth behavior.
- Record login audits from `UserManager.on_after_login`.

Modify `api/auth/router.py`:

- Add an authenticated logout wrapper that records `auth.logout` and then returns a successful logout response for the frontend client.

## Frontend Architecture

Create or extend an authenticated fetch helper:

- Read the stored JWT token from `authClient`.
- Attach `Authorization: Bearer <token>` to all `/api` requests.
- Centralize JSON error handling.
- Clear auth state or surface a session-expired message on `401`.

Modify `frontend/src/composables/useApi.ts`:

- Replace raw `fetch` calls with the authenticated helper.
- Remove `userId` from `sendMessageStream` and `archiveSession`.
- Keep Trace query parameter construction explicit and complete.

Modify `frontend/src/types/index.ts`:

- Add `role` to `AuthUser`.
- Add Chat message metadata fields for tool calls, thinking blocks, sources, and images when the backend or renderer can infer them.

Modify `frontend/src/App.vue`:

- Use user role to hide unsupported navigation actions, while relying on backend enforcement as authoritative.
- Remove middle explanatory text from panel headers and page metadata.
- Align Chat, MCP, Skills, and Trace content panel tone with the rest of the control plane.

Modify `frontend/src/components/Trace.vue`:

- Preserve `session_id`, `status`, `timeRange`, `run_id`, `agent_id`, and pagination filters.
- Display permission errors and empty filtered results clearly.
- Use the shared clipboard fallback.

Modify `frontend/src/components/Chat.vue`:

- Auto-scroll on outgoing messages, incoming chunks, session changes, and loading state changes.
- Show a streaming cursor or subtle token animation while assistant content is incomplete.
- Show a Markdown loading skeleton for empty assistant messages during stream startup.
- Add copy buttons to rendered code blocks.
- Render Mermaid fenced blocks as diagrams with safe fallback text.
- Support click-to-zoom for rendered images.
- Collapse source citations when the response contains source blocks.
- Collapse thinking sections by default when the response contains thinking markers.
- Render tool calls as a compact timeline when tool-call metadata or recognizable tool-call text is available.

Create `frontend/src/lib/clipboard.ts`:

- Use `navigator.clipboard.writeText` when available and permitted.
- Fall back to a temporary textarea plus `document.execCommand("copy")`.
- Return success/failure so callers can show accurate messages.

## Data Flow

Chat request:

1. Vue sends message, session id, and model id with JWT auth.
2. FastAPI resolves `current_active_user`.
3. Permission layer allows `session:write:own` unless role is `guest`.
4. Backend passes `user_id=str(current_user.id)` to Agno.
5. Agno writes session/run rows with the canonical user id.
6. Session sidebar reloads through an owned-session query.

Trace query:

1. Vue sends filter parameters.
2. FastAPI resolves actor and role.
3. Admin receives requested filters.
4. Non-admin receives filters plus forced `user_id=current_user.id`.
5. Trace list returns only accessible rows.
6. Trace detail verifies owner before spans are returned.

Mutation audit:

1. Route verifies permission.
2. Route performs mutation.
3. Route records an audit event with actor, action, resource, status, and request metadata.
4. Audit write failure is logged but does not roll back the primary operation unless the mutation itself fails.

## Error Handling

- `401`: unauthenticated or expired token.
- `403`: authenticated but role lacks the requested permission.
- `404`: resource missing or not owned when revealing existence would help guessing.
- `400`: invalid filter, malformed request, or invalid role value.
- Audit write failures should log server-side warnings and not expose internals to the frontend.
- Clipboard fallback should show a concise failure only after both primary and fallback paths fail.

## Testing

Backend tests:

- Role policy unit tests for admin/user/guest permissions.
- Chat session list filters by current user.
- Session detail and archive return `404` for another user's session.
- Guest cannot archive or send Chat messages if write permission is denied.
- Trace list forces non-admin owner filter.
- Trace detail returns `404` for another user's trace.
- Admin can list and inspect all traces/sessions.
- Mutation endpoints produce audit records.

Frontend tests:

- Authenticated API helper attaches JWT.
- Chat API no longer sends `user_id`.
- Archive API no longer appends `user_id`.
- Trace API preserves filter query parameters.
- Clipboard helper succeeds through fallback when `navigator.clipboard` fails.
- Source-level or component tests confirm right/content panel copy is removed.
- Chat renderer exposes code copy, Mermaid, image zoom, collapsible sources, collapsible thinking, and tool timeline hooks.

Verification commands:

- `uv run ruff check .`
- `uv run ty check .`
- `cd frontend && npm run test:shell`
- `cd frontend && npm run build`
- Playwright validation after starting the app:
  - Login flow still works.
  - Trace filters include `session_id` and return scoped data.
  - Copy buttons succeed without browser clipboard permission.
  - Chat streams and scrolls to the newest message.
  - Light mode Skills panel has a visible border.

## Acceptance Criteria

- No frontend-provided `user_id` can grant data access.
- Session list, detail, archive, and Chat history are isolated by current user unless actor is admin.
- Trace list and detail are isolated by current user unless actor is admin.
- Guest users have read-only access to their own allowed data.
- Route code uses centralized RBAC helpers rather than repeated ad hoc admin checks.
- Audit logs are persisted for the required action categories.
- Trace filtering by `session_id` and other exposed filters works after security filtering.
- Copy buttons no longer fail solely because `navigator.clipboard` is unavailable or blocked.
- Chat, MCP, Skills, and Trace panels use the same restrained control-plane tone.
- Skills light mode content area has a visible border.
- Middle explanatory panel copy is removed; only top-level labels remain.
- Chat includes the requested interaction upgrades.
- Documentation explains the security model, roles, audit logging, and remaining P1 work.

## Risks And Mitigations

- Agno table schema may differ by installed version. Mitigation: inspect generated tables at runtime, use existing `PostgresDb` helpers where possible, and keep direct SQL focused on known columns already used by this app.
- Existing sessions may have missing or anonymous `user_id`. Mitigation: admin can see legacy data; normal users see only rows matching their id. A later migration can claim legacy sessions explicitly.
- `fastapi-users` generated user routes may allow role changes if schemas are too broad. Mitigation: keep `UserUpdate` free of role fields for self-service paths and reserve role changes for a later admin-only role-management endpoint.
- Mermaid rendering can add bundle and runtime complexity. Mitigation: lazy-load Mermaid and degrade fenced `mermaid` blocks to code if rendering fails.
- Audit logging during auth callbacks may not have full request metadata. Mitigation: record what is available in callbacks and use middleware or wrapper routes if richer context is required.

## Milestone Plan

Milestone 1, P0 backend security:

- User roles, permission helpers, Session ownership, Trace ownership, audit table, mutation audits.

Milestone 2, P0 frontend security compatibility:

- Authenticated fetch helper, removal of frontend `user_id` authority, Trace filter fix, copy fallback.

Milestone 3, P0/P1 interface alignment:

- Right/content panel tone, text removal, Skills light border, first Chat experience upgrades.

Milestone 4, P1 cleanup:

- i18n, state-management consolidation, dead-code cleanup, dependency upgrades, docs expansion.
