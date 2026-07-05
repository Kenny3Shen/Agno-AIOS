Status: complete

Implemented:
- Added Agent Eval frontend API types for suites, cases, suite runs, case runs, Agno eval runs, trends, failures, and create payloads.
- Added `useAgentEvalsApi()` using the existing `apiFetch`, `messageFromResponse`, and `messageFromUnknown` pattern.
- Added Agent Eval frontend permission constants while keeping role behavior unchanged: admin uses `"*"`, user has `agent_eval:read`, guest has no eval permission.
- Added pure Agent Eval workbench helpers and deterministic shell-imported tests.

TDD evidence:
- RED: `bun run test:shell` failed on missing `agent_eval:write` permission assertion.
- GREEN: added permission constants; `bun run test:shell` passed.
- RED: `bun run test:shell` failed on missing `agentEvalsWorkbench.ts`.
- GREEN: added helper module; `bun run test:shell` passed.
- RED: `bun run test:shell` failed on missing `AgentEvalType`.
- GREEN: added types and composable; `bun run test:shell` passed.

Verification:
- `cd frontend && /home/shenss/.bun/bin/bun run test:shell` passed.
- `cd frontend && /home/shenss/.bun/bin/bun run test:auth` passed: 5 pass, 0 fail.
- `cd frontend && /home/shenss/.bun/bin/bun run build` passed.

Concerns:
- `agentEvalsRequestFailed` was added to the local API fallback key union as requested, but locale files are outside Task 6 ownership and were not modified.
