# Frontend Vue Security Platform Design

## Goal

Switch the product frontend back to `frontend/` and make the Vue workspace read as an AI information-security middle platform. The work adds first-class registration and login, refines the existing shell and dashboard language around data-platform and SOC operations, updates Markdown documentation, verifies the result, and commits only aligned changes.

## Product Context

The target user is a security operator or platform engineer who needs one workspace for vulnerability intelligence, asset exposure, RAG knowledge, Agent orchestration, MCP tools, and runtime tracing. The page's job is not marketing. It should open as an operational command center after authentication and help the user move from data assets to security decisions.

External reference patterns:

- Data middle platforms such as Alibaba Cloud DataWorks and Huawei DataArts Studio emphasize ingestion, storage, governance, asset maps, data service, and data security.
- SOC/SIEM/SOAR products such as Microsoft Sentinel and Google Security Operations emphasize threat intelligence, incident investigation, automation, response, and traceable operations.
- Agno AIOS should combine these: data foundation plus security operations loop, with AI Agent capabilities as the orchestration layer.

## Scope

In scope:

- Keep `frontend/` as the active Vue/Vite frontend.
- Add a login/register screen that uses existing FastAPI Users endpoints:
  - `POST /api/auth/register`
  - `POST /api/auth/jwt/login`
  - `GET /api/auth/users/me`
  - `POST /api/auth/jwt/logout`
  - `GET /api/auth/oauth/providers`
- Persist the Bearer token in local storage and show a session-aware workspace header with current user and logout.
- Refine the existing shell so navigation and metrics use AI information-security middle-platform language.
- Improve old-page presentation in the main workspace without replacing the existing business components.
- Update README and superpowers documentation to state that `frontend/` is the main frontend.
- Verify with Python checks, frontend build, and Playwright screenshots.
- Commit only the changes that belong to this goal.

Out of scope:

- Backend auth schema changes.
- Rebuilding the React frontend.
- Adding new backend data products or incident APIs that do not exist yet.
- Committing unrelated existing changes in `frontend-react/`, `source/`, backend auth files, or lockfiles unless this task directly modifies them.

## Design Plan

### Token System

Color:

- `#071014` command background: SOC night-console surface.
- `#0E171F` data panel: dense working regions.
- `#EEF3F7` light workspace background.
- `#2F8FED` signal blue: selected route and data lineage.
- `#54D38A` verified green: healthy services and confirmed controls.
- `#F6C343` risk yellow and `#F06A6A` critical red: risk state accents.

Type:

- Display and body use the existing system Chinese stack for reliability in WSL/browser environments.
- Monospace is reserved for IDs, tokens, trace identifiers, sessions, and telemetry.
- Labels stay compact and scannable; no hero-scale text inside dashboard panels.

Layout:

```text
Unauthenticated
┌─────────────────────────────┬──────────────────────┐
│ Auth form                   │ Data lineage matrix   │
│ login/register tabs         │ SOC signals           │
│ OAuth providers if enabled  │ risk/service chips    │
└─────────────────────────────┴──────────────────────┘

Authenticated
┌──────────────┬──────────────────────────────────────┐
│ Sidebar      │ Header: module, user, theme, logout  │
│ grouped by   ├──────────────────────────────────────┤
│ platform     │ Data/SOC metrics strip               │
│ capability   ├──────────────────────────────────────┤
│              │ Existing module component            │
└──────────────┴──────────────────────────────────────┘
```

Signature:

The login page uses a "lineage matrix" made of small data cells, risk rails, and incident chips. It should feel like entering a secured data operations room, not a generic SaaS landing page.

### Self-Critique

The generic default for this kind of prompt would be a dark dashboard with a glowing gradient hero and oversized metric cards. This plan avoids that by keeping the workspace dense and utilitarian, putting the distinctive risk into one place: the auth screen's lineage matrix. The application shell remains restrained because repeated security operations need scanning speed more than spectacle.

## Architecture

Files to create:

- `frontend/src/lib/authClient.ts`: pure auth API client, token storage helpers, message extraction, and typed response handling.
- `frontend/src/lib/authClient.test.mjs`: Node-compatible behavioral tests for endpoint shape and token storage. This gives TDD coverage for auth logic without introducing a new test framework.
- `frontend/src/components/AuthScreen.vue`: login/register UI, OAuth provider loading, error states, and visual signature.

Files to modify:

- `frontend/src/App.vue`: auth gate, user session state, refined navigation groups, workspace signals, user/logout controls, and platform copy.
- `frontend/src/types/index.ts`: auth types.
- `frontend/src/style.css`: shared auth and shell styles plus light/dark polish.
- `frontend/package.json`: add a test script if needed.
- `README.md`: switch docs from `frontend-react` back to `frontend` and document auth.
- `docs/superpowers/plans/2026-06-29-frontend-vue-security-platform.md`: implementation plan.

## Data Flow

Startup:

1. App initializes theme.
2. App asks `authClient` for a stored token.
3. If a token exists, `GET /api/auth/users/me` runs with `Authorization: Bearer <token>`.
4. A valid response opens the workspace. An invalid response clears the token and returns to auth.

Login:

1. Auth screen submits `application/x-www-form-urlencoded` to `/api/auth/jwt/login`.
2. Token is stored only after a successful response.
3. App loads current user and opens the workspace.

Register:

1. Auth screen submits JSON to `/api/auth/register`.
2. On success, the same credentials are used to login.
3. The workspace opens with the new session.

Logout:

1. App calls `/api/auth/jwt/logout` with the token when available.
2. Token is cleared regardless of logout response so the local session cannot linger.

OAuth:

1. Auth screen loads provider names from `/api/auth/oauth/providers`.
2. Enabled providers are shown as buttons.
3. Clicking a provider requests `/api/auth/{provider}/authorize` and redirects to the returned `authorization_url`.

## Error Handling

- Network and HTTP errors surface as concise Chinese messages in the auth screen.
- Validation rejects empty or malformed email and passwords shorter than 8 characters before calling the API.
- Expired or invalid stored tokens are cleared and the user returns to login.
- OAuth provider loading failure should not block password login.

## Testing And Verification

- TDD red/green for `authClient`:
  - login uses FastAPI Users form data.
  - register uses JSON body.
  - current user sends Bearer token.
  - logout clears token even if the server fails.
- Frontend build: `fish -lc 'cd frontend; npm run build'`.
- Python checks from repo root:
  - `uv run ruff check .`
  - `uv run ty check .`
- Playwright:
  - Start frontend dev server through Fish so `fnm` exposes Node.
  - Capture unauthenticated desktop and mobile screenshots.
  - Stub auth APIs in browser context or exercise visible login/register states when backend is unavailable.

## Acceptance Criteria

- Visiting the Vue app without a valid token shows the new registration/login screen.
- Logging in with a valid backend account stores a token and opens the workspace.
- Registering a valid user calls the backend register endpoint and then logs in.
- The authenticated workspace shows the current user and a logout control.
- Navigation and metric copy reflect AI information-security middle-platform concepts.
- README names `frontend/` as the main frontend and removes React-first instructions.
- Verification commands are run and results are reported.
- Git commit exists for the aligned changes.
