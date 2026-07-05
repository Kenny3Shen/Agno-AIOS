# Approvals Control Design

Date: 2026-07-06

## Context

Agno AIOS already exposes an AgentOS control surface and has an `approvals`
module placeholder in the frontend. The next feature slice should make that
module useful without reintroducing app-owned shadow tables for Agno runtime
state.

Agno documents approvals as a Human-in-the-Loop flow:

- A protected tool uses `@approval` with a HITL primitive such as
  `requires_confirmation`.
- When a user triggers that tool, the run pauses and Agno persists a pending
  approval record in the configured database.
- An admin lists, reviews, approves, or rejects the record.
- The run can then be continued by the runtime path that owns the paused run.

Relevant docs:

- https://docs.agno.com/hitl/approval
- https://docs.agno.com/agent-os/approvals/overview
- https://docs.agno.com/api-reference/approvals/list-approvals
- https://docs.agno.com/api-reference/approvals/resolve-approval

The installed Agno package exposes async approval APIs on `AsyncPostgresDb`,
including `get_approvals`, `get_approval`, `get_pending_approval_count`, and
`update_approval`.

## Decision

Implement option A: AIOS approvals control only manages Agno-native approval
records.

The first implementation must use Agno `AsyncPostgresDb` public methods as the
source of truth. It must not create or depend on an AIOS-owned `os_approvals`
runtime table. Application control-plane operations such as scheduler manual
triggering, MCP token deletion, or MCP config changes are out of scope for this
slice unless they are later expressed as Agno approval-enabled tools.

## Goals

- Show pending and resolved Agno approvals in the existing AgentOS control UI.
- Let authorized admins approve or reject pending approvals.
- Keep the backend as a thin adapter over Agno async APIs.
- Preserve current AgentOS module navigation and response shape where practical.
- Add tests that prevent direct Agno approvals table coupling and double-resolve
  regressions.

## Non-Goals

- Do not build a generic approval engine for AIOS-owned control-plane actions.
- Do not create, migrate, or maintain a local `os_approvals` table.
- Do not directly query Agno approval tables from route handlers.
- Do not implement automatic paused-run continuation in this slice.
- Do not gate scheduler, MCP token, or settings operations unless a later spec
  makes those operations Agno approval-enabled tools.

## Architecture

### Backend Boundary

Add a focused approval service, for example
`api/services/approval_control_service.py`, responsible for all approval
projection and mutation.

Responsibilities:

- Obtain the Agno runtime DB through `get_async_agno_postgres_db()`.
- Call `AsyncPostgresDb.get_approvals()` for list and filter operations.
- Call `AsyncPostgresDb.get_approval()` for detail retrieval.
- Call `AsyncPostgresDb.get_pending_approval_count()` for summary metrics.
- Call `AsyncPostgresDb.update_approval(..., expected_status="pending", ...)`
  to approve or reject a pending approval.
- Normalize Agno approval dictionaries into AIOS response models.

Non-responsibilities:

- Building SQL against Agno approval tables.
- Owning approval persistence.
- Continuing paused Agent runs.
- Resolving non-Agno application actions.

### Routes

Keep `/api/os/approvals` as the frontend-facing control-plane surface.

Expected route shape:

- `GET /api/os/approvals`
  - Returns the AgentOS module payload plus approval-specific fields.
  - Supports filters aligned with Agno API fields: `status`, `source_type`,
    `approval_type`, `pause_type`, `agent_id`, `team_id`, `workflow_id`,
    `user_id`, `schedule_id`, `run_id`, `page`, and `limit`.
- `GET /api/os/approvals/{approval_id}`
  - Returns one normalized approval record.
- `POST /api/os/approvals/{approval_id}/resolve`
  - Body: `status`, optional `resolution_data`.
  - Accepted statuses: `approved`, `rejected`.
  - The backend sets `resolved_by` from the authenticated actor and
    `resolved_at` from server time.

The generic `GET /api/os/{module}` route can continue to serve dashboard
payloads. Specific approval actions should use explicit approval sub-routes so
the API surface stays clear and testable.

### Authorization

Read access should follow the existing OS control read permission pattern.
Resolve access must require a write/admin permission, for example the same
permission family used by other AgentOS control mutations.

The implementation should not trust client-provided `resolved_by`. The backend
must derive it from the authenticated actor. If no actor identity is available,
use a stable system fallback only where existing auth conventions allow it.

### Payload Model

Normalize records around the Agno approval response fields:

- `id`
- `status`
- `source_type`
- `approval_type`
- `pause_type`
- `tool_name`
- `tool_args`
- `agent_id`
- `team_id`
- `workflow_id`
- `user_id`
- `schedule_id`
- `run_id`
- `session_id`
- `source_name`
- `requirements`
- `context`
- `resolution_data`
- `resolved_by`
- `resolved_at`
- `created_at`
- `updated_at`
- `run_status`

Dashboard metrics should include at least:

- pending count
- approved count for the current page/filter
- rejected count for the current page/filter
- total count for the current page/filter

Counts that Agno exposes directly should use Agno APIs. Aggregations that Agno
does not expose can be derived from `get_approvals()` result pages for display,
but must not become direct table SQL in route handlers.

### Frontend

Reuse `AgentOSControl.vue` for the first slice instead of adding a separate
top-level page.

The `approvals` module should show:

- A filter row for status and source identifiers.
- A stable approval list with status, tool name, source, requester, and created
  time.
- A detail panel showing tool arguments, context, requirements, run/session
  identifiers, and resolution metadata.
- Approve and reject actions only for pending records and only when the user has
  write permission.
- Loading, empty, denied, and failed states consistent with existing AgentOS
  control UI.

The frontend API composable should add focused methods rather than overloading
scheduler methods:

- `listApprovals(params)`
- `getApproval(id)`
- `resolveApproval(id, payload)`

### Data Flow

1. A protected Agno tool is decorated with `@approval` and
   `@tool(requires_confirmation=True)`.
2. During an Agent or Team run, Agno pauses execution and writes a pending
   approval through `AsyncPostgresDb`.
3. AIOS calls `GET /api/os/approvals` to list pending or historical records.
4. An admin chooses approve or reject.
5. AIOS calls `AsyncPostgresDb.update_approval()` with
   `expected_status="pending"` and server-derived resolver metadata.
6. The approval record becomes approved or rejected.
7. Run continuation remains the responsibility of the Agent runtime path and can
   be designed in a later slice.

## Error Handling

- Unknown approval ID returns 404.
- Non-pending approval resolution returns 409 so double resolution is visible.
- Unsupported status returns 422.
- Agno DB/API errors return a controlled 500 with no table names or raw SQL in
  the client payload.
- Missing write permission returns 403.
- Empty result sets return a normal empty page, not an error.

## Testing Strategy

### Backend Unit Tests

- List approvals calls `AsyncPostgresDb.get_approvals()` with supported filters.
- Detail retrieval calls `AsyncPostgresDb.get_approval()`.
- Resolve calls `AsyncPostgresDb.update_approval()` with
  `expected_status="pending"`.
- Resolve derives `resolved_by` from the actor rather than request JSON.
- Double-resolve or stale status maps to 409.
- Unsupported resolve status maps to validation failure.

### Static Guard Tests

- Route handlers do not import synchronous `PostgresDb`.
- Route handlers do not execute SQL against Agno approvals tables.
- `os_approvals` is not required for runtime approvals.

### Frontend Tests

- The approvals module renders rows from API payloads.
- Pending records expose approve/reject actions.
- Resolved records do not expose mutation actions.
- Approve/reject refreshes the list or selected record after success.
- Error messages use existing API error handling conventions.

### Stage Verification

Implementation should pass:

- `uv run ruff check .`
- `uv run ty check .`
- `uv run pytest api/tests`
- `cd frontend && bun run test:shell`
- `cd frontend && bun run test:auth`
- `cd frontend && bun run build`
- `uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8001`

## Migration Notes

This feature should also remove or retire any existing `os_approvals` dashboard
bootstrap path if it is only serving placeholder data. If an existing migration
or table is still needed for unrelated historical UI data, keep it outside the
Agno approvals runtime path and document that exception explicitly.

When the first real protected tool is added, it should follow Agno docs:

- decorate with `@approval`
- use `@tool(requires_confirmation=True)`
- attach the same `AsyncPostgresDb` runtime DB to the Agent or Team

## Acceptance Criteria

- `/api/os/approvals` reads Agno-native approvals through `AsyncPostgresDb`.
- Admin users can approve or reject pending approvals.
- Double resolution is blocked by `expected_status="pending"`.
- The frontend shows approval list, detail, and resolve controls in the AgentOS
  approvals module.
- No new AIOS-owned approval runtime table is introduced.
- Existing scheduler and MCP control-plane actions are not silently folded into
  this approval model.
- Tests cover the service boundary, route behavior, and frontend interaction
  states.
