# Dashboard Shell Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine `frontend-react` into a cleaner dashboard-first middle-office shell with fixed workspace scrolling, consistent product copy, and light/dark theme switching.

**Architecture:** Keep the existing TanStack Start route, auth gate, workspace data layer, and shadcn/Tailwind components. Remove sidebar utility widgets and the right inspector column, move dashboard metrics into the central workspace, and add a small reusable theme module that toggles the root `dark` class using localStorage.

**Tech Stack:** TanStack Start/Router, React 19, TypeScript, Tailwind CSS v4 dark variant, shadcn/ui `Button` and `Switch`, Vitest, Playwright CLI.

---

### Task 1: Theme State Module

**Files:**
- Create: `frontend-react/src/lib/theme.ts`
- Test: `frontend-react/src/lib/theme.test.ts`

- [x] Add a typed theme module with `ThemeMode = 'light' | 'dark'`, `THEME_STORAGE_KEY`, `getStoredTheme`, `setStoredTheme`, and `applyThemeClass`.
- [x] Test that invalid stored values fall back to `light`.
- [x] Test that `applyThemeClass` toggles the `dark` class on a provided root element.

### Task 2: Sidebar Simplification

**Files:**
- Modify: `frontend-react/src/features/workspace/workspace-sidebar.tsx`
- Modify: `frontend-react/src/components/security-platform.tsx`

- [x] Remove sidebar `backendLabel`, `navQuery`, and `onNavQueryChange` props.
- [x] Delete the left-top “模块数”“联通状态” cards and the module search input.
- [x] Keep grouped navigation and bottom platform status.
- [x] Update `SecurityWorkspace` to stop owning `navQuery`.

### Task 3: Central Dashboard Layout And Scroll Fix

**Files:**
- Modify: `frontend-react/src/components/security-platform.tsx`

- [x] Remove the top-level metrics strip outside the workspace.
- [x] Remove the right-side inspector column containing “运行上下文”“模型与知识”“服务状态”“最近 Trace”.
- [x] Move dashboard metrics into the central dashboard panel above the active module content.
- [x] Replace the broken desktop `overflow-hidden` chain with a single scrollable central workspace viewport.
- [x] Verify the central workspace scrollTop changes in Playwright when the user wheels over the middle panel.

### Task 4: Product Copy Cleanup

**Files:**
- Modify: `frontend-react/src/components/security-platform.tsx`
- Modify: `frontend-react/src/features/workspace/navigation.ts`

- [x] Remove user-facing copy containing “旧版”, “兼容”, “fallback”, and migration phrasing.
- [x] Replace offline “预览” language with neutral demo/local runtime wording where the backend is unavailable.
- [x] Keep technical labels such as URL Markdown “渲染预览” only when they describe the active feature.

### Task 5: Theme Toggle UI

**Files:**
- Modify: `frontend-react/src/components/security-platform.tsx`
- Modify: `frontend-react/src/styles.css`

- [x] Add a header theme toggle using existing shadcn `Switch` and lucide icons.
- [x] Apply `dark` to `document.documentElement` from stored mode on mount.
- [x] Add Tailwind `dark:` classes to the shell/sidebar/header/cards for usable light and dark modes.

### Task 6: Docs And Verification

**Files:**
- Modify: `README.md`
- Replace: `frontend-react/README.md`

- [x] Document dashboard-first layout, theme toggle, auth gate, and verification commands.
- [x] Run `npm test`, `npm run check`, `npm run lint -- . --max-warnings=0`, `npx tsc --noEmit`, `npm run build`, and `npm run build:source` in `frontend-react`.
- [x] Run `uv run ruff check .` and `uv run ty check .`.
- [x] Run Playwright CLI against `http://127.0.0.1:3000/` to verify login, no removed sidebar/right-column text, scroll works, theme toggle works, no console errors, and desktop/mobile screenshots.
