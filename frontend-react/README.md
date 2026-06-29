# Agno AIOS Frontend

`frontend-react` is the TanStack Start + React frontend for the AI information security platform.

## Stack

- TanStack Start / Router / Query
- React 19 + TypeScript
- Tailwind CSS v4
- shadcn/ui source components
- GSAP for dashboard reveal animation
- npm as the package manager

## Runtime Behavior

- The root route is auth-gated and uses FastAPI Users endpoints for registration, JWT login, current user restore, and OAuth provider discovery.
- After login, users land directly in the dashboard-first security operations workspace.
- The left sidebar contains product identity, grouped module navigation, platform status, plus desktop resize and collapse controls.
- The dashboard page contains the global metric cards; other modules keep their own work content without repeating dashboard-only metrics.
- The RAG workspace is organized into write entry, knowledge asset list, and retrieval validation panels; long document titles, sources, and metadata are compacted so cards do not overflow.
- The tracing workspace is organized into filters, date-range selection, paginated trace queue, compact queue stats, a relative trace timeline, linked conversation history, and a span detail waterfall.
- Native select controls are replaced by the local shadcn/Radix Select wrapper so dropdown popups follow light/dark mode.
- The header includes API status, refresh, light/dark theme switch, current user, and logout.
- The theme switch stores `light` or `dark` in localStorage using `agno-aios-theme`.

## Development

Install dependencies:

```bash
npm install
```

Run the dev server:

```bash
npm run dev -- --host 0.0.0.0
```

The backend is expected at `http://127.0.0.1:8000`; Vite proxies `/api` there.

## Build

Build the TanStack Start app:

```bash
npm run build
```

Build static assets into the repository-level `source/` directory for FastAPI hosting:

```bash
npm run build:source
```

## Verification

Run the frontend checks:

```bash
npm test
npm run check
npm run lint -- . --max-warnings=0
npx tsc --noEmit
npm run build
npm run build:source
```

Rendered QA should cover:

- Auth page loads before login.
- Register/login reaches the dashboard.
- The dashboard is the initial workspace after login.
- Removed sidebar text does not appear: `模块数`, `联通状态`, `搜索模块`.
- Removed right-column text does not appear: `运行上下文`, `模型与知识`.
- Dashboard-only metrics appear only on `态势总览`: `Agent 模型`, `Trace 活跃`, `知识切片`, `服务开关`.
- The central workspace uses a light surface in light mode and a dark surface in dark mode.
- The desktop sidebar can be dragged wider/narrower and collapsed.
- RAG and tracing panels render the redesigned workspaces without horizontal overflow.
- The tracing panel can switch between recent presets and custom dates, change page size, and move across pages.
- The tracing panel shows `Trace 时间线`, `关联对话记录`, and `Span waterfall` for the selected run.
- Dropdown popups remain dark in dark mode and no native `<select>` controls remain in the workspace.
- The light/dark switch toggles the root `dark` class and updates the visual theme.
- Desktop and mobile layouts have no horizontal overflow.
