# AgentOS Control Plane Development Notes

## Purpose

This document records the Agno OS alignment work for Agno AIOS. The goal is to keep the product focused on an AI security operations center while adding the missing AgentOS control-plane surfaces shown in the Agno OS reference image.

## Reference Image Gap Analysis

The reference image shows a left navigation with:

- Home
- Chat
- Sessions
- Traces
- Studio
- Memory
- Knowledge
- Metrics
- Evaluation
- Approvals
- Scheduler
- Settings

Agno AIOS already has Home, Chat, Trace, Knowledge, MCP, Skills, Dashboard, CVE, Assets, Collect, and Settings. The missing AgentOS-style capabilities are:

- Sessions: session inventory and session-level run history.
- Studio: registered agent, team, workflow, MCP, and skill components.
- Memory: stored user memories, memory counts, and memory hygiene status.
- Metrics: aggregated run, trace, latency, span, and error metrics.
- Evaluation: evaluation run registry and evaluation readiness.
- Approvals: pending sensitive action approvals and resolution state.
- Scheduler: recurring automation schedule registry and run history.

MCP and Skills are not in the reference left rail, but they are important to this AI security center. They remain first-class navigation entries.

## Agno Docs MCP Review

The Agno docs MCP review used `/features/api`, `/reference-api/overview`, `/memory/best-practices`, `/sessions/persisting-sessions/overview`, `/api-reference/sessions/update-session`, and `/api-reference/sessions/delete-session`.

Important Agno guidance:

- A live Agent API should manage runs, sessions, memory, knowledge, evals, traces, metrics, schedules, approvals, and components. Source: `/features/api`.
- AgentOS core resources include Agents, Teams, Workflows, Sessions, Memory, Knowledge, and Evals. Source: `/reference-api/overview`.
- Memory production guidance recommends automatic memory for most cases and says every production memory design should monitor growth and token impact. Source: `/memory/best-practices`.
- Agno session storage includes `metadata`, `runs`, `user_id`, `created_at`, and `updated_at`. Source: `/sessions/persisting-sessions/overview`.
- Agno's update-session API allows modifying session properties such as metadata. Source: `/api-reference/sessions/update-session`.
- Agno's delete-session API permanently deletes the session and associated runs, so it is not suitable for the Chat sidebar "delete" affordance when Trace history must remain available. Source: `/api-reference/sessions/delete-session`.
- The current backend already follows several Agno patterns: `PostgresDb`, tracing via `setup_tracing`, knowledge via `Knowledge` + `PgVector`, enabled local Skills, and `MCPTools`.

Backend gaps identified before this iteration:

- Chat runs do not pass an authenticated `user_id` into `Agent.arun`, so memory and sessions are less isolated than Agno recommends for multi-user products.
- Sessions exist via `/api/chat/sessions`, but there is no dedicated AgentOS-style session control page/API.
- Memory storage exists through Agno `PostgresDb`, but there is no memory inventory or stats API.
- Metrics are partially visible in Trace UI, but there is no aggregated control-plane metrics API.
- Evaluations, approvals, and schedules do not have product APIs yet.
- Studio-level component registry is spread across settings, MCP, Skills, and static code instead of being presented as one control-plane registry.

Implemented backend and UI resolution:

- Chat runs now pass the authenticated `user_id` into Agno runs.
- Sessions, Studio, Memory, Metrics, Evaluation, Approvals, and Scheduler now have AgentOS-style APIs and shared frontend pages.
- Metrics are no longer duplicated as Trace page summary cards; Dashboard owns aggregate charts and status views.
- Chat sidebar deletion is implemented as soft archive, not Agno hard delete.
- The backend creates `app.chat_session_archives` and also marks `agno.agno_sessions.metadata.agno_aios_archived=true` when available.
- `/api/chat/sessions` hides archived sessions by default, while `/api/chat/sessions/{session_id}`, `/api/traces`, and `/api/traces/{trace_id}` keep reading original Agno data.
- `/api/os/sessions` includes archived sessions so the AgentOS control plane still shows the full inventory.

## Security And RBAC Notes

Agno AIOS now treats frontend identity as display-only. Backend routes derive the actor from the authenticated JWT user and use centralized RBAC helpers for authorization.

- Roles are `admin`, `user`, and `guest`.
- Admin users can inspect all Session, Conversation, and Trace data.
- Standard users can access only their own Session, Chat, and Trace data.
- Guest users are read-only for owned resources.
- Session ownership is checked before detail reads or archive mutations, preventing Session ID guessing.
- Trace list filters are preserved, but non-admin users are automatically scoped to their own `user_id`.
- Audit logs are written to `app.audit_logs` and cover auth, delete/archive, Knowledge, MCP, Skill, Settings, and admin operations.
- UI visibility is secondary to backend enforcement; protected APIs must reject unauthorized requests even when menus are hidden.

## FastMCP Docs MCP Review

The FastMCP docs MCP review used `/integrations/fastapi`, `/servers/lifespan`, `/deployment/http`, and `/servers/middleware`.

Important FastMCP guidance:

- When mounting FastMCP into FastAPI, the FastMCP lifespan must be passed or combined so the session manager initializes. Source: `/integrations/fastapi` and `/servers/lifespan`.
- Remote MCP servers should use authentication; some clients refuse unauthenticated remote MCP. Source: `/deployment/http`.
- MCP middleware is the recommended shape for cross-cutting logging, timing, rate limiting, error handling, and response limiting. Source: `/servers/middleware`.

MCP gaps identified before this iteration:

- The runtime manually enters the FastMCP ASGI lifespan, which satisfies session-manager startup, but the design should be documented because it differs from the `combine_lifespans` example.
- Token authentication is implemented as an ASGI wrapper and supports Bearer and query tokens. That is usable for current Agno `MCPTools`, but it is not represented as FastMCP middleware.
- Response limiting, rate limiting, timing, and error-handling middleware are now installed when the available FastMCP version exposes them. The ASGI token wrapper remains because Agno `MCPTools` currently uses a query token.

## Implementation Scope

This iteration implements an AgentOS-aligned MVP:

- Reorder the sidebar:
  - Home
  - Dashboard
  - Chat
  - Skills
  - MCP
  - Knowledge
  - Trace
  - Sessions
  - Studio
  - Memory
  - Metrics
  - Evaluation
  - Approvals
  - Scheduler
  - remaining security data tools: CVE, Assets, Collect
  - Settings
- Fix Trace Span Waterfall scrolling by giving the detail shell and waterfall list an explicit scrollable height chain.
- Move Trace Queue into the expandable left navigation under `Trace`, mirroring the Chat session list.
- Remove Trace page summary cards from the Trace content area; Dashboard owns query totals, OK counts, latency, heatmaps, and distribution charts.
- Expand Dashboard with native SVG/CSS data-platform charts: latency trend, hour heatmap, Agent load radar, and Span/Error distribution.
- Add `/api/os/*` endpoints for missing control-plane modules.
- Add frontend pages for the missing modules using a shared control-plane panel.
- Pass `user_id` from authenticated chat requests into Agno runs.
- Add FastMCP middleware where available while keeping the existing ASGI token wrapper for URL-token compatibility.
- Update README and docs to describe the new AgentOS-aligned control plane.

Out of scope for this iteration:

- Full AgentOS runtime replacement.
- Real production scheduler workers.
- Human-in-the-loop approval resume for paused Agno runs.
- Full evaluation runner. The evaluation page/API exposes readiness and registry scaffolding.
