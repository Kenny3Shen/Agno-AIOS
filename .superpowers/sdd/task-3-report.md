# Task 3 Report: Agno Async Eval Result Service

## What I implemented

- Added `api/services/agent_eval_result_service.py`.
- Added normalization for dict rows, dataclass rows, Pydantic-style objects, `to_dict()` objects, and plain attribute objects.
- Added async result listing through `get_async_agno_postgres_db().get_eval_runs(...)`.
- Added single-run lookup through `get_async_agno_postgres_db().get_eval_run(...)`.
- Added deterministic trends grouped by created date, eval type, and passed/failed/unknown status.
- Added failed-run listing based on normalized `passed is False`.
- Added static guard coverage to prevent direct table SQL and non-async DB usage in this service.

## Tests run and results

- `uv run pytest api/tests/test_agent_eval_result_service.py -q`
  - Result: PASS, `6 passed in 0.45s`
- `uv run pytest api/tests/test_postgres_sql_templates.py::test_agent_eval_result_service_uses_agno_async_api_only -q`
  - Result: PASS, `1 passed in 7.17s`
- `uv run ruff check .`
  - Result: PASS, `All checks passed!`
- `uv run ty check .`
  - Result: FAIL with one remaining diagnostic outside Task 3 scope:
    - `api/services/os_control_service.py:490` passes `str | int` to `_record(status: str)`.

## TDD Evidence

### RED command/output summary

Command:

```bash
uv run pytest api/tests/test_agent_eval_result_service.py -q
```

Output summary:

```text
ERROR collecting api/tests/test_agent_eval_result_service.py
ImportError: cannot import name 'agent_eval_result_service' from 'api.services'
1 error
```

This matched the expected RED state because the service module did not exist yet.

### GREEN command/output summary

Command:

```bash
uv run pytest api/tests/test_agent_eval_result_service.py -q
```

Output summary:

```text
6 passed in 0.45s
```

Static guard command:

```bash
uv run pytest api/tests/test_postgres_sql_templates.py::test_agent_eval_result_service_uses_agno_async_api_only -q
```

Output summary:

```text
1 passed in 7.17s
```

## Files changed

- `api/services/agent_eval_result_service.py`
- `api/tests/test_agent_eval_result_service.py`
- `api/tests/test_postgres_sql_templates.py`
- `.superpowers/sdd/task-3-report.md`

## Self-review findings

- The service does not import or instantiate non-async Agno DB classes.
- The service does not query eval tables with SQL.
- `get_eval_runs` tuple and list-only return shapes are both covered.
- Trend aggregation is deterministic and intentionally simple.
- Existing unrelated dirty files were left unstaged and unchanged.

## Concerns

- `uv run ty check .` is blocked by an existing unrelated diagnostic in `api/services/os_control_service.py`; I did not modify that file because it is outside Task 3 scope.

## Review Fix: Agno Eval Raw Rows

### Fix details

- Updated `normalize_agno_eval_run()` to read real Agno `EvalRunRecord.eval_data` payloads and fall back to legacy/raw `data` dicts.
- Normalized enum-like `eval_type` values to stable lower-case strings, including installed Agno `EvalType.ACCURACY` -> `accuracy`.
- Updated list and detail DB calls to pass `deserialize=False`, preserving raw row shape and accurate `(rows, total)` tuple totals from `AsyncPostgresDb.get_eval_runs()`.

### RED evidence

Command:

```bash
uv run pytest api/tests/test_agent_eval_result_service.py api/tests/test_postgres_sql_templates.py::test_agent_eval_result_service_uses_agno_async_api_only -q
```

Output summary:

```text
3 failed, 5 passed in 6.98s
```

Expected failures:

- `get_eval_runs()` did not receive `deserialize=False`.
- `get_eval_run()` did not receive `deserialize=False`.
- Real Agno `EvalRunRecord(eval_data=..., eval_type=EvalType.ACCURACY)` normalized `data` as `{}` instead of the eval payload.

### Verification

- `uv run pytest api/tests/test_agent_eval_result_service.py api/tests/test_postgres_sql_templates.py::test_agent_eval_result_service_uses_agno_async_api_only -q`
  - Result: PASS, `8 passed in 7.06s`
- `uv run ruff check .`
  - Result: PASS, `All checks passed!`
- `uv run ty check .`
  - Result: FAIL with unrelated diagnostics outside Task 3 owned files:
    - `api/services/os_control_service.py:490`: `_record(status=...)` expected `str`, found `str | int`.
    - `api/tests/test_os_control_permissions.py:155`: `delete_os_memory(request=None, ...)` expected `Request[State]`, found `None`.
    - `api/tests/test_os_control_permissions.py:181`: `delete_os_memory(request=None, ...)` expected `Request[State]`, found `None`.
    - `api/tests/test_os_control_permissions.py:208`: `prune_os_memory(request=None, ...)` expected `Request[State]`, found `None`.
