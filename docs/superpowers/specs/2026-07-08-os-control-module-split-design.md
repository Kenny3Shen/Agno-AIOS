# OS Control Module Split Design

## Goal

Split OS control into first-class functional modules without preserving the old aggregate service/composable compatibility layer, while keeping module permissions explicit at each route boundary.

## Scope

- Backend OS control payload modules: sessions, memory, metrics, evaluation, knowledge, approvals.
- Backend OS control routes: one route module per functional area.
- Frontend control-plane composables: one composable per functional area that calls the route it owns.
- Existing external paths may stay stable when they are already module-specific, but code must not route through a generic `get_control_payload()` or `useOsControlApi()` aggregate.

## Backend Boundaries

- `api/services/os_control_payloads.py`: shared payload types and formatting helpers only.
- `api/services/os_control_identity.py`: actor-to-user-scope helpers only.
- `api/services/os_memory_control.py`: Agno user memory projection, update, and delete.
- `api/services/os_sessions_control.py`: Agno session projection.
- `api/services/os_metrics_control.py`: trace/session/memory aggregate metrics.
- `api/services/os_evaluation_control.py`: AIOS evaluation control projection.
- `api/services/os_knowledge_control.py`: knowledge status projection.
- `api/services/approval_control_service.py`: remains approval domain service.

`api/services/os_control_service.py` is removed. There is no module registry or generic dispatcher.

## Route Boundaries And Permissions

- `api/routes/os_sessions_control.py`: `GET /api/os/sessions`, requires `sessions:read`.
- `api/routes/os_memory_control.py`: `GET /api/os/memory`, requires `memories:read`; `PATCH /api/os/memory/{memory_id}` requires `memories:write`; `DELETE /api/os/memory/{memory_id}` requires `memories:delete`. Mutations keep audit events.
- `api/routes/os_metrics_control.py`: `GET /api/os/metrics`, requires `metrics:read`.
- `api/routes/os_evaluation_control.py`: `GET /api/os/evaluation`, requires `evals:read`.
- `api/routes/os_knowledge_control.py`: `GET /api/os/knowledge`, requires `knowledge:read`.
- `api/routes/os_approvals_control.py`: approval list/detail/resolve endpoints, with `approvals:read` and `approvals:write`. Resolve keeps audit events.

Unsupported module names are no longer handled by a catch-all route. Missing paths are ordinary 404s.

## Frontend Boundaries

- `useControlPlaneApi.ts`: generic non-memory control modules only.
- `useMemoryControlApi.ts`: memory query/update/delete.
- `useApprovalsApi.ts`: approval list/detail/resolve.
- `useSchedulerApi.ts`: direct AgentOS schedule calls.

`useOsControlApi()` is removed from the implementation and from `useApi.ts` re-exports. Components import the functional composable they use directly.

## Testing

- Backend tests assert route-level permissions for each route module and verify memory mutations remain user-scoped and audited.
- Backend tests assert `api.services.os_control_service` is gone.
- Frontend source contracts assert `useOsControlApi()` is gone and components import the new functional composables directly.
- Existing shell/auth/build and focused backend tests must pass.
