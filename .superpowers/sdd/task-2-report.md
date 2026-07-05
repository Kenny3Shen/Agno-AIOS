# Task 2 Report: Replace Static Guards That Protected Local AsyncPgVector

## Summary

Removed the last production dependency on `api.services.async_pgvector.AsyncPgVector` by deleting the adapter module and removing its shutdown hook from `api/main.py`. The runtime path now stays on the Agno `PgVector` contract only.

## Commands Run

1. `uv run pytest api/tests/test_postgres_sql_templates.py::test_knowledge_runtime_uses_agno_pgvector_contract`
   - Result: passed
2. `rg -n "AsyncPgVector|async_pgvector" api docs`
   - Result: production references were removed; remaining hits are in historical docs, task docs, and the test assertion that checks the Agno contract.
3. `uv run pytest api/tests/test_postgres_sql_templates.py api/tests/test_knowledge_pipeline.py`
   - Result: `48 passed`
4. `uv run ruff check .`
   - Result: passed
5. `uv run ty check .`
   - Result: passed

## Files Changed

- `api/main.py`
  - Removed `dispose_async_pgvector_engines` import.
  - Removed the lifespan shutdown call to that cleanup helper.
- `api/services/async_pgvector.py`
  - Deleted the file with `git rm`.

## Reference Classification

- Production code:
  - `api/main.py` was the only remaining production import path and was cleaned up.
- Test code:
  - `api/tests/test_postgres_sql_templates.py` already contained the Task 2 contract assertions and did not need further churn.
- Historical / documentation:
  - `docs/database-tables.md`
  - `docs/architecture.md`
  - `docs/adr/0008-sqlalchemy-for-control-plane-data.md`
  - `docs/superpowers/specs/2026-07-05-agno-async-api-contract-design.md`
  - `docs/superpowers/plans/2026-07-05-agno-async-api-contract-migration.md`

## Self-Review

- Verified the runtime source now imports `PgVector` and constructs `vector_db = PgVector(...)`.
- Verified `AsyncPgVector` no longer appears in production source.
- Verified the removed shutdown helper was not referenced elsewhere in `api/`.
- Verified the targeted contract test and the broader knowledge pipeline tests pass.
- Verified repo-wide lint and type checks pass.

## Concerns

- Historical docs still describe the retired adapter. That is consistent with the task brief, but those pages now intentionally preserve old-state context rather than current implementation guidance.
- Two unrelated untracked image files were left untouched as requested.
