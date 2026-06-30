# AgentOS Control Plane Alignment Design

## Goal

Align Agno AIOS with the Agno OS reference navigation and Agno docs MCP guidance while keeping the product an AI security operations center.

## Product Context

The target user is a security operator or AI platform engineer. They need one control plane for chat, skills, MCP tools, knowledge, traces, sessions, memory, metrics, evaluations, approvals, schedules, and security data workflows.

## Design Direction

Subject: AI information-security control plane for Agno-powered security operations.

Audience: SOC analysts, incident responders, and internal platform engineers.

Single job: make agent runtime state visible and operable without hiding the security workflows already present in Agno AIOS.

Color token system:

- Command black `#15161B`
- Console panel `#1C1D22`
- Light operations surface `#EEF3F7`
- Signal blue `#147FA2`
- Verified green `#28A66F`
- Action orange-red `#FF4D2E`

Type:

- Existing Inter / Fira Sans / Microsoft YaHei stack remains the product default.
- JetBrains Mono / Fira Code remains reserved for ids, counters, trace names, and control-plane state.

Layout:

```text
Sidebar
┌ Home ┐
└ Dashboard ┘
────────────
Chat
Skills
MCP
Knowledge
Trace
Sessions
Studio
Memory
Metrics
Evaluation
Approvals
Scheduler
CVE
Assets
Collect
────────────
Settings
```

Signature:

The new AgentOS control-plane pages use a compact "runtime ledger" treatment: module cards, status counters, record tables, and small monospaced state chips. This fits the security-middle-platform subject better than adding decorative hero sections.

Dashboard uses data-platform style SVG/CSS charts instead of a marketing dashboard: latency trend, hourly heatmap, Agent load radar, and Span/Error distribution. Trace summary counters live here, not in the Trace detail workspace.

Self-critique:

The default generated solution would add a separate decorative dashboard for every missing item. This design keeps one reusable, restrained control-plane surface and spends visual emphasis only on the left rail order and dense runtime records.

## Agno Docs Findings

Agno `/features/api` says a live agent API covers runs, sessions, memory, knowledge, evals, traces, metrics, schedules, approvals, and components.

Agno `/reference-api/overview` lists Agents, Teams, Workflows, Sessions, Memory, Knowledge, and Evals as core AgentOS resources.

Agno `/memory/best-practices` recommends automatic memory for most production cases and monitoring memory growth.

Agno `/sessions/persisting-sessions/overview` documents session `metadata`, `runs`, and `user_id`; `/api-reference/sessions/update-session` supports metadata updates; `/api-reference/sessions/delete-session` permanently deletes sessions and runs.

Implementation consequence:

- Keep `update_memory_on_run=True`.
- Add `user_id` to chat runs.
- Implement Chat sidebar deletion as soft archive using an app overlay table plus Agno session metadata, not Agno hard delete.
- Expose Sessions, Memory, Metrics, Evaluation, Approvals, Scheduler, and Studio APIs.
- Keep missing heavy backends as explicit scaffolding rather than pretending they are complete.

## FastMCP Docs Findings

FastMCP `/integrations/fastapi` and `/servers/lifespan` require lifespan initialization when mounting MCP in FastAPI.

FastMCP `/deployment/http` recommends authentication for remote MCP.

FastMCP `/servers/middleware` recommends middleware for error handling, rate limiting, timing, logging, and response limiting.

Implementation consequence:

- Keep the existing explicit lifespan runtime because it starts the FastMCP ASGI app.
- Keep the ASGI token wrapper because Agno `MCPTools` currently sends a query token.
- Add best-effort FastMCP middleware imports for error handling, timing, rate limiting, and response limiting where installed.
- Document the remaining gap between query-token compatibility and native OAuth/JWT FastMCP auth.

## Backend Architecture

Create `api/services/os_control_service.py`.

Responsibilities:

- Read Agno sessions, memories, traces, spans, MCP config, Skills config, and knowledge status.
- Return lightweight records for AgentOS-style pages.
- Create local tables for approvals, schedules, and evaluation registry scaffolding.
- Avoid model calls and avoid long-running execution.

Create `api/routes/os_control.py`.

Responsibilities:

- Expose `/api/os/sessions`, `/api/os/studio`, `/api/os/memory`, `/api/os/metrics`, `/api/os/evaluation`, `/api/os/approvals`, and `/api/os/scheduler`.
- Return JSON responses shaped for the frontend shared panel.

Modify `api/routes/chat.py` and `api/services/llm_service.py`.

Responsibilities:

- Accept optional `user_id`.
- Pass `user_id` into `security_agent.arun`.
- Archive Chat sessions without deleting Agno runs/traces.

Modify `api/mcp/server.py`.

Responsibilities:

- Add FastMCP middleware when supported by the installed version.
- Preserve current token behavior.

## Frontend Architecture

Create `frontend/src/components/AgentOSControl.vue`.

Responsibilities:

- Render a shared page for Sessions, Studio, Memory, Metrics, Evaluation, Approvals, and Scheduler.
- Fetch `/api/os/{module}`.
- Show summary counters, capability notes, and record tables.
- Handle empty and error states.

Modify `frontend/src/types/index.ts`.

Responsibilities:

- Add shared control-plane response types.

Modify `frontend/src/composables/useApi.ts`.

Responsibilities:

- Add `useOsControlApi()`.

Modify `frontend/src/App.vue`.

Responsibilities:

- Put Dashboard directly under Home and above the middle nav.
- Order middle nav as Chat, Skills, MCP, Knowledge, Trace, then the new AgentOS pages and other security tools.
- Route all missing pages to the shared control-plane component.

Modify `frontend/src/components/Trace.vue`.

Responsibilities:

- Make the waterfall/detail body scroll reliably on desktop and mobile.
- Show only the selected Trace detail. Trace Queue lives under the left `Trace` nav item.

Modify `frontend/src/components/Dashboard.vue`.

Responsibilities:

- Own trace totals, OK/error counts, latency trends, hourly heatmap, Agent load radar, and Span/Error distribution.

## Testing

Backend:

- Add a focused Node shell test for navigation ordering and new components.
- Add a Python syntax/import check through `uv run ruff check .`.
- Add static type check through `uv run ty check .`.

Frontend:

- Extend `frontend/src/uiShell.test.mjs` for sidebar order, Dashboard placement, and missing page wiring.
- Run `npm run test:shell`.
- Run `npm run build`.

Runtime:

- Use `playwright-cli` to inspect authenticated shell shape with mocked auth/session APIs when needed.
- Verify Trace page can scroll its detail/waterfall area.
