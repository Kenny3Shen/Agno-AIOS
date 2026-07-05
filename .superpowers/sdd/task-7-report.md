# Task 7 Report: Evaluation Workbench UI

## What I implemented
- Added `frontend/src/components/AgentEvals.vue` as a dedicated Evaluation workbench.
- Mapped the `evaluation` nav entry to `AgentEvals` in `App.vue`.
- Removed `evaluation` from OS control tabs while keeping it full-canvas.
- Added Chinese and English `agentEvals` locale sections plus `api.errors.agentEvalsRequestFailed`.
- Added shell tests asserting the dedicated component mapping, no OS-control fallback, visible `PerformanceEval`, and no manual performance run action.
- Built the UI around existing dense security-dashboard primitives: KPI strip, compact filters, tabs, case/run/failure/trend lists, and a right detail panel.
- Gated write actions by `agent_eval:write` and run/replay actions by `agent_eval:run`.

## TDD Evidence
- RED: `cd frontend && /home/shenss/.bun/bin/bun run test:shell` failed before `AgentEvals.vue` existed and before `evaluation` mapped away from `AgentOSControl`.
- GREEN: `cd frontend && /home/shenss/.bun/bin/bun run test:shell` passed after adding the component, mapping, shell navigation changes, and tests.

## Verification
- `cd frontend && /home/shenss/.bun/bin/bun run test:shell`
  - Passed.
- `cd frontend && /home/shenss/.bun/bin/bun run test:auth`
  - Passed: `5 pass`, `0 fail`.
- `cd frontend && /home/shenss/.bun/bin/bun run build`
  - Passed.

## Files changed
- `frontend/src/components/AgentEvals.vue`
- `frontend/src/App.vue`
- `frontend/src/modules/shellNavigation.ts`
- `frontend/src/i18n/locales/zh-CN.ts`
- `frontend/src/i18n/locales/en-US.ts`
- `frontend/src/uiShell.test.mjs`

## Self-review findings
- The component does not expose a manual `PerformanceEval` run button or click handler.
- Failure replay is only enabled when the selected failure payload provides an AIOS `case_run_id`, avoiding accidental replay calls with an Agno eval run ID.
- No backend files or Task 6 helper/type files were changed.
- `frontend/dist` build output remains ignored and was not staged.

## Concerns
- Create/edit actions are permission-gated but currently show an unavailable-action notice because full create/edit forms were not part of the first UI slice.
