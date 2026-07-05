# Task 3 Report: Lock Knowledge Lifecycle To Agno Async Methods

## Scope

- Added contract-style tests for `KnowledgeBaseLifecycle` in `api/tests/test_knowledge_pipeline.py`.
- Tightened the static source guard in `api/tests/test_postgres_sql_templates.py`.
- No implementation change was needed in `api/services/knowledge_service.py`; the lifecycle already uses Agno async methods.

## TDD Evidence

### Initial focused run

Command:

```bash
uv run pytest api/tests/test_knowledge_pipeline.py api/tests/test_postgres_sql_templates.py::test_knowledge_async_lifecycle_uses_agno_async_api
```

Result:

- 2 tests failed in `api/tests/test_knowledge_pipeline.py`.
- Failure cause was my first draft of the search contract asserting a hard-coded `max_results=5`, while the real runtime path computed `max_results=15` from rerank policy.

### Fix applied

- Reworked the search assertions to capture the actual `max_results` passed into `asearch`.
- Kept the guard focused on the async Agno surface:
  - `ainsert` for text/file ingestion
  - `asearch` for search
  - `aget_content` for list/reload paths
  - `aget_content_by_id` for delete
  - sync methods raise if touched

### Green run

Command:

```bash
uv run pytest api/tests/test_knowledge_pipeline.py api/tests/test_postgres_sql_templates.py::test_knowledge_async_lifecycle_uses_agno_async_api
```

Result:

- `23 passed`

### Static checks

Commands:

```bash
uv run ruff check api/tests/test_knowledge_pipeline.py api/tests/test_postgres_sql_templates.py
uv run ty check api/tests/test_knowledge_pipeline.py api/tests/test_postgres_sql_templates.py
```

Result:

- Both passed.

## Files Changed

- `api/tests/test_knowledge_pipeline.py`
- `api/tests/test_postgres_sql_templates.py`
- `.superpowers/sdd/task-3-report.md`

## Self-Review

- The new contract tests fail if lifecycle code falls back to sync Agno methods, because the fake knowledge object raises on `insert`, `search`, `load`, `get_content`, `get_content_by_id`, `remove_content_by_id`, and `remove_all_content`.
- The static assertions only target sync method spellings, so they do not collide with async names like `aget_content`.
- I did not touch unrelated workspace changes, including the existing frontend edits and untracked screenshot files.

## Concerns

- None for this task. The only transient issue was the initial overly strict `max_results` expectation, which is now derived from the actual call.
