# Task 4 Report: Security Agent Eval Builder And Eval Runner

## What I implemented
- Added `SecurityRunRuntime.security_agent_context()` as a public async context manager that builds the full security Agent with MCP tools.
- Updated `SecurityRunRuntime.stream()` to reuse `security_agent_context()` while keeping fallback behavior unchanged.
- Added `api/services/agent_eval_runner.py` with:
  - `AgentEvalRunnerDependencies`
  - `run_case()`
  - `run_suite()`
  - `replay_case_run()`
- Wired all eval dimensions to Agno async Eval APIs:
  - `AccuracyEval.arun()`
  - `AgentAsJudgeEval.arun()`
  - `ReliabilityEval.arun()`
  - `PerformanceEval.arun()`
- Stored Agno eval IDs on case-run rows through the Task 2 case store.
- Added suite execution summary accounting and replay linkage.
- Added static guard coverage that the runner uses `.arun(` and does not use sync `.run(` or sync Agno Postgres DB APIs.

## Tests run and results
- `uv run pytest api/tests/test_agent_eval_runner.py::test_security_runtime_exposes_agent_context_for_evals -q`
  - RED: failed before `security_agent_context()` existed.
  - GREEN: passed after adding the context manager.
- `uv run pytest api/tests/test_agent_eval_runner.py::test_run_case_maps_all_eval_types_to_agno_arun -q`
  - RED: failed before `api.services.agent_eval_runner` existed.
  - GREEN: passed after implementing the runner.
- `uv run pytest api/tests/test_agent_eval_runner.py -q`
  - GREEN during worker execution: `4 passed`.
- `uv run pytest api/tests/test_agent_eval_runner.py api/tests/test_postgres_sql_templates.py::test_agent_eval_runner_prefers_agno_async_eval_api -q`
  - GREEN after final inspection: `5 passed in 6.93s`.
- `uv run ruff check api/services/security_run_runtime.py api/services/agent_eval_runner.py api/tests/test_agent_eval_runner.py api/tests/test_postgres_sql_templates.py`
  - GREEN: `All checks passed!`.
- `uv run ty check .`
  - GREEN during worker execution after Task 4 test typing fixes.
  - GREEN after final inspection: `All checks passed!`.
- `uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8001`
  - Worker verified startup reached `Application startup complete` and stopped it cleanly.

## TDD Evidence: RED command/output summary
- Command:
  ```bash
  uv run pytest api/tests/test_agent_eval_runner.py::test_security_runtime_exposes_agent_context_for_evals -q
  ```
  Output summary: failed as expected because `SecurityRunRuntime.security_agent_context()` did not exist.
- Command:
  ```bash
  uv run pytest api/tests/test_agent_eval_runner.py::test_run_case_maps_all_eval_types_to_agno_arun -q
  ```
  Output summary: failed as expected because `api.services.agent_eval_runner` did not exist.

## TDD Evidence: GREEN command/output summary
- Command:
  ```bash
  uv run pytest api/tests/test_agent_eval_runner.py api/tests/test_postgres_sql_templates.py::test_agent_eval_runner_prefers_agno_async_eval_api -q
  ```
  Output summary: `5 passed in 6.93s`.
- Command:
  ```bash
  uv run ruff check api/services/security_run_runtime.py api/services/agent_eval_runner.py api/tests/test_agent_eval_runner.py api/tests/test_postgres_sql_templates.py
  ```
  Output summary: `All checks passed!`.

## Files changed
- `api/services/security_run_runtime.py`
- `api/services/agent_eval_runner.py`
- `api/tests/test_agent_eval_runner.py`
- `api/tests/test_postgres_sql_templates.py`

## Self-review findings
- The runner calls only Agno eval `arun()` methods and the async Agno DB factory.
- The runner does not query Agno eval tables with SQL.
- The change does not edit security Agent prompts.
- `PerformanceEval` is implemented in the backend runner but no frontend button is introduced in this task.
- Current unrelated dirty files from another task were not staged or committed.

## Concerns
- Full-repo verification may be affected by unrelated dirty Memory/OS Control files currently present in the shared workspace. Task 4 scoped tests and scoped ruff passed.
