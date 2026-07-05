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
- Review-fix RED: `uv run pytest api/tests/test_agent_eval_persistence.py api/tests/test_agent_eval_case_store.py api/tests/test_agent_eval_routes.py -q` failed on missing Agno eval id -> AIOS case run lookup, and `cd frontend && /home/shenss/.bun/bin/bun run test:shell` failed because the PerformanceEval disabled state only existed in a tooltip.
- Review-fix GREEN: the same backend target passed `24 passed`, and frontend shell test passed after enriching failures with `case_run_id`, making PerformanceEval disabled status visible, and requiring an explicit suite selection for suite runs.
- Smoke-fix RED: Playwright reproduced a real `/api/agent-evals/cases` 500 caused by concurrent hot-path table bootstrap during the workbench's parallel API load.
- Smoke-fix GREEN: `uv run pytest api/tests/test_agent_eval_persistence.py::test_ensure_agent_eval_tables_serializes_concurrent_bootstrap -q` passed after adding a process-local async bootstrap lock and ready marker.

## Verification
- `cd frontend && /home/shenss/.bun/bin/bun run test:shell`
  - Passed.
- `cd frontend && /home/shenss/.bun/bin/bun run test:auth`
  - Passed: `5 pass`, `0 fail`.
- `cd frontend && /home/shenss/.bun/bin/bun run build`
  - Passed.
- `uv run ruff check .`
  - Passed.
- `uv run ty check .`
  - Passed.
- `uv run pytest api/tests`
  - Passed: `205 passed`.
- `uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8001`
  - Started successfully on `http://0.0.0.0:8001`.
- `playwright-cli`
  - Registered a local smoke user, opened Evaluation, verified the dedicated Agent Evals workbench rendered, `PerformanceEval` disabled text was visible, `Run Suite` was disabled without an explicit suite, and the latest Agent Eval API requests returned 200 including `/api/agent-evals/cases`.

## Files changed
- `frontend/src/components/AgentEvals.vue`
- `frontend/src/App.vue`
- `frontend/src/modules/shellNavigation.ts`
- `frontend/src/i18n/locales/zh-CN.ts`
- `frontend/src/i18n/locales/en-US.ts`
- `frontend/src/uiShell.test.mjs`
- `api/persistence/agent_evals.py`
- `api/tests/test_agent_eval_persistence.py`

## Self-review findings
- The component does not expose a manual `PerformanceEval` run button or click handler.
- Failure replay is enabled through an explicit AIOS case-run projection: `/api/agent-evals/failures` keeps Agno run data intact and adds `case_run_id`, `case_id`, and `suite_run_id` from app-owned case-run rows.
- The failure projection uses one app-owned SQLAlchemy JSONB lookup per failure page, instead of one lookup per Agno eval run.
- Suite run action now requires a concrete suite filter instead of silently running the first suite while the filter is `all`.
- Agent Eval table bootstrap is serialized in-process so parallel workbench requests do not race DDL on first load.
- `frontend/dist` build output remains ignored and was not staged.

## Concerns
- Create/edit actions are permission-gated but currently show an unavailable-action notice because full create/edit forms were not part of the first UI slice.
