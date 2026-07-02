# P1 Frontend Consolidation Design

## Status

Approved by user message: `continue execution` on 2026-07-02.

## Context

P0 security work is already in place: RBAC permissions, user-scoped chat/session/trace access, audit logging, trace filter fixes, clipboard fallback, Chat streaming UX, and control-plane tone adjustments. P1 now reduces project drift and makes the frontend easier to operate safely.

The design reference is Agno AgentOS Control Plane:

- `/agent-os/control-plane`: one interface for chat, traces, knowledge, sessions, and performance.
- `/agent-os/introduction`: runtime plus control plane, with data ownership, request isolation, RBAC, and local trace/session storage.
- `/features/observability`: trace UI supports filtering by user, session, and time range, with trace data staying in the user's database.
- `/features/security-and-auth`: layered auth, roles/scopes, and user isolation are first-class behavior, not only UI state.

The local product should keep the existing dark security-dashboard identity, but remove duplicated explanations and inconsistent surface styling.

## Goals

1. Remove confirmed dead code and stale project structure.
2. Centralize frontend state that is currently scattered across pages or the shell.
3. Standardize design tokens for background, border, radius, padding, and shadow.
4. Add i18n foundations for Chinese and English UI copy.
5. Upgrade or remove dependencies only where evidence shows value and low migration risk.
6. Update documentation, including `AGENTS.md`, to match the active codebase.

## Non-Goals

- No backend permission rewrite in P1 unless P1 verification reveals a regression.
- No full visual redesign. P1 should consolidate the current control-plane style.
- No broad framework migration.
- No automatic translation of historical spec documents.
- No generated `source/assets/*` manual edits.

## Proposed Approach

Use a staged, commit-per-risk-boundary implementation:

1. Cleanup first, because dead code makes state and dependency audits noisy.
2. State management second, because design/i18n should consume stable shell state.
3. Design tokens and i18n third, because both touch many UI strings and styles.
4. Dependency/docs final, because lockfile and generated build output must reflect the finished code.

This is safer than a single large UI pass because each stage can be tested and reverted independently.

## Project Structure Decisions

The active frontend is `frontend/` (Vue 3 + Vite + Element Plus). The historical `frontend-react/` directory is a P1 deletion candidate. It can be removed only after confirming no package script, README instruction, or active import uses it.

Confirmed unused files should be deleted only when both conditions hold:

- A targeted `rg` search finds no active import or runtime reference outside generated output and historical docs.
- `npm run build` passes after deletion.

Expected cleanup candidates include:

- `frontend-react/`
- unused Vue starter asset `frontend/src/assets/vue.svg`
- unused composables such as `frontend/src/composables/useMessage.ts` and `frontend/src/composables/useDebounce.ts` if no live imports remain.

## State Management Design

Introduce Pinia for shared frontend state. The first P1 scope should centralize state that affects multiple views or the shell:

- `useAuthStore`: current user, role, login/logout state, user menu visibility, derived permission helpers.
- `useShellStore`: sidebar collapsed state, active module, theme, shared shell navigation state.
- `useSessionStore`: chat session list, current session id, loading/error state, session refresh/delete helpers.
- `useTraceStore`: trace queue, selected trace, filters, pagination, and loading state.

Page-local form state stays local. Do not move one-off input models into stores unless another component consumes them.

## i18n Design

Use `vue-i18n` with Chinese as the default locale and English as the secondary locale.

Initial migration scope:

- shell navigation
- common actions and statuses
- auth/login/logout text
- Chat/Trace/MCP/Skills high-level labels and toasts
- shared error strings

Copy in deeply specialized page tables can be migrated incrementally after the foundation exists. The implementation must not mix ad hoc English and Chinese in new code; new text should come from locale dictionaries unless it is data returned by the API.

## Design Token Design

Keep the current operational dashboard style and extract stable CSS variables:

- surface levels: app, panel, elevated, subtle
- borders: default, strong, focus
- radii: shell, panel, control
- spacing: xs through xl
- shadows: panel and popover
- semantic colors: success, warning, danger, info

Component CSS should consume tokens instead of hard-coded one-off colors where the token clearly exists. Avoid decorative gradients and large marketing sections. Right-side content panels should use the same panel border/background model in light and dark modes.

## Dependency Strategy

Use dependency changes only to reduce local implementation or enable a committed architecture:

- Add `pinia` for shared Vue state.
- Add `vue-i18n` for locale dictionaries and runtime switching.
- Keep `mermaid` because Chat already uses it.
- Remove dependencies only after `rg` and package-script evidence confirms they are unused.
- Avoid broad major upgrades during P1 unless the package manager reports a security or compatibility reason.

Backend dependency upgrades are not part of P1 unless verification shows a failing or vulnerable dependency. The backend already uses `uv`, `ruff`, and `ty`; keep those commands as the required Python verification path.

## Testing and Verification

Each implementation stage should run the smallest relevant checks, then the final stage runs the full suite:

- `uv run ruff check .`
- `uv run ty check .`
- backend unit tests that cover P0 security behavior if backend files change
- `npm run test:shell`
- `npm run test:auth`
- `npm run build`
- Playwright CLI smoke test for login shell, Chat, Trace filters, theme switching, i18n switching, and clipboard behavior

## Risk Controls

- Do not edit generated `source/assets/*` directly.
- Do not delete historical docs even if they reference removed directories.
- Do not remove `frontend-react/` until active references are checked.
- Keep Pinia migration focused on shell/shared state; avoid moving every page's local state.
- Keep i18n default locale Chinese to avoid breaking the user's current workflow.
- Commit after each clean verification boundary.
