# Task 5 Report: Agent Evals API Routes

## Status

Complete.

## Scope

Implemented Agent Evals route models and handlers in `api/routes/agent_evals.py`, included the router in `api/main.py`, and added focused route/static include tests.

## Endpoints

- `GET /api/agent-evals/suites`
- `POST /api/agent-evals/suites`
- `GET /api/agent-evals/suites/{suite_id}`
- `PATCH /api/agent-evals/suites/{suite_id}`
- `GET /api/agent-evals/cases`
- `POST /api/agent-evals/cases`
- `GET /api/agent-evals/cases/{case_id}`
- `PATCH /api/agent-evals/cases/{case_id}`
- `GET /api/agent-evals/suites/{suite_id}/runs`
- `POST /api/agent-evals/suites/{suite_id}/runs`
- `GET /api/agent-evals/cases/{case_id}/runs`
- `POST /api/agent-evals/cases/{case_id}/runs`
- `POST /api/agent-evals/case-runs/{case_run_id}/replay`
- `GET /api/agent-evals/agno-runs`
- `GET /api/agent-evals/agno-runs/{eval_run_id}`
- `GET /api/agent-evals/trends`
- `GET /api/agent-evals/failures`

## TDD Evidence

RED:

```text
uv run pytest api/tests/test_agent_eval_routes.py -q
ERROR api/tests/test_agent_eval_routes.py
ImportError: cannot import name 'agent_evals' from 'api.routes'
```

```text
uv run pytest api/tests/test_postgres_sql_templates.py::test_agent_evals_router_is_included -q
FAILED api/tests/test_postgres_sql_templates.py::test_agent_evals_router_is_included
assert 'agent_evals' in main_source
```

GREEN:

```text
uv run pytest api/tests/test_agent_eval_routes.py -q
6 passed in 6.43s
```

```text
uv run pytest api/tests/test_postgres_sql_templates.py::test_agent_evals_router_is_included -q
1 passed in 8.51s
```

## Verification

```text
uv run ruff check .
All checks passed!
```

```text
uv run ty check .
All checks passed!
```

## Notes

- Read/write/run permissions use dependency wrappers over the existing permission helpers.
- Service `ValueError` is mapped to route-level 4xx responses: not found to 404, disabled to 409, other validation failures to 422.
- Pydantic request models reject unsupported eval types and threshold values outside `1..10`.
- No files outside the Task 5 ownership list were changed.
