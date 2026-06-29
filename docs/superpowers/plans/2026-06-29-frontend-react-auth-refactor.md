# Frontend React Auth Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `frontend-react` toward a modular TanStack/shadcn middle-office dashboard and add FastAPI Users aligned login/register UI.

**Architecture:** Keep the current dashboard behavior intact while extracting authentication and navigation into focused modules. Gate the existing security workspace behind an auth provider that talks to `/api/auth/jwt/login`, `/api/auth/register`, `/api/auth/users/me`, and `/api/auth/oauth/providers`.

**Tech Stack:** TanStack Start/Router/Query, React 19, TypeScript, Tailwind CSS v4, shadcn/ui source components, FastAPI Users JWT/OAuth endpoints.

---

### Task 1: Authentication Client And Provider

**Files:**
- Create: `frontend-react/src/lib/auth.ts`
- Create: `frontend-react/src/features/auth/auth-provider.tsx`

- [x] Add a typed auth client for login, register, current user, OAuth providers, and token persistence.
- [x] Add a React provider that restores the current user from `localStorage`, exposes `login`, `register`, `logout`, and refreshes `/users/me`.

### Task 2: Login And Register Surface

**Files:**
- Create: `frontend-react/src/features/auth/auth-screen.tsx`

- [x] Build a shadcn/Tailwind login-register screen with email/password forms.
- [x] Show configured OAuth providers from `/api/auth/oauth/providers`.
- [x] Submit login as `application/x-www-form-urlencoded` to match FastAPI Users JWT login.
- [x] Submit register as JSON to `/api/auth/register`.

### Task 3: Workspace Navigation Extraction

**Files:**
- Create: `frontend-react/src/features/workspace/navigation.ts`
- Modify: `frontend-react/src/components/security-platform.tsx`

- [x] Move workspace nav metadata and nav item type out of the large dashboard component.
- [x] Keep module labels aligned with the legacy Vue shell.

### Task 4: Auth Gate And User Controls

**Files:**
- Modify: `frontend-react/src/components/security-platform.tsx`

- [x] Rename the existing dashboard implementation to an internal workspace component.
- [x] Export `SecurityPlatform` as `AuthProvider + AuthGate + SecurityWorkspace`.
- [x] Add current user and logout controls to the dashboard header.

### Task 5: Verification

**Commands:**
- `fish -lc 'set -lx PATH ~/.local/share/fnm/node-versions/v24.14.0/installation/bin $PATH; npm run check'`
- `fish -lc 'set -lx PATH ~/.local/share/fnm/node-versions/v24.14.0/installation/bin $PATH; npm run lint -- . --max-warnings=0'`
- `fish -lc 'set -lx PATH ~/.local/share/fnm/node-versions/v24.14.0/installation/bin $PATH; npm run build'`
- `fish -lc 'set -lx PATH ~/.local/share/fnm/node-versions/v24.14.0/installation/bin $PATH; npm run build:source'`
- `uv run ruff check .`
- `uv run ty check .`
- Playwright CLI fallback if Browser MCP is unavailable: verify auth screen, login/register controls, dashboard gate, and dashboard module switching.
