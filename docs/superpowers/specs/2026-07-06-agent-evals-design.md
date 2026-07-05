# Agent Evals Center Design

Date: 2026-07-06

## Context

Agno AIOS currently has an `Evaluation` navigation item, but the page is only a
generic AgentOS ledger over the old `os_eval_runs` control table. The requested
feature is a real Agent Evals center for the security Agent, aligned with Agno
Evals and suitable for regression suites such as CVE judgment accuracy, expected
MCP tool usage, permission-boundary behavior, degradation-mode stability, and
failure replay.

Relevant Agno docs:

- https://docs.agno.com/evals/overview
- https://docs.agno.com/agent-platform/evals
- https://docs.agno.com/evals/accuracy/overview
- https://docs.agno.com/evals/agent-as-judge/overview
- https://docs.agno.com/evals/reliability/overview
- https://docs.agno.com/evals/performance/overview

Agno describes Evals across four dimensions:

- `accuracy`: correctness checks using LLM-as-a-judge methodology.
- `agent-as-judge`: custom criteria and scoring.
- `reliability`: tool calls, error handling, and related behavior.
- `performance`: runtime and memory footprint.

The installed Agno package exposes the corresponding Eval classes and async eval
run storage APIs, including `AccuracyEval`, `AgentAsJudgeEval`,
`ReliabilityEval`, `PerformanceEval`, `AsyncPostgresDb.get_eval_runs()`, and
`AsyncPostgresDb.get_eval_run()`.

## Decision

Implement route 1: AIOS owns eval suite and case orchestration metadata, while
Agno owns eval execution results.

AIOS app-owned tables use Async SQLAlchemy and live under the app control-plane
boundary. Agno eval run results are written and read through Agno public async
APIs wherever available. The implementation must not query Agno eval internal
tables directly.

The first implementation includes backend support for all four Agno dimensions:

- `accuracy`
- `agent_as_judge`
- `reliability`
- `performance`

The frontend must not expose a manual `PerformanceEval` run button in the first
slice. It may display performance history, filtering, and status if results
exist.

## Async API Priority

Use Agno async APIs first.

- Eval execution must use `arun()` for Agno Eval classes when the installed
  class exposes it.
- Eval result reads must use `AsyncPostgresDb.get_eval_runs()` and
  `AsyncPostgresDb.get_eval_run()`.
- Runtime DB access must come from `get_async_agno_postgres_db()`.
- App-owned suite/case metadata must use the existing Async SQLAlchemy
  engine/session boundary.
- A synchronous Agno API is allowed only as a narrow exception when the installed
  Agno package has no async equivalent for that capability. That exception must
  stay behind a small adapter, run off the request event loop if needed, and be
  documented in code and tests.

## Goals

- Let admins manage security Agent eval suites and cases.
- Run a suite or a single case through Agno Evals.
- Store only AIOS orchestration metadata in app-owned tables.
- Persist and retrieve eval results through Agno DB APIs.
- Show eval history, trends, failed samples, and replay actions.
- Make expected MCP tool calls and permission-boundary checks first-class case
  configuration.
- Keep the UI consistent with the current dense security operations console.
- Add tests that guard the Agno/API boundary and the hidden Performance button.

## Non-Goals

- Do not build a replacement eval result store for Agno.
- Do not query Agno eval tables with SQL.
- Do not make performance benchmarks part of the first visible manual workflow.
- Do not implement scheduled weekly production evals in this slice.
- Do not implement CI wiring in this slice.
- Do not edit security Agent prompts from this feature.

## Architecture

### Backend Services

Add focused services instead of growing `os_control_service.py`.

`api/services/agent_eval_case_store.py`

- Owns Async SQLAlchemy access to AIOS eval suites, cases, suite runs, and case
  runs.
- Creates, lists, updates, disables, and tags suites and cases.
- Persists suite-run and case-run orchestration status.
- Does not instantiate Agno Eval classes.
- Does not read Agno runtime tables.

`api/services/agent_eval_runner.py`

- Loads a case from the case store.
- Builds the security Agent or controlled callable required by the selected
  Agno Eval type.
- Maps case configuration to Agno Eval classes.
- Executes `AccuracyEval`, `AgentAsJudgeEval`, `ReliabilityEval`, and
  `PerformanceEval` through their public async `arun()` APIs when available.
- Reuses a captured Agent response for `agent_as_judge` and `reliability`.
- Lets `AccuracyEval` run through its official agent-backed API instead of
  forcing a precomputed output path that the local Agno API does not expose.
- Runs `PerformanceEval` against an explicit callable that wraps the target
  Agent/case path.
- Records Agno eval run IDs returned or persisted by Agno in the case-run
  metadata.
- Handles partial case failures without aborting the entire suite.

`api/services/agent_eval_result_service.py`

- Uses `get_async_agno_postgres_db()`.
- Reads historical results through `AsyncPostgresDb.get_eval_runs()`.
- Reads detail through `AsyncPostgresDb.get_eval_run()`.
- Joins Agno result projections with AIOS suite/case metadata.
- Produces trend, failure queue, and detail payloads for the frontend.

`api/routes/agent_evals.py`

- Exposes explicit `/api/agent-evals/...` routes.
- Does not overload generic `/api/os/{module}` for mutations.
- Keeps the existing `Evaluation` navigation item but moves it to the dedicated
  feature surface.
- Does not call synchronous Agno DB APIs from async route handlers.

### App-Owned Tables

Use Async SQLAlchemy models under the configured app schema.

`app.agent_eval_suites`

- `id`
- `name`
- `description`
- `target_agent_id`
- `enabled`
- `tags`
- `created_by`
- `created_at`
- `updated_at`

`app.agent_eval_cases`

- `id`
- `suite_id`
- `name`
- `description`
- `target_agent_id`
- `input`
- `expected_output`
- `criteria`
- `threshold`
- `eval_types`
- `expected_tool_calls`
- `expected_tool_call_arguments`
- `allow_additional_tool_calls`
- `performance_config`
- `metadata`
- `enabled`
- `created_at`
- `updated_at`

`app.agent_eval_suite_runs`

- `id`
- `suite_id`
- `status`
- `started_by`
- `started_at`
- `completed_at`
- `summary`
- `error_summary`

`app.agent_eval_case_runs`

- `id`
- `suite_run_id`
- `case_id`
- `status`
- `started_at`
- `completed_at`
- `agent_run_id`
- `session_id`
- `trace_id`
- `agno_eval_run_ids`
- `error_type`
- `error_summary`
- `replay_of_case_run_id`

`agno_eval_run_ids` is a JSON object keyed by eval type, for example
`{"accuracy": "...", "reliability": "..."}`. This avoids duplicating Agno eval
result payloads while keeping AIOS able to connect cases to Agno history.

Table creation should be part of startup/bootstrap or a migration path, not a
per-request hot path.

### Agno Eval Mapping

`accuracy`

- Use `AccuracyEval` for expected-output judgment through its agent-backed API.
- Case fields: `input`, `expected_output`, optional guidelines/context.
- Security examples: CVE severity judgment, exploitability assessment, stable
  fallback wording.

`agent_as_judge`

- Use `AgentAsJudgeEval`.
- Case fields: `criteria`, `threshold`, optional evaluator Agent.
- Security examples: permission-boundary adherence, analyst-quality reasoning,
  refusal of unsafe action requests.

`reliability`

- Use `ReliabilityEval`.
- Case fields: `expected_tool_calls`, `expected_tool_call_arguments`,
  `allow_additional_tool_calls`.
- Security examples: required MCP tool invocation, no unexpected MCP tools,
  expected tool arguments for CVE or playbook lookups.

`performance`

- Use `PerformanceEval` in the backend.
- Case fields: `performance_config` with iterations, warmup, runtime, and memory
  toggles.
- First frontend slice shows performance history and filters only. Manual
  performance execution is not exposed because model, MCP, and network variance
  can make ad hoc UI benchmarks noisy.

## Routes

Suite and case management:

- `GET /api/agent-evals/suites`
- `POST /api/agent-evals/suites`
- `GET /api/agent-evals/suites/{suite_id}`
- `PATCH /api/agent-evals/suites/{suite_id}`
- `GET /api/agent-evals/cases`
- `POST /api/agent-evals/cases`
- `GET /api/agent-evals/cases/{case_id}`
- `PATCH /api/agent-evals/cases/{case_id}`

Execution:

- `POST /api/agent-evals/suites/{suite_id}/runs`
- `POST /api/agent-evals/cases/{case_id}/runs`
- `POST /api/agent-evals/case-runs/{case_run_id}/replay`

Results:

- `GET /api/agent-evals/runs`
- `GET /api/agent-evals/runs/{suite_run_id}`
- `GET /api/agent-evals/case-runs/{case_run_id}`
- `GET /api/agent-evals/agno-runs`
- `GET /api/agent-evals/agno-runs/{eval_run_id}`
- `GET /api/agent-evals/trends`
- `GET /api/agent-evals/failures`

The `agno-runs` endpoints are thin projections over Agno `AsyncPostgresDb` eval
run APIs. They must not depend on Agno table names.

## Data Flow

1. An admin creates a suite and one or more cases.
2. The backend stores suite/case metadata in app-owned tables through Async
   SQLAlchemy.
3. An authorized user starts a suite or case run.
4. The runner creates a suite-run and case-run record.
5. The runner invokes the configured Agno Eval classes according to their public
   API shape.
6. For `agent_as_judge` and `reliability`, the runner captures one Agent output
   and feeds it into both dimensions when both are enabled.
7. For `accuracy`, the runner passes the Agent and expected output to
   `AccuracyEval` and lets Agno manage the eval run.
8. For `performance`, the runner passes an explicit callable to
   `PerformanceEval`.
9. Agno stores eval run results in its database.
10. AIOS stores only orchestration status and Agno eval run IDs.
11. The frontend reads suite/case metadata from AIOS and eval results from Agno
   projections.
12. Failed samples can be replayed by creating a new case run linked to the
    failed `case_run_id`.

## Authorization

Add dedicated permissions:

- `agent_eval:read`: read suites, cases, history, trends, and failure details.
- `agent_eval:write`: create, update, disable, and tag suites or cases.
- `agent_eval:run`: run suites, run cases, and replay failures.

The backend must derive actor identity from authenticated users. It must not
trust client-provided `started_by`, `created_by`, or resolver metadata.

## Error Handling

- A single case failure marks that case run as failed and does not abort the
  entire suite.
- Suite responses include counts for passed, failed, skipped, and errored cases.
- Unknown suite, case, case-run, or eval-run IDs return 404.
- Disabled suites or cases cannot be run unless an explicit override is later
  designed.
- Invalid eval type or malformed case config returns 422.
- Missing read/write/run permission returns 403.
- Agno Eval or Agent execution exceptions are summarized for the UI and retained
  in `agent_eval_case_runs.error_summary`.
- Client payloads must not expose raw SQL, table names, stack traces, or secrets.

## Frontend Design

The local UI observation found these relevant patterns:

- Current `Evaluation` is only an empty generic ledger and should be replaced.
- `Knowledge` provides the best pattern for dense case management: metric strip,
  compact forms, action icons, and a responsive table.
- `Trace` provides the best pattern for history and drill-down: KPI strip,
  filter row, left list, right runs/detail area, and a drawer for complex
  details.
- `Approvals` provides the best pattern for failure queues: queue on the left,
  structured JSON/detail blocks on the right.
- `MCP` provides useful compact service and token cards for tool-call status
  presentation.

The Eval Center page should therefore use:

- Top KPI strip: suites, cases, pass rate, failures, latest run, performance
  samples.
- Filter row: suite, case, eval type, status, target Agent, tag, date range.
- Left panel: suite/case/run navigation.
- Main panel: case table or run list depending on selected tab.
- Detail drawer: input, output, expected output, criteria, judge result, tool
  calls, expected tool calls, Agno eval run IDs, trace/session/run IDs, and
  replay action.
- Tool-call chips: `expected`, `called`, `missing`, `unexpected`.
- Performance history visible in filters and result lists, but no visible manual
  run button in the first slice.

Do not make a marketing or hero page. The first screen is the usable eval
workbench.

## Testing Strategy

### Backend Unit Tests

- Suite and case CRUD use Async SQLAlchemy helpers.
- Suite run creates suite-run and case-run records.
- Single case failure produces a partial suite result.
- Runner maps each eval type to the expected Agno Eval class.
- Result service calls `AsyncPostgresDb.get_eval_runs()` and `get_eval_run()`.
- Replay creates a new case run linked to the failed source case run.
- Authorization checks distinguish read, write, and run permissions.

### Static Guard Tests

- No route or result service queries Agno eval table names directly.
- Eval result adapters do not import synchronous Agno `PostgresDb`.
- Eval runner uses Agno `arun()` methods for Eval execution when available.
- Any synchronous Agno exception is isolated behind a named adapter and covered
  by a source-level test.
- Performance run controls are not exposed in the frontend first slice.

### Frontend Tests

- Eval navigation renders the real workbench instead of the generic ledger.
- Users without write/run permission do not see create, edit, run, or replay
  actions.
- Case table renders eval type, status, target Agent, tags, and latest result.
- Failure detail drawer shows input, output, judge criteria, tool-call status,
  Agno eval run IDs, and trace/session/run links.
- Performance results can be displayed or filtered, but manual performance run
  action is absent.

### Verification Commands

Run at completion:

```bash
uv run ruff check .
uv run ty check .
uv run pytest api/tests
cd frontend && /home/shenss/.bun/bin/bun run test:shell
cd frontend && /home/shenss/.bun/bin/bun run test:auth
cd frontend && /home/shenss/.bun/bin/bun run build
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
```

Use Playwright for a frontend smoke pass over Evaluation, case management,
history, failure detail, and mobile/desktop layout.

## Acceptance Criteria

- The Evaluation navigation opens a real Agent Evals center.
- Admins can create, update, disable, and list suites and cases.
- Authorized users can run suite/case evals for accuracy, agent-as-judge,
  reliability, and backend performance.
- The frontend does not expose manual performance run controls in the first
  slice.
- Eval execution and result history/detail use Agno async APIs wherever the
  installed package exposes them.
- AIOS stores suite/case orchestration metadata through Async SQLAlchemy.
- Failed cases are visible and replayable.
- Expected MCP tool-call status is visible and test-covered.
- Tests prevent direct coupling to Agno eval internal tables.
