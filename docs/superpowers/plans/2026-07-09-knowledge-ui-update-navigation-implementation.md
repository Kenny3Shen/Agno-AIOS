# Knowledge UI Update Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the confirmed方案 1: a document-first Knowledge workbench, unified Add/Update Drawer with per-request ingest options, document-level incremental replacement cleanup, and a tighter sidebar with Memory below Trace.

**Architecture:** Backend changes extend the existing Knowledge lifecycle instead of adding a versioned document model. Frontend changes keep `Knowledge.vue` as the page orchestrator and split the document list, metadata panel, ingest Drawer, and retrieval playground into focused components. Navigation remains controlled by existing shell layout helpers and stored `NAV_TAGS` behavior.

**Tech Stack:** FastAPI, Pydantic, Agno Knowledge, Agno AsyncPostgresDb, PgVector, Async SQLAlchemy Core, pytest, ruff, ty, Vue 3, Element Plus, Pinia auth store, vue-i18n, Bun tests, Playwright.

## Global Constraints

- Development environment is WSL2 Ubuntu 24.04.
- Python commands must use `uv`; run Python files with `uv run python`.
- Use `uv run ruff check <file_name>` after phase-level backend work.
- Use `uv run ty check <file_name>` after phase-level backend work.
- Start pre-prod with `uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8001` before browser verification.
- Backend verification must include relevant `uv run pytest ...`.
- Frontend verification must include `cd frontend && bun run test:shell`, `cd frontend && bun run test:auth`, and `cd frontend && bun run build`.
- Browser verification must use Playwright at 1920x1080 and capture screenshots for Knowledge page, Drawer, and navigation.
- If `frontend/package.json` changes, use `bun install/add/remove <package>`.
- Do not implement the Trace session detail gap in this phase.
- Do not force stable Knowledge doc IDs across updates; updates may return a new doc ID.
- Per-request ingest options must not mutate global RAG settings.
- Existing user-customized `NAV_TAGS` layouts must remain respected.
- Preserve unrelated dirty files and untracked screenshots.

---

## Scope Check

The approved spec contains one cohesive phase with three dependent surfaces: Knowledge backend update semantics, Knowledge frontend UI, and sidebar default layout. Trace session detail debugging was moved out of scope, so this plan stays within one implementation plan.

## File Structure

Create:

- `frontend/src/modules/knowledgeWorkbench.ts`: pure helpers for document selection, display labels, ingest default payloads, and update merge behavior.
- `frontend/src/modules/knowledgeWorkbench.test.mjs`: unit tests for those pure helpers.
- `frontend/src/components/knowledge/KnowledgeDocumentList.vue`: document list, filters, refresh/clear controls, visibility control, and row actions.
- `frontend/src/components/knowledge/KnowledgeMetadataPanel.vue`: selected document summary and metadata JSON viewer.
- `frontend/src/components/knowledge/KnowledgeIngestDrawer.vue`: Add/Update Drawer with file/text/path modes, collapsed per-request advanced options, and ingest pipeline state.
- `frontend/src/components/knowledge/KnowledgeRetrievalPlayground.vue`: retrieval query controls and results.

Modify:

- `api/persistence/knowledge_sources.py`: add source snapshot deletion.
- `api/services/knowledge_ingest_service.py`: add reader strategy lookup and per-request ingest option coercion helpers.
- `api/services/knowledge_service.py`: wire per-request ingest options into add/update flows and delete source snapshots with old content.
- `api/routes/knowledge.py`: add request model fields for ingest options and pass them to lifecycle methods.
- `api/tests/test_knowledge_lifecycle.py`: add backend lifecycle tests for ingest overrides and update cleanup.
- `api/tests/test_knowledge_ingest_runtime.py`: add reader strategy and option coercion tests.
- `api/tests/test_postgres_sql_templates.py`: adjust source snapshot hygiene guard if needed.
- `frontend/src/types/index.ts`: add `KnowledgeIngestOptions` and request fields.
- `frontend/src/composables/useKnowledgeApi.ts`: pass new request shapes unchanged.
- `frontend/src/components/Knowledge.vue`: become the page orchestrator using the new components.
- `frontend/src/i18n/locales/en-US.ts`: update Knowledge and Drawer copy.
- `frontend/src/i18n/locales/zh-CN.ts`: update Knowledge and Drawer copy.
- `frontend/src/modules/testSource.mjs`: expose new Knowledge component sources for shell tests.
- `frontend/src/modules/knowledgeSettingsSourceContracts.test.mjs`: replace old advanced/global RAG and source-replacement assertions with new component assertions.
- `frontend/src/modules/shellNavigation.test.mjs`: update default group expectations.
- `frontend/src/App.vue`: move Memory into Governance defaults after Trace.
- `frontend/src/components/Settings.vue`: update navigation settings defaults.
- `frontend/src/style.css`: tighten sidebar nav density.

---

### Task 1: Backend Per-Request Ingest Options

**Files:**
- Modify: `api/services/knowledge_ingest_service.py`
- Modify: `api/services/knowledge_service.py`
- Modify: `api/routes/knowledge.py`
- Modify: `api/tests/test_knowledge_ingest_runtime.py`
- Modify: `api/tests/test_knowledge_lifecycle.py`

**Interfaces:**
- Produces:
  - `KnowledgeIngestOverrides` dataclass in `api.services.knowledge_ingest_service`
  - `coerce_ingest_overrides(values: Mapping[str, object] | None) -> KnowledgeIngestOverrides`
  - `profile_for_strategy(strategy: str | None) -> KnowledgeIngestProfile | None`
  - `profile_for_filename_or_strategy(filename: str | None, strategy: str | None) -> KnowledgeIngestProfile`
  - `KnowledgeIngestOptionsRequest` Pydantic model in `api.routes.knowledge`
- Consumes:
  - Existing `KnowledgeReaderConfig`
  - Existing `knowledge_settings()`
  - Existing `reader_for_profile(...)`

- [ ] **Step 1: Add failing ingest runtime tests**

Append to `api/tests/test_knowledge_ingest_runtime.py`:

```python
from api.services.knowledge_ingest_service import (
    coerce_ingest_overrides,
    profile_for_filename_or_strategy,
    profile_for_strategy,
)


def test_profile_for_strategy_resolves_known_reader_strategy() -> None:
    profile = profile_for_strategy("csv_row")

    assert profile is not None
    assert profile.strategy == "csv_row"
    assert profile.reader == "CSVReader"


def test_profile_for_filename_or_strategy_prefers_explicit_strategy() -> None:
    profile = profile_for_filename_or_strategy("alerts.json", "code")

    assert profile.strategy == "code"
    assert profile.reader == "TextReader"


def test_coerce_ingest_overrides_normalizes_numeric_values() -> None:
    overrides = coerce_ingest_overrides(
        {
            "chunk_size": "1500",
            "chunk_overlap": 120,
            "code_chunk_size": "2200",
            "semantic_threshold": "0.61",
            "reader_strategy": "markdown",
        }
    )

    assert overrides.chunk_size == 1500
    assert overrides.chunk_overlap == 120
    assert overrides.code_chunk_size == 2200
    assert overrides.semantic_threshold == 0.61
    assert overrides.reader_strategy == "markdown"
```

Run:

```bash
uv run pytest api/tests/test_knowledge_ingest_runtime.py::test_profile_for_strategy_resolves_known_reader_strategy api/tests/test_knowledge_ingest_runtime.py::test_profile_for_filename_or_strategy_prefers_explicit_strategy api/tests/test_knowledge_ingest_runtime.py::test_coerce_ingest_overrides_normalizes_numeric_values -q
```

Expected: FAIL because the helper functions do not exist.

- [ ] **Step 2: Implement ingest option helpers**

Add to `api/services/knowledge_ingest_service.py` after `INGEST_PROFILES`:

```python
@dataclass(frozen=True)
class KnowledgeIngestOverrides:
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    code_chunk_size: int | None = None
    semantic_threshold: float | None = None
    reader_strategy: str | None = None


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def profile_for_strategy(strategy: str | None) -> KnowledgeIngestProfile | None:
    clean_strategy = (strategy or "").strip().lower()
    if not clean_strategy:
        return None
    for profile in INGEST_PROFILES:
        if profile.strategy == clean_strategy:
            return profile
    return None


def profile_for_filename_or_strategy(
    filename: str | None,
    strategy: str | None,
) -> KnowledgeIngestProfile:
    return profile_for_strategy(strategy) or profile_for_filename(filename)


def coerce_ingest_overrides(values: Mapping[str, object] | None) -> KnowledgeIngestOverrides:
    source = values or {}
    return KnowledgeIngestOverrides(
        chunk_size=_optional_int(source.get("chunk_size")),
        chunk_overlap=_optional_int(source.get("chunk_overlap")),
        code_chunk_size=_optional_int(source.get("code_chunk_size")),
        semantic_threshold=_optional_float(source.get("semantic_threshold")),
        reader_strategy=str(source.get("reader_strategy") or "").strip().lower() or None,
    )
```

Also add `Mapping` to the imports:

```python
from collections.abc import Mapping
```

Run the same pytest command from Step 1.

Expected: PASS.

- [ ] **Step 3: Add failing lifecycle metadata test**

Append to `api/tests/test_knowledge_lifecycle.py`:

```python
@pytest.mark.asyncio
async def test_add_text_document_records_per_request_ingest_options() -> None:
    content_row = SimpleNamespace(
        id="content-options",
        name="Runbook",
        metadata={"user_id": "u1", "source": "manual", "chunks": 1},
        created_at=0,
    )
    knowledge = StrictAsyncKnowledge(contents=[content_row])

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_storage_async=lambda: None,
            store_source_async=lambda _content_id, _source: None,
        )
    )

    result = await lifecycle.add_text_document_async(
        "Runbook",
        "body",
        owner_user_id="u1",
        ingest_options={
            "chunk_size": 1500,
            "chunk_overlap": 120,
            "code_chunk_size": 2200,
            "semantic_threshold": 0.61,
            "reader_strategy": "markdown",
        },
    )

    assert result["id"] == "content-options"
    insert_kwargs = knowledge.calls[0][2]
    assert insert_kwargs["metadata"]["chunk_size"] == "1500"
    assert insert_kwargs["metadata"]["chunk_overlap"] == "120"
    assert insert_kwargs["metadata"]["code_chunk_size"] == "2200"
    assert insert_kwargs["metadata"]["semantic_threshold"] == "0.61"
    assert insert_kwargs["metadata"]["chunk_strategy"] == "markdown"
    assert insert_kwargs["metadata"]["reader"] == "MarkdownReader"
```

Run:

```bash
uv run pytest api/tests/test_knowledge_lifecycle.py::test_add_text_document_records_per_request_ingest_options -q
```

Expected: FAIL because `add_text_document_async()` does not accept `ingest_options`.

- [ ] **Step 4: Wire options into Knowledge lifecycle**

Modify imports in `api/services/knowledge_service.py`:

```python
from api.services.knowledge_ingest_service import (
    PROFILE_CSV as _PROFILE_CSV,
    PROFILE_JSON as _PROFILE_JSON,
    PROFILE_MARKDOWN as _PROFILE_MARKDOWN,
    PROFILE_TEXT as _PROFILE_TEXT,
    SUPPORTED_FILE_SUFFIXES,
    KnowledgeIngestOverrides,
    KnowledgeIngestProfile,
    KnowledgeReader,
    KnowledgeReaderConfig,
    coerce_ingest_overrides as _coerce_ingest_overrides,
    profile_for_filename as _profile_for_filename,
    profile_for_filename_or_strategy as _profile_for_filename_or_strategy,
    reader_for_profile as _reader_for_profile,
)
```

Replace `_reader_config()` with:

```python
def _reader_config(
    needs_embedder: bool,
    overrides: KnowledgeIngestOverrides | None = None,
) -> KnowledgeReaderConfig:
    settings = knowledge_settings()
    options = overrides or KnowledgeIngestOverrides()
    chunk_size = options.chunk_size or settings.chunk_size
    chunk_overlap = options.chunk_overlap if options.chunk_overlap is not None else settings.chunk_overlap
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")
    return KnowledgeReaderConfig(
        embedder=_get_embedder() if needs_embedder else None,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        code_chunk_size=options.code_chunk_size or settings.code_chunk_size,
        semantic_threshold=options.semantic_threshold if options.semantic_threshold is not None else settings.semantic_threshold,
    )
```

Add helpers after `knowledge_profile_for_filename()`:

```python
def knowledge_profile_for_filename_or_strategy(
    filename: str | None,
    strategy: str | None,
) -> KnowledgeIngestProfile:
    return _profile_for_filename_or_strategy(filename, strategy)


def _metadata_ingest_options(overrides: KnowledgeIngestOverrides) -> dict[str, str]:
    metadata: dict[str, str] = {}
    if overrides.chunk_size is not None:
        metadata["chunk_size"] = str(overrides.chunk_size)
    if overrides.chunk_overlap is not None:
        metadata["chunk_overlap"] = str(overrides.chunk_overlap)
    if overrides.code_chunk_size is not None:
        metadata["code_chunk_size"] = str(overrides.code_chunk_size)
    if overrides.semantic_threshold is not None:
        metadata["semantic_threshold"] = str(overrides.semantic_threshold)
    if overrides.reader_strategy is not None:
        metadata["reader_strategy"] = overrides.reader_strategy
    return metadata
```

Replace `reader_for_profile(...)` with:

```python
def reader_for_profile(
    profile: KnowledgeIngestProfile,
    filename: str | None = None,
    overrides: KnowledgeIngestOverrides | None = None,
) -> KnowledgeReader:
    return _reader_for_profile(
        profile,
        _reader_config(
            needs_embedder=profile.strategy == "semantic",
            overrides=overrides,
        ),
        filename,
    )
```

Replace `reader_for_filename(...)` with:

```python
def reader_for_filename(
    filename: str | None,
    overrides: Mapping[str, object] | KnowledgeIngestOverrides | None = None,
) -> KnowledgeReader:
    ingest_overrides = (
        overrides
        if isinstance(overrides, KnowledgeIngestOverrides)
        else _coerce_ingest_overrides(overrides)
    )
    profile = knowledge_profile_for_filename_or_strategy(
        filename,
        ingest_overrides.reader_strategy,
    )
    return _reader_for_profile(
        profile,
        _reader_config(
            needs_embedder=profile.strategy == "semantic",
            overrides=ingest_overrides,
        ),
        filename,
    )
```

Update lifecycle method signatures:

```python
async def add_text_document_async(
    self,
    title: str,
    content: str,
    source: str = "manual",
    metadata: dict[str, Any] | None = None,
    owner_user_id: str | None = None,
    visibility: str = "private",
    ingest_options: Mapping[str, object] | None = None,
) -> KnowledgeDocumentPayload:
```

Inside `add_text_document_async()`, after `filename = ...`:

```python
ingest_overrides = _coerce_ingest_overrides(ingest_options)
profile = knowledge_profile_for_filename_or_strategy(
    filename,
    ingest_overrides.reader_strategy,
)
```

Include options metadata in `safe_metadata`:

```python
safe_metadata = {
    **base_metadata,
    **_metadata_ingest_options(ingest_overrides),
    **_owner_metadata(owner_user_id, normalized_visibility),
    "title": clean_title,
    "source": clean_source,
    "file_type": Path(filename).suffix.lower() or "text",
    "chunk_strategy": profile.strategy,
    "reader": profile.reader,
    "input_mode": base_metadata.get("input_mode", "manual"),
}
```

Call `reader_for_profile(profile, filename, ingest_overrides)`.

Repeat the same signature, profile selection, metadata option merge, and reader call pattern for `add_file_document_async()` and `replace_document_source_async()`.

Update module-level wrappers at the end of `api/services/knowledge_service.py` to accept and pass `ingest_options`.

Run:

```bash
uv run pytest api/tests/test_knowledge_lifecycle.py::test_add_text_document_records_per_request_ingest_options api/tests/test_knowledge_ingest_runtime.py::test_profile_for_filename_or_strategy_prefers_explicit_strategy -q
```

Expected: PASS.

- [ ] **Step 5: Add route request model fields**

Modify `api/routes/knowledge.py` by adding:

```python
class KnowledgeIngestOptionsRequest(BaseModel):
    chunk_size: int | None = Field(default=None, ge=200)
    chunk_overlap: int | None = Field(default=None, ge=0)
    code_chunk_size: int | None = Field(default=None, ge=256)
    semantic_threshold: float | None = Field(default=None, ge=0, le=1)
    reader_strategy: str | None = None
```

Add this field to `KnowledgeTextRequest`, `KnowledgeFileRequest`, and `KnowledgeSourceReplacementRequest`:

```python
ingest_options: KnowledgeIngestOptionsRequest | None = None
```

Pass the model dump to service calls:

```python
ingest_options=request.ingest_options.model_dump(exclude_none=True)
if request.ingest_options is not None
else None,
```

Run:

```bash
uv run pytest api/tests/test_knowledge_lifecycle.py::test_add_text_document_records_per_request_ingest_options -q
uv run ruff check api/routes/knowledge.py api/services/knowledge_service.py api/services/knowledge_ingest_service.py api/tests/test_knowledge_lifecycle.py api/tests/test_knowledge_ingest_runtime.py
uv run ty check api/routes/knowledge.py api/services/knowledge_service.py api/services/knowledge_ingest_service.py api/tests/test_knowledge_lifecycle.py api/tests/test_knowledge_ingest_runtime.py
```

Expected: all commands pass.

- [ ] **Step 6: Commit backend ingest options**

```bash
git add api/routes/knowledge.py api/services/knowledge_service.py api/services/knowledge_ingest_service.py api/tests/test_knowledge_lifecycle.py api/tests/test_knowledge_ingest_runtime.py
git commit -m "feat: add per-request knowledge ingest options"
```

---

### Task 2: Backend Incremental Replace Cleanup

**Files:**
- Modify: `api/persistence/knowledge_sources.py`
- Modify: `api/services/knowledge_service.py`
- Modify: `api/tests/test_knowledge_lifecycle.py`

**Interfaces:**
- Produces:
  - `delete_knowledge_source_async(content_id: str) -> None`
  - `KnowledgeBaseLifecycleDependencies.delete_source_async`
  - `KnowledgeBaseLifecycle._delete_source_async(content_id: str) -> None`
- Consumes:
  - Existing `_delete_content_async(knowledge, content_id)`
  - Existing source snapshot table helpers

- [ ] **Step 1: Add failing source deletion lifecycle test**

Update the existing `test_replace_document_source_uploads_new_version_and_deletes_old_content()` in `api/tests/test_knowledge_lifecycle.py` by adding:

```python
deleted_sources: list[str] = []

async def delete_source_async(content_id: str) -> None:
    deleted_sources.append(content_id)
```

Add `delete_source_async=delete_source_async` to `KnowledgeBaseLifecycleDependencies(...)`.

Add this assertion at the end:

```python
assert deleted_sources == ["content-old"]
```

Run:

```bash
uv run pytest api/tests/test_knowledge_lifecycle.py::test_replace_document_source_uploads_new_version_and_deletes_old_content -q
```

Expected: FAIL because the dependency does not exist and old source snapshots are not deleted.

- [ ] **Step 2: Implement source snapshot deletion**

Add to imports in `api/services/knowledge_service.py`:

```python
from api.persistence.knowledge_sources import (
    delete_knowledge_source_async as _delete_knowledge_source_async,
    get_knowledge_source_async as _get_knowledge_source_async,
    upsert_knowledge_source_async as _upsert_knowledge_source_async,
)
```

Add to `api/persistence/knowledge_sources.py`:

```python
async def delete_knowledge_source_async(content_id: str) -> None:
    await ensure_knowledge_sources_table_async()
    table = knowledge_sources_table()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(table.delete().where(table.c.content_id == content_id))
```

Extend `KnowledgeBaseLifecycleDependencies`:

```python
delete_source_async: Callable[[str], Any] | None = None
```

Add method to `KnowledgeBaseLifecycle`:

```python
async def _delete_source_async(self, content_id: str) -> None:
    if self.dependencies.delete_source_async is not None:
        result = self.dependencies.delete_source_async(content_id)
        if hasattr(result, "__await__"):
            await result
        return
    await _delete_knowledge_source_async(content_id)
```

Modify `_delete_content_async()` in `KnowledgeBaseLifecycle`:

```python
async def _delete_content_async(self, knowledge: Any, content_id: str) -> None:
    if self.dependencies.delete_content_async is not None:
        result = self.dependencies.delete_content_async(knowledge, content_id)
        if hasattr(result, "__await__"):
            await result
    else:
        await _delete_content_async(knowledge, content_id)
    await self._delete_source_async(content_id)
```

Run the pytest command from Step 1.

Expected: PASS.

- [ ] **Step 3: Add cleanup failure test**

Append to `api/tests/test_knowledge_lifecycle.py`:

```python
@pytest.mark.asyncio
async def test_replace_document_source_reports_old_cleanup_failure() -> None:
    old_row = SimpleNamespace(
        id="content-old",
        name="Runbook",
        description="upload:runbook.md",
        metadata={
            "user_id": "u1",
            "visibility": "private",
            "source": "upload:runbook.md",
            "title": "Runbook",
            "file_name": "runbook.md",
            "file_type": ".md",
            "_tais_source": {"kind": "text", "digest": "old", "version": 1},
        },
        created_at=0,
    )
    new_row = SimpleNamespace(
        id="content-new",
        name="Runbook",
        description="upload:runbook-v2.csv",
        metadata={
            "user_id": "u1",
            "visibility": "private",
            "source": "upload:runbook-v2.csv",
            "title": "Runbook",
            "file_name": "runbook-v2.csv",
            "file_type": ".csv",
        },
        created_at=1,
    )
    knowledge = StrictAsyncKnowledge(
        contents=[new_row],
        content_by_id={"content-old": old_row, "content-new": new_row},
    )

    async def content_by_id(content_id: str):
        return knowledge._content_by_id.get(content_id)

    async def delete_content_async(_knowledge, content_id: str) -> None:
        assert content_id == "content-old"
        raise RuntimeError("old cleanup failed")

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_contents_storage_async=lambda: None,
            ensure_storage_async=lambda: None,
            knowledge_content_by_id_async=content_by_id,
            delete_content_async=delete_content_async,
            store_source_async=lambda _content_id, _source: None,
        )
    )

    with (
        patch.object(knowledge_service, "reader_for_profile", return_value=object()),
        pytest.raises(RuntimeError, match="old cleanup failed"),
    ):
        await lifecycle.replace_document_source_async(
            "content-old",
            content="col\nvalue\n",
            file_name="runbook-v2.csv",
            user=SimpleNamespace(id="u1", role="user", is_superuser=False),
        )
```

Run:

```bash
uv run pytest api/tests/test_knowledge_lifecycle.py::test_replace_document_source_reports_old_cleanup_failure -q
```

Expected: PASS after Step 2 because cleanup errors propagate.

- [ ] **Step 4: Add cross-type metadata test**

Append to `api/tests/test_knowledge_lifecycle.py`:

```python
@pytest.mark.asyncio
async def test_replace_document_source_cross_type_uses_new_reader_profile() -> None:
    old_row = SimpleNamespace(
        id="content-old-json",
        name="Asset Policy",
        description="upload:policy.json",
        metadata={
            "user_id": "u1",
            "visibility": "private",
            "source": "upload:policy.json",
            "title": "Asset Policy",
            "file_name": "policy.json",
            "file_type": ".json",
        },
        created_at=0,
    )
    new_row = SimpleNamespace(
        id="content-new-js",
        name="Asset Policy",
        description="upload:policy.js",
        metadata={"user_id": "u1", "source": "upload:policy.js"},
        created_at=1,
    )
    knowledge = StrictAsyncKnowledge(
        contents=[new_row],
        content_by_id={"content-old-json": old_row, "content-new-js": new_row},
    )

    async def content_by_id(content_id: str):
        return knowledge._content_by_id.get(content_id)

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: knowledge,
            ensure_contents_storage_async=lambda: None,
            ensure_storage_async=lambda: None,
            knowledge_content_by_id_async=content_by_id,
            delete_content_async=lambda _knowledge, _content_id: None,
            delete_source_async=lambda _content_id: None,
            store_source_async=lambda _content_id, _source: None,
        )
    )

    with patch.object(knowledge_service, "reader_for_profile", return_value=object()):
        result = await lifecycle.replace_document_source_async(
            "content-old-json",
            content="console.log('policy')",
            file_name="policy.js",
            source="upload:policy.js",
            user=SimpleNamespace(id="u1", role="user", is_superuser=False),
        )

    assert result is not None
    insert_kwargs = knowledge.calls[0][2]
    assert insert_kwargs["metadata"]["file_name"] == "policy.js"
    assert insert_kwargs["metadata"]["file_type"] == ".js"
    assert insert_kwargs["metadata"]["chunk_strategy"] == "code"
    assert insert_kwargs["metadata"]["reader"] == "TextReader"
```

Run:

```bash
uv run pytest api/tests/test_knowledge_lifecycle.py::test_replace_document_source_cross_type_uses_new_reader_profile -q
```

Expected: PASS.

- [ ] **Step 5: Run backend cleanup gates**

```bash
uv run pytest api/tests/test_knowledge_lifecycle.py api/tests/test_knowledge_ingest_runtime.py -q
uv run ruff check api/persistence/knowledge_sources.py api/services/knowledge_service.py api/services/knowledge_ingest_service.py api/routes/knowledge.py api/tests/test_knowledge_lifecycle.py api/tests/test_knowledge_ingest_runtime.py
uv run ty check api/persistence/knowledge_sources.py api/services/knowledge_service.py api/services/knowledge_ingest_service.py api/routes/knowledge.py api/tests/test_knowledge_lifecycle.py api/tests/test_knowledge_ingest_runtime.py
```

Expected: all commands pass.

- [ ] **Step 6: Commit backend cleanup**

```bash
git add api/persistence/knowledge_sources.py api/services/knowledge_service.py api/tests/test_knowledge_lifecycle.py
git commit -m "fix: clean knowledge source snapshots on replacement"
```

---

### Task 3: Frontend Types And Pure Knowledge Workbench Helpers

**Files:**
- Create: `frontend/src/modules/knowledgeWorkbench.ts`
- Create: `frontend/src/modules/knowledgeWorkbench.test.mjs`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/uiShell.test.mjs`

**Interfaces:**
- Produces:
  - `KnowledgeIngestOptions` interface.
  - `createDefaultKnowledgeIngestOptions(status?: KnowledgeStatus | null): KnowledgeIngestOptions`
  - `mergeUpdatedKnowledgeDocument(documents: KnowledgeDocument[], oldId: string | null, updated: KnowledgeDocument): KnowledgeDocument[]`
  - `resolveSelectedKnowledgeDocumentId(documents: KnowledgeDocument[], selectedId: string | null): string`
  - `knowledgeDocumentType(doc: KnowledgeDocument): string`
  - `knowledgeDocumentStatus(doc: KnowledgeDocument): { labelKey: string; value: "ready" | "parsing" | "failed"; tone: string }`
- Consumes:
  - Existing frontend `KnowledgeDocument` and `KnowledgeStatus` types.

- [ ] **Step 1: Add failing helper tests**

Create `frontend/src/modules/knowledgeWorkbench.test.mjs`:

```javascript
import assert from "node:assert/strict"
import {
  createDefaultKnowledgeIngestOptions,
  knowledgeDocumentStatus,
  knowledgeDocumentType,
  mergeUpdatedKnowledgeDocument,
  resolveSelectedKnowledgeDocumentId,
} from "./knowledgeWorkbench.ts"

const docs = [
  { id: "doc-a", title: "a.md", source: "upload:a.md", chunks: 2, created_at: "", metadata: { file_type: ".md" } },
  { id: "doc-b", title: "b.csv", source: "upload:b.csv", chunks: 0, created_at: "", metadata: { file_name: "b.csv" } },
]

assert.equal(
  resolveSelectedKnowledgeDocumentId(docs, null),
  "doc-a",
  "selection should default to first document",
)

assert.equal(
  resolveSelectedKnowledgeDocumentId(docs, "doc-b"),
  "doc-b",
  "selection should keep an existing selected document",
)

assert.equal(
  resolveSelectedKnowledgeDocumentId([docs[0]], "doc-b"),
  "doc-a",
  "selection should recover when filtering hides the selected document",
)

assert.deepEqual(
  mergeUpdatedKnowledgeDocument(docs, "doc-a", { ...docs[0], id: "doc-new", title: "new.js" }).map((doc) => doc.id),
  ["doc-new", "doc-b"],
  "updated documents should replace old id and select returned id",
)

assert.equal(
  knowledgeDocumentType({ ...docs[1], type: "" }),
  "CSV",
  "document type should fall back to file metadata",
)

assert.deepEqual(
  knowledgeDocumentStatus({ ...docs[0], status: "completed" }),
  { labelKey: "knowledge.status.ready", value: "ready", tone: "ready" },
  "completed documents should display as ready",
)

assert.deepEqual(
  createDefaultKnowledgeIngestOptions({
    chunk_size: 1200,
    chunk_overlap: 160,
    code_chunk_size: 1800,
    semantic_threshold: 0.52,
  }),
  {
    chunk_size: 1200,
    chunk_overlap: 160,
    code_chunk_size: 1800,
    semantic_threshold: 0.52,
    reader_strategy: "auto",
  },
  "default ingest options should mirror status defaults",
)
```

Modify `frontend/src/uiShell.test.mjs`:

```javascript
import "./modules/knowledgeWorkbench.test.mjs"
```

Run:

```bash
cd frontend && bun run test:shell
```

Expected: FAIL because `knowledgeWorkbench.ts` does not exist.

- [ ] **Step 2: Add frontend types**

Modify `frontend/src/types/index.ts`:

```typescript
export interface KnowledgeIngestOptions {
  chunk_size?: number | null
  chunk_overlap?: number | null
  code_chunk_size?: number | null
  semantic_threshold?: number | null
  reader_strategy?: string | null
}
```

Add `ingest_options?: KnowledgeIngestOptions | null` to:

```typescript
export interface KnowledgeTextRequest {
  title: string
  content: string
  source?: string
  metadata?: Record<string, string>
  visibility?: ResourceVisibility
  ingest_options?: KnowledgeIngestOptions | null
}

export interface KnowledgeFileRequest {
  path: string
  title?: string | null
  visibility?: ResourceVisibility
  ingest_options?: KnowledgeIngestOptions | null
}

export interface KnowledgeSourceReplacementRequest {
  content: string
  file_name: string
  title?: string | null
  source?: string | null
  metadata?: Record<string, string>
  ingest_options?: KnowledgeIngestOptions | null
}
```

- [ ] **Step 3: Implement pure helper module**

Create `frontend/src/modules/knowledgeWorkbench.ts`:

```typescript
import type { KnowledgeDocument, KnowledgeIngestOptions, KnowledgeStatus } from "../types"

const metadataValue = (doc: KnowledgeDocument, ...keys: string[]) => {
  for (const key of keys) {
    const value = doc.metadata?.[key]
    if (value) return value
  }
  return ""
}

export const createDefaultKnowledgeIngestOptions = (
  status?: Pick<KnowledgeStatus, "chunk_size" | "chunk_overlap" | "code_chunk_size" | "semantic_threshold"> | null,
): KnowledgeIngestOptions => ({
  chunk_size: status?.chunk_size ?? null,
  chunk_overlap: status?.chunk_overlap ?? null,
  code_chunk_size: status?.code_chunk_size ?? null,
  semantic_threshold: status?.semantic_threshold ?? null,
  reader_strategy: "auto",
})

export const resolveSelectedKnowledgeDocumentId = (
  documents: KnowledgeDocument[],
  selectedId: string | null,
) => {
  if (selectedId && documents.some((doc) => doc.id === selectedId)) return selectedId
  return documents[0]?.id || ""
}

export const mergeUpdatedKnowledgeDocument = (
  documents: KnowledgeDocument[],
  oldId: string | null,
  updated: KnowledgeDocument,
) => {
  const withoutOld = documents.filter((doc) => doc.id !== oldId && doc.id !== updated.id)
  return [updated, ...withoutOld]
}

export const knowledgeDocumentType = (doc: KnowledgeDocument) => {
  const metaType = String(doc.type || metadataValue(doc, "file_type", "mime_type") || "")
  if (metaType) return metaType.replace(/^\./, "").toUpperCase()
  const text = `${doc.title} ${doc.source} ${metadataValue(doc, "file_name")}`
  const suffix = text.match(/\.([a-z0-9]+)(?:\s|$)/i)?.[1]
  return (suffix || "TEXT").toUpperCase()
}

export const knowledgeDocumentSize = (doc: KnowledgeDocument) => {
  const size = Number(doc.size ?? metadataValue(doc, "file_size"))
  if (!Number.isFinite(size) || size <= 0) return "-"
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

export const knowledgeDocumentStatus = (doc: KnowledgeDocument) => {
  const raw = String(doc.status || metadataValue(doc, "status", "embedding_status")).toLowerCase()
  if (raw.includes("fail") || raw.includes("error")) {
    return { labelKey: "knowledge.status.failed", value: "failed" as const, tone: "failed" }
  }
  if (["completed", "complete", "ready", "done", "success", "succeeded"].some((item) => raw.includes(item))) {
    return { labelKey: "knowledge.status.ready", value: "ready" as const, tone: "ready" }
  }
  if (Number(doc.chunks || 0) > 0) {
    return { labelKey: "knowledge.status.ready", value: "ready" as const, tone: "ready" }
  }
  return { labelKey: "knowledge.status.parsing", value: "parsing" as const, tone: "parsing" }
}
```

Run:

```bash
cd frontend && bun run test:shell
```

Expected: PASS for `knowledgeWorkbench.test.mjs`. Existing tests may still fail later because old Knowledge source-contract assertions have not yet been updated.

- [ ] **Step 4: Commit frontend helper foundation**

```bash
git add frontend/src/types/index.ts frontend/src/modules/knowledgeWorkbench.ts frontend/src/modules/knowledgeWorkbench.test.mjs frontend/src/uiShell.test.mjs
git commit -m "feat: add knowledge workbench helpers"
```

---

### Task 4: Knowledge UI Component Split And Drawer Flow

**Files:**
- Create: `frontend/src/components/knowledge/KnowledgeDocumentList.vue`
- Create: `frontend/src/components/knowledge/KnowledgeMetadataPanel.vue`
- Create: `frontend/src/components/knowledge/KnowledgeIngestDrawer.vue`
- Create: `frontend/src/components/knowledge/KnowledgeRetrievalPlayground.vue`
- Modify: `frontend/src/components/Knowledge.vue`
- Modify: `frontend/src/composables/useKnowledgeApi.ts`
- Modify: `frontend/src/i18n/locales/en-US.ts`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/modules/testSource.mjs`
- Modify: `frontend/src/modules/knowledgeSettingsSourceContracts.test.mjs`

**Interfaces:**
- Consumes:
  - `KnowledgeDocument`
  - `KnowledgeStatus`
  - `KnowledgeIngestOptions`
  - `createDefaultKnowledgeIngestOptions(...)`
  - `mergeUpdatedKnowledgeDocument(...)`
  - `resolveSelectedKnowledgeDocumentId(...)`
- Produces:
  - Document-first Knowledge page with `.knowledge-document-workbench`
  - Shared `.knowledge-ingest-drawer`
  - `.knowledge-metadata-panel`
  - `.retrieval-playground`

- [ ] **Step 1: Update source-contract tests first**

Modify `frontend/src/modules/testSource.mjs`:

```javascript
export const knowledgeDocumentList = readOptionalSource("components/knowledge/KnowledgeDocumentList.vue")
export const knowledgeMetadataPanel = readOptionalSource("components/knowledge/KnowledgeMetadataPanel.vue")
export const knowledgeIngestDrawer = readOptionalSource("components/knowledge/KnowledgeIngestDrawer.vue")
export const knowledgeRetrievalPlayground = readOptionalSource("components/knowledge/KnowledgeRetrievalPlayground.vue")
export const knowledgeWorkbenchSource = readOptionalSource("modules/knowledgeWorkbench.ts")
```

Modify imports in `frontend/src/modules/knowledgeSettingsSourceContracts.test.mjs` to include:

```javascript
  knowledgeDocumentList,
  knowledgeIngestDrawer,
  knowledgeMetadataPanel,
  knowledgeRetrievalPlayground,
  knowledgeWorkbenchSource,
```

Replace the old Knowledge assertions from `advanced-configuration` through `source-replacement-dialog` with:

```javascript
assert.match(
  knowledge,
  /knowledge-document-workbench/,
  "Knowledge page must use the document-first workbench shell",
)

assert.match(
  knowledge,
  /KnowledgeDocumentList/,
  "Knowledge page must delegate document list rendering",
)

assert.match(
  knowledge,
  /KnowledgeMetadataPanel/,
  "Knowledge page must delegate selected metadata rendering",
)

assert.match(
  knowledge,
  /KnowledgeIngestDrawer/,
  "Knowledge page must use the shared Add and Update Drawer",
)

assert.match(
  knowledgeRetrievalPlayground,
  /retrieval-playground/,
  "Knowledge retrieval playground must remain available",
)

assert.match(
  knowledgeIngestDrawer,
  /knowledge-ingest-drawer/,
  "Knowledge Add and Update must share one Drawer surface",
)

assert.match(
  knowledgeIngestDrawer,
  /advancedIngestOpen/,
  "Knowledge Drawer advanced ingest options must be collapsed by local state",
)

assert.match(
  knowledgeIngestDrawer,
  /ingest_options/,
  "Knowledge Drawer must send per-request ingest options",
)

assert.doesNotMatch(
  knowledge,
  /advanced-configuration/,
  "Knowledge page must not keep global RAG editing in the bottom page area",
)

assert.doesNotMatch(
  knowledge,
  /metadataDialogOpen|sourceReplacementDialogOpen|source-replacement-dialog/,
  "Knowledge page must replace metadata and source replacement dialogs with the new panel and Drawer",
)

assert.match(
  knowledgeMetadataPanel,
  /knowledge-metadata-panel/,
  "Knowledge metadata panel must render selected document metadata",
)

assert.match(
  knowledgeWorkbenchSource,
  /mergeUpdatedKnowledgeDocument/,
  "Knowledge update flow must merge returned new document IDs through a pure helper",
)
```

Run:

```bash
cd frontend && bun run test:shell
```

Expected: FAIL because the new components do not exist and `Knowledge.vue` still contains old global advanced configuration.

- [ ] **Step 2: Add i18n keys**

Add these keys under `knowledge` in both locale files. English:

```typescript
workbench: {
  documents: "Documents",
  metadata: "Metadata",
  addDocument: "Add document",
  updateDocument: "Update",
  selectedMetadata: "Selected document metadata",
  noSelection: "Select a document to inspect metadata",
},
drawer: {
  addTitle: "Add knowledge document",
  updateTitle: "Update knowledge document",
  advancedIngest: "Advanced ingest options",
  advancedIngestHint: "Collapsed by default. Overrides apply only to this request.",
  readerStrategy: "Reader strategy",
  automaticReader: "Automatic",
  chunkSize: "Chunk size",
  chunkOverlap: "Chunk overlap",
  codeChunkSize: "Code chunk size",
  semanticThreshold: "Semantic threshold",
  updateTarget: "Updating",
},
```

Chinese:

```typescript
workbench: {
  documents: "文档",
  metadata: "Metadata",
  addDocument: "新增文档",
  updateDocument: "更新",
  selectedMetadata: "选中文档 Metadata",
  noSelection: "选择文档后查看 Metadata",
},
drawer: {
  addTitle: "新增知识文档",
  updateTitle: "更新知识文档",
  advancedIngest: "高级摄取参数",
  advancedIngestHint: "默认折叠，仅影响本次新增或更新。",
  readerStrategy: "Reader 策略",
  automaticReader: "自动识别",
  chunkSize: "Chunk Size",
  chunkOverlap: "Chunk Overlap",
  codeChunkSize: "Code Chunk Size",
  semanticThreshold: "Semantic Threshold",
  updateTarget: "正在更新",
},
```

- [ ] **Step 3: Create `KnowledgeDocumentList.vue`**

Create `frontend/src/components/knowledge/KnowledgeDocumentList.vue` with:

```vue
<template>
  <section class="knowledge-document-list">
    <div class="document-management-bar">
      <div class="document-management-title">
        <h4>{{ t("knowledge.workbench.documents") }}</h4>
        <span>{{ t("knowledge.documents.visibleCount", { count: filteredDocuments.length, total: documents.length }) }}</span>
      </div>
      <div class="document-management-controls">
        <div class="document-command-group">
          <el-tooltip :content="t('shell.actions.refresh')" placement="top">
            <el-button size="small" class="cursor-pointer" :loading="loading" @click="$emit('refresh')">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip :content="t('knowledge.actions.clear')" placement="top">
            <el-button type="danger" plain size="small" class="cursor-pointer" :disabled="documents.length === 0" :loading="clearing" @click="$emit('clear')">
              <el-icon><Delete /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip :content="t('knowledge.workbench.addDocument')" placement="top">
            <el-button type="primary" size="small" class="cursor-pointer" @click="$emit('add')">
              <el-icon><DocumentAdd /></el-icon>
            </el-button>
          </el-tooltip>
        </div>
        <el-input v-model="query" class="document-filter" :placeholder="t('knowledge.documents.searchPlaceholder')" clearable>
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </div>
    </div>

    <div v-if="loading && documents.length === 0" class="document-loading">
      <el-icon class="is-loading"><Loading /></el-icon>
      {{ t("knowledge.documents.loading") }}
    </div>

    <div v-else class="document-table document-list-compact" role="table" :aria-label="t('knowledge.documents.ariaLabel')">
      <div class="document-table-head" role="row">
        <span role="columnheader">{{ t("knowledge.documents.columns.name") }}</span>
        <span role="columnheader">{{ t("knowledge.documents.columns.embeddingStatus") }}</span>
        <span role="columnheader">{{ t("knowledge.documents.columns.visibility") }}</span>
        <span role="columnheader">{{ t("knowledge.documents.columns.actions") }}</span>
      </div>

      <div v-if="filteredDocuments.length === 0" class="empty-box">{{ t("knowledge.documents.empty") }}</div>

      <article
        v-for="row in filteredDocuments"
        :key="row.id"
        class="document-row"
        :class="{ selected: row.id === selectedDocumentId }"
        role="row"
        @click="$emit('select', row.id)"
      >
        <div class="document-cell document-main" role="cell">
          <span class="doc-title" :title="row.title">{{ row.title }}</span>
          <em>{{ documentType(row) }} · {{ row.chunks }} chunks</em>
        </div>
        <div class="document-cell" role="cell" :data-label="t('knowledge.documents.columns.embeddingStatus')">
          <span class="status-badge" :class="documentStatus(row).tone">{{ t(documentStatus(row).labelKey) }}</span>
        </div>
        <div class="document-cell document-visibility-cell" role="cell" :data-label="t('knowledge.documents.columns.visibility')">
          <ResourceVisibilityTabs
            :model-value="row.visibility || 'private'"
            class="document-visibility-tabs"
            :disabled="!row.can_manage"
            :aria-label="t('knowledge.documents.visibilityLabel', { title: row.title })"
            @click.stop
            @update:model-value="(value) => $emit('visibility', row, value)"
          />
        </div>
        <div class="document-actions" role="cell" :data-label="t('knowledge.documents.columns.actions')" @click.stop>
          <div class="document-action-buttons">
            <el-tooltip :content="t('knowledge.documents.preview')" placement="top">
              <el-button text class="cursor-pointer" :aria-label="t('knowledge.documents.previewLabel', { title: row.title })" @click="$emit('preview', row)">
                <el-icon><View /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip :content="t('knowledge.workbench.updateDocument')" placement="top">
              <el-button text class="cursor-pointer" :disabled="!row.can_manage || updatingDocId === row.id" :loading="updatingDocId === row.id" :aria-label="t('knowledge.documents.replaceSourceLabel', { title: row.title })" @click="$emit('update', row)">
                <el-icon><UploadFilled /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip :content="t('knowledge.documents.rebuild')" placement="top">
              <el-button text class="cursor-pointer" :disabled="!row.can_manage || rebuildingDocId === row.id" :loading="rebuildingDocId === row.id" :aria-label="t('knowledge.documents.reEmbeddingLabel', { title: row.title })" @click="$emit('rebuild', row)">
                <el-icon><RefreshRight /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip :content="t('knowledge.documents.delete')" placement="top">
              <el-button type="danger" text class="cursor-pointer" :loading="deletingDocId === row.id" :aria-label="t('knowledge.documents.deleteLabel', { title: row.title })" @click="$emit('delete', row)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </el-tooltip>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue"
import { useI18n } from "vue-i18n"
import { Delete, DocumentAdd, Loading, Refresh, RefreshRight, Search, UploadFilled, View } from "@element-plus/icons-vue"
import type { KnowledgeDocument, ResourceVisibility } from "../../types"
import { knowledgeDocumentStatus, knowledgeDocumentType } from "../../modules/knowledgeWorkbench"
import ResourceVisibilityTabs from "../common/ResourceVisibilityTabs.vue"

const props = defineProps<{
  documents: KnowledgeDocument[]
  selectedDocumentId: string
  loading: boolean
  clearing: boolean
  deletingDocId: string | null
  rebuildingDocId: string | null
  updatingDocId: string | null
}>()

defineEmits<{
  add: []
  refresh: []
  clear: []
  select: [documentId: string]
  preview: [document: KnowledgeDocument]
  update: [document: KnowledgeDocument]
  rebuild: [document: KnowledgeDocument]
  delete: [document: KnowledgeDocument]
  visibility: [document: KnowledgeDocument, visibility: ResourceVisibility]
}>()

const { t } = useI18n()
const query = ref("")
const documentType = knowledgeDocumentType
const documentStatus = knowledgeDocumentStatus

const filteredDocuments = computed(() => {
  const value = query.value.trim().toLowerCase()
  if (!value) return props.documents
  return props.documents.filter((doc) => {
    const metadataText = Object.values(doc.metadata || {}).join(" ")
    return [doc.id, doc.title, doc.source, metadataText].some((text) => String(text || "").toLowerCase().includes(value))
  })
})
</script>
```

- [ ] **Step 4: Create `KnowledgeMetadataPanel.vue`**

Create `frontend/src/components/knowledge/KnowledgeMetadataPanel.vue`:

```vue
<template>
  <section class="knowledge-metadata-panel knowledge-panel ag-content-panel">
    <div class="knowledge-section-head">
      <h4>{{ t("knowledge.workbench.selectedMetadata") }}</h4>
      <span v-if="document">{{ shortId(document.id) }}</span>
    </div>

    <div v-if="!document" class="empty-box">{{ t("knowledge.workbench.noSelection") }}</div>
    <template v-else>
      <div class="knowledge-runtime-summary metadata-summary">
        <div class="knowledge-runtime-chip">
          <span>{{ t("knowledge.drawer.documentName") }}</span>
          <strong :title="document.title">{{ document.title }}</strong>
        </div>
        <div class="knowledge-runtime-chip">
          <span>{{ t("knowledge.drawer.type") }}</span>
          <strong>{{ documentType(document) }}</strong>
        </div>
        <div class="knowledge-runtime-chip">
          <span>{{ t("knowledge.drawer.chunks") }}</span>
          <strong>{{ document.chunks }}</strong>
        </div>
        <div class="knowledge-runtime-chip">
          <span>{{ t("knowledge.drawer.updated") }}</span>
          <strong>{{ formatDate(document.created_at) }}</strong>
        </div>
      </div>
      <pre class="metadata-json">{{ prettyJson(document.metadata || {}) }}</pre>
    </template>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n"
import type { KnowledgeDocument } from "../../types"
import { knowledgeDocumentType } from "../../modules/knowledgeWorkbench"

defineProps<{ document: KnowledgeDocument | null }>()
const { t, locale } = useI18n()
const documentType = knowledgeDocumentType

const shortId = (value: string) => value.length > 14 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value || "-"
const prettyJson = (value: unknown) => JSON.stringify(value, null, 2)
const formatDate = (value: string) => {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(locale.value, { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })
}
</script>
```

- [ ] **Step 5: Create `KnowledgeRetrievalPlayground.vue`**

Create `frontend/src/components/knowledge/KnowledgeRetrievalPlayground.vue`:

```vue
<template>
  <section class="knowledge-panel ag-content-panel retrieval-playground">
    <div class="knowledge-section-head">
      <h4>{{ t("knowledge.retrieval.title") }}</h4>
      <span class="status-badge embedding">{{ searchType }}</span>
    </div>

    <div class="playground-question">
      <el-input
        v-model="query"
        type="textarea"
        :rows="4"
        :placeholder="t('knowledge.retrieval.queryPlaceholder')"
      />
      <div class="playground-controls">
        <label class="knowledge-field">
          <span>{{ t("knowledge.labels.searchType") }}</span>
          <el-select v-model="searchType" size="small">
            <el-option :label="t('knowledge.labels.hybrid')" value="hybrid" />
            <el-option :label="t('knowledge.labels.vector')" value="vector" />
            <el-option :label="t('knowledge.labels.keyword')" value="keyword" />
          </el-select>
        </label>
        <label class="knowledge-field">
          <span>{{ t("knowledge.labels.topK") }}</span>
          <el-input-number v-model="limit" :min="1" :max="20" size="small" class="!w-full" />
        </label>
        <el-button
          type="primary"
          class="cursor-pointer"
          :disabled="searching || !query.trim()"
          :loading="searching"
          @click="emitSearch"
        >
          {{ t("knowledge.actions.search") }}
        </el-button>
      </div>
    </div>

    <div class="playground-results">
      <div class="result-head">
        <strong>{{ t("knowledge.retrieval.resultTitle") }}</strong>
        <span>{{ t("knowledge.retrieval.resultCount", { count: searchResults.length }) }}</span>
      </div>

      <div v-if="searching" class="empty-box">
        <el-icon class="is-loading mr-1"><Loading /></el-icon>
        {{ t("knowledge.retrieval.searching") }}
      </div>
      <div v-else-if="searched && searchResults.length === 0" class="empty-box">{{ t("knowledge.retrieval.noResults") }}</div>
      <div v-else-if="!searched" class="empty-box">{{ t("knowledge.retrieval.idle") }}</div>

      <article
        v-for="result in searchResults"
        :key="`${result.doc_id}:${result.chunk_index}`"
        class="retrieval-hit"
      >
        <div class="hit-toolbar">
          <strong class="truncate">{{ result.title || result.doc_id || t("knowledge.labels.untitledChunk") }}</strong>
          <span class="score-badge">{{ formatScore(result.score) }}</span>
        </div>
        <p>{{ result.content }}</p>
        <div class="hit-meta">
          <span>{{ t("knowledge.labels.chunkIndex", { index: result.chunk_index }) }}</span>
          <span :title="result.source">{{ t("knowledge.labels.sourceValue", { value: result.source || "-" }) }}</span>
          <span :title="result.doc_id">{{ t("knowledge.labels.docValue", { value: shortId(result.doc_id) }) }}</span>
        </div>
      </article>

      <div v-if="searchResults.length" class="answer-preview">
        <span>{{ t("knowledge.retrieval.answer") }}</span>
        <p>{{ retrievalAnswer }}</p>
        <em>{{ t("knowledge.retrieval.reference", { value: retrievalReferences }) }}</em>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from "vue"
import { useI18n } from "vue-i18n"
import { Loading } from "@element-plus/icons-vue"
import type { KnowledgeSearchResult } from "../../types"

defineProps<{
  searching: boolean
  searched: boolean
  searchResults: KnowledgeSearchResult[]
  retrievalAnswer: string
  retrievalReferences: string
}>()

const emit = defineEmits<{
  search: [query: string, limit: number, searchType: string]
}>()

const { t } = useI18n()
const query = ref("")
const limit = ref(5)
const searchType = ref("hybrid")

const emitSearch = () => {
  const cleanQuery = query.value.trim()
  if (!cleanQuery) return
  emit("search", cleanQuery, limit.value, searchType.value)
}

const formatScore = (score: number) => `${Math.round(score * 100)}%`
const shortId = (value: string) => value ? (value.length > 12 ? `${value.slice(0, 8)}...` : value) : "-"
</script>
```

The parent `Knowledge.vue` must adapt `runSearch` to accept `(query: string, limit: number, searchType: string)` from this component.

- [ ] **Step 6: Create `KnowledgeIngestDrawer.vue`**

Create `frontend/src/components/knowledge/KnowledgeIngestDrawer.vue`:

```vue
<template>
  <el-drawer
    :model-value="modelValue"
    class="knowledge-ingest-drawer"
    :title="mode === 'update' ? t('knowledge.drawer.updateTitle') : t('knowledge.drawer.addTitle')"
    direction="rtl"
    size="460px"
    :before-close="beforeClose"
    @update:model-value="(value) => emit('update:modelValue', value)"
  >
    <div class="drawer-ingest-flow">
      <div v-if="mode === 'update' && targetDocument" class="knowledge-runtime-chip update-target">
        <span>{{ t("knowledge.drawer.updateTarget") }}</span>
        <strong :title="targetDocument.title">{{ targetDocument.title }}</strong>
      </div>

      <el-tabs v-if="mode === 'add'" v-model="inputMode">
        <el-tab-pane :label="t('knowledge.tabs.upload')" name="file">
          <el-upload
            drag
            :auto-upload="false"
            :limit="1"
            :on-change="onFileChange"
            :on-remove="clearSelectedFile"
          >
            <el-icon><UploadFilled /></el-icon>
            <div>{{ t("knowledge.upload.dropHint") }}</div>
          </el-upload>
        </el-tab-pane>
        <el-tab-pane :label="t('knowledge.tabs.text')" name="text">
          <el-input v-model="textForm.title" :placeholder="t('knowledge.drawer.documentName')" />
          <el-input v-model="textForm.content" type="textarea" :rows="8" :placeholder="t('knowledge.upload.textPlaceholder')" />
        </el-tab-pane>
        <el-tab-pane :label="t('knowledge.tabs.path')" name="path">
          <el-input v-model="pathForm.path" :placeholder="t('knowledge.upload.pathPlaceholder')" />
          <el-input v-model="pathForm.title" :placeholder="t('knowledge.drawer.documentName')" />
        </el-tab-pane>
      </el-tabs>

      <template v-else>
        <el-upload
          drag
          :auto-upload="false"
          :limit="1"
          :on-change="onFileChange"
          :on-remove="clearSelectedFile"
        >
          <el-icon><UploadFilled /></el-icon>
          <div>{{ t("knowledge.upload.dropHint") }}</div>
        </el-upload>
      </template>

      <label class="knowledge-field">
        <span>{{ t("knowledge.documents.columns.visibility") }}</span>
        <ResourceVisibilityTabs v-model="visibility" />
      </label>

      <el-collapse v-model="advancedPanels" class="drawer-advanced-ingest">
        <el-collapse-item name="advanced">
          <template #title>
            <div class="advanced-title">
              <span>{{ t("knowledge.drawer.advancedIngest") }}</span>
              <em>{{ t("knowledge.drawer.advancedIngestHint") }}</em>
            </div>
          </template>
          <div class="advanced-grid compact">
            <label class="knowledge-field">
              <span>{{ t("knowledge.drawer.readerStrategy") }}</span>
              <el-select v-model="ingestOptions.reader_strategy">
                <el-option v-for="option in readerStrategyOptions" :key="option.value" :label="option.label" :value="option.value" />
              </el-select>
            </label>
            <label class="knowledge-field">
              <span>{{ t("knowledge.drawer.chunkSize") }}</span>
              <el-input-number v-model="ingestOptions.chunk_size" :min="200" :step="100" />
            </label>
            <label class="knowledge-field">
              <span>{{ t("knowledge.drawer.chunkOverlap") }}</span>
              <el-input-number v-model="ingestOptions.chunk_overlap" :min="0" :step="20" />
            </label>
            <label class="knowledge-field">
              <span>{{ t("knowledge.drawer.codeChunkSize") }}</span>
              <el-input-number v-model="ingestOptions.code_chunk_size" :min="256" :step="100" />
            </label>
            <label class="knowledge-field">
              <span>{{ t("knowledge.drawer.semanticThreshold") }}</span>
              <el-input-number v-model="ingestOptions.semantic_threshold" :min="0" :max="1" :step="0.01" />
            </label>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <template #footer>
      <div class="drawer-footer-actions">
        <el-button :disabled="loading" @click="emit('update:modelValue', false)">{{ t("common.cancel") }}</el-button>
        <el-button type="primary" :loading="loading" :disabled="!canSubmit" @click="submit">
          {{ mode === "update" ? t("knowledge.workbench.updateDocument") : t("knowledge.workbench.addDocument") }}
        </el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue"
import { ElMessageBox, type UploadFile } from "element-plus"
import { useI18n } from "vue-i18n"
import { UploadFilled } from "@element-plus/icons-vue"
import type { KnowledgeDocument, KnowledgeIngestOptions, KnowledgeStatus, ResourceVisibility } from "../../types"
import { createDefaultKnowledgeIngestOptions } from "../../modules/knowledgeWorkbench"
import ResourceVisibilityTabs from "../common/ResourceVisibilityTabs.vue"

type DrawerMode = "add" | "update"
type InputMode = "file" | "text" | "path"

interface FileSubmitPayload {
  file: File
  title: string
  visibility: ResourceVisibility
  ingest_options: KnowledgeIngestOptions | null
}

interface TextSubmitPayload {
  title: string
  content: string
  source: string
  metadata: Record<string, string>
  visibility: ResourceVisibility
  ingest_options: KnowledgeIngestOptions | null
}

interface PathSubmitPayload {
  path: string
  title: string
  visibility: ResourceVisibility
  ingest_options: KnowledgeIngestOptions | null
}

interface UpdateSubmitPayload {
  document: KnowledgeDocument
  file: File
  title: string
  source: string
  metadata: Record<string, string>
  ingest_options: KnowledgeIngestOptions | null
}

const props = defineProps<{
  modelValue: boolean
  mode: DrawerMode
  targetDocument: KnowledgeDocument | null
  status: KnowledgeStatus | null
  loading: boolean
}>()

const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  "submit-file": [payload: FileSubmitPayload]
  "submit-text": [payload: TextSubmitPayload]
  "submit-path": [payload: PathSubmitPayload]
  "submit-update-file": [payload: UpdateSubmitPayload]
}>()

const { t } = useI18n()
const inputMode = ref<InputMode>("file")
const selectedFile = ref<File | null>(null)
const visibility = ref<ResourceVisibility>("private")
const advancedPanels = ref<string[]>([])
const ingestOptions = reactive<KnowledgeIngestOptions>(createDefaultKnowledgeIngestOptions(props.status))
const textForm = reactive({ title: "", content: "", source: "manual" })
const pathForm = reactive({ path: "", title: "" })

const advancedIngestOpen = computed(() => advancedPanels.value.includes("advanced"))
const readerStrategyOptions = computed(() => [
  { label: t("knowledge.drawer.automaticReader"), value: "auto" },
  ...(props.status?.chunk_profiles || []).map((profile) => ({
    label: `${profile.label} · ${profile.reader}`,
    value: profile.strategy,
  })),
])

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    Object.assign(ingestOptions, createDefaultKnowledgeIngestOptions(props.status))
    visibility.value = props.targetDocument?.visibility || "private"
    textForm.title = ""
    textForm.content = ""
    textForm.source = "manual"
    pathForm.path = ""
    pathForm.title = ""
    selectedFile.value = null
    advancedPanels.value = []
    inputMode.value = "file"
  },
)

const onFileChange = (file: UploadFile) => {
  selectedFile.value = file.raw || null
}

const clearSelectedFile = () => {
  selectedFile.value = null
}

const ingestOptionsPayload = () => {
  if (!advancedIngestOpen.value) return null
  return {
    chunk_size: ingestOptions.chunk_size ?? null,
    chunk_overlap: ingestOptions.chunk_overlap ?? null,
    code_chunk_size: ingestOptions.code_chunk_size ?? null,
    semantic_threshold: ingestOptions.semantic_threshold ?? null,
    reader_strategy: ingestOptions.reader_strategy === "auto" ? null : ingestOptions.reader_strategy || null,
  }
}

const canSubmit = computed(() => {
  if (props.loading) return false
  if (props.mode === "update") return Boolean(props.targetDocument && selectedFile.value)
  if (inputMode.value === "file") return Boolean(selectedFile.value)
  if (inputMode.value === "text") return Boolean(textForm.title.trim() && textForm.content.trim())
  return Boolean(pathForm.path.trim())
})

const beforeClose = async (done: () => void) => {
  if (!props.loading) {
    done()
    return
  }
  await ElMessageBox.confirm(t("knowledge.drawer.closeDuringMutation"), t("common.confirm"))
  done()
}

const submit = () => {
  const ingest_options = ingestOptionsPayload()
  if (props.mode === "update" && props.targetDocument && selectedFile.value) {
    emit("submit-update-file", {
      document: props.targetDocument,
      file: selectedFile.value,
      title: props.targetDocument.title,
      source: `upload:${selectedFile.value.name}`,
      metadata: { file_name: selectedFile.value.name },
      ingest_options,
    })
    return
  }
  if (inputMode.value === "file" && selectedFile.value) {
    emit("submit-file", {
      file: selectedFile.value,
      title: selectedFile.value.name,
      visibility: visibility.value,
      ingest_options,
    })
    return
  }
  if (inputMode.value === "text") {
    emit("submit-text", {
      title: textForm.title.trim(),
      content: textForm.content,
      source: textForm.source.trim() || "manual",
      metadata: { input_mode: "manual" },
      visibility: visibility.value,
      ingest_options,
    })
    return
  }
  emit("submit-path", {
    path: pathForm.path.trim(),
    title: pathForm.title.trim(),
    visibility: visibility.value,
    ingest_options,
  })
}
</script>
```

- [ ] **Step 7: Refactor `Knowledge.vue` as orchestrator**

Replace the old upload panels, metadata dialog, and source replacement dialog with:

```vue
<template>
  <div class="knowledge-console knowledge-workflow-shell ag-page-flow">
    <section class="knowledge-document-workbench">
      <KnowledgeDocumentList
        :documents="documents"
        :selected-document-id="selectedDocumentId"
        :loading="loading"
        :clearing="clearing"
        :deleting-doc-id="deletingDocId"
        :rebuilding-doc-id="rebuildingDocId"
        :updating-doc-id="replacingSourceDocId"
        @add="openAddDrawer"
        @refresh="loadKnowledge"
        @clear="clearAllDocuments"
        @select="selectedDocumentId = $event"
        @preview="openPreview"
        @update="openUpdateDrawer"
        @rebuild="rebuildDocument"
        @delete="deleteDocument"
        @visibility="updateDocumentVisibility"
      />
      <KnowledgeMetadataPanel :document="selectedDocument" />
    </section>

    <KnowledgeRetrievalPlayground
      :searching="searching"
      :searched="searched"
      :search-results="searchResults"
      :retrieval-answer="retrievalAnswer"
      :retrieval-references="retrievalReferences"
      @search="runSearch"
    />

    <KnowledgeIngestDrawer
      v-model="ingestDrawerOpen"
      :mode="ingestDrawerMode"
      :target-document="ingestTargetDocument"
      :status="status"
      :loading="drawerMutating"
      @submit-file="submitDrawerFileUpload"
      @submit-text="submitDrawerTextDocument"
      @submit-path="submitDrawerPathDocument"
      @submit-update-file="submitDrawerUpdateFile"
    />

    <el-drawer
      v-model="previewDrawerOpen"
      class="document-preview-drawer"
      :title="t('knowledge.drawer.previewTitle')"
      direction="rtl"
      size="420px"
    >
      <!-- keep existing preview drawer content -->
    </el-drawer>
  </div>
</template>
```

Add orchestrator state:

```typescript
type IngestDrawerMode = "add" | "update"
const selectedDocumentId = ref("")
const ingestDrawerOpen = ref(false)
const ingestDrawerMode = ref<IngestDrawerMode>("add")
const ingestTargetDocument = ref<KnowledgeDocument | null>(null)

const selectedDocument = computed(() => documents.value.find((doc) => doc.id === selectedDocumentId.value) || null)
const drawerMutating = computed(() => uploadingBrowserFile.value || savingText.value || savingPath.value || Boolean(replacingSourceDocId.value))
```

After every `documents.value = data.documents`, set:

```typescript
selectedDocumentId.value = resolveSelectedKnowledgeDocumentId(documents.value, selectedDocumentId.value)
```

On update success:

```typescript
documents.value = mergeUpdatedKnowledgeDocument(documents.value, doc.id, updated)
selectedDocumentId.value = updated.id
await loadKnowledge()
selectedDocumentId.value = resolveSelectedKnowledgeDocumentId(documents.value, updated.id)
```

- [ ] **Step 8: Add compact workbench CSS**

Keep the existing Knowledge scoped style variables, but change document list grid:

```css
.knowledge-document-workbench {
  display: grid;
  grid-template-columns: minmax(420px, 0.98fr) minmax(360px, 1.02fr);
  gap: 14px;
  align-items: start;
}

.document-list-compact .document-table-head,
.document-list-compact .document-row {
  grid-template-columns: minmax(180px, 1fr) minmax(84px, 0.34fr) minmax(96px, 0.38fr) 132px;
}

.document-row.selected {
  border-color: color-mix(in srgb, var(--kn-embedding) 56%, var(--kn-border));
  background: color-mix(in srgb, var(--kn-embedding-soft) 44%, var(--kn-panel));
  box-shadow: inset 3px 0 0 var(--kn-embedding);
}

@media (max-width: 1120px) {
  .knowledge-document-workbench {
    grid-template-columns: minmax(0, 1fr);
  }
}
```

- [ ] **Step 9: Run frontend tests**

```bash
cd frontend && bun run test:shell
cd frontend && bun run test:auth
cd frontend && bun run build
```

Expected: all commands pass.

- [ ] **Step 10: Commit Knowledge UI split**

```bash
git add frontend/src/components/Knowledge.vue frontend/src/components/knowledge frontend/src/composables/useKnowledgeApi.ts frontend/src/i18n/locales/en-US.ts frontend/src/i18n/locales/zh-CN.ts frontend/src/modules/testSource.mjs frontend/src/modules/knowledgeSettingsSourceContracts.test.mjs
git commit -m "feat: refactor knowledge document workbench"
```

---

### Task 5: Sidebar Navigation Defaults And Density

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/components/Settings.vue`
- Modify: `frontend/src/style.css`
- Modify: `frontend/src/modules/shellNavigation.test.mjs`

**Interfaces:**
- Produces:
  - Default governance group order `trace`, `memory`, `evaluation`, `approvals`, `scheduler`
  - Default knowledge group order `skills`, `mcp`, `knowledge`
  - Tighter sidebar nav CSS
- Consumes:
  - Existing `buildSidebarNavGroups(...)` behavior preserving stored layouts

- [ ] **Step 1: Update failing navigation tests**

Modify `frontend/src/modules/shellNavigation.test.mjs` expectations.

In the `buildShellHomeSections(...)` test, change groups:

```javascript
{ key: "knowledge", items: [item("skills"), item("mcp"), item("knowledge")] },
{ key: "governance", items: [item("trace"), item("memory"), item("evaluation"), item("approvals"), item("scheduler")] },
```

Expected section result:

```javascript
[
  { title: "Operations", items: ["dashboard", "chat", "workflow"] },
  { title: "Knowledge", items: ["skills", "mcp", "knowledge"] },
  { title: "Governance", items: ["trace", "memory", "evaluation", "approvals", "scheduler"] },
  { title: "Security Data", items: ["cve", "collect"] },
]
```

In the stored layout test, use defaults:

```javascript
{ key: "knowledge", ids: ["skills", "mcp", "knowledge"] },
{ key: "governance", ids: ["trace", "memory", "evaluation", "approvals", "scheduler"] },
```

Keep the stored group that moves `trace` into Knowledge. Add `memory` to stored governance:

```javascript
{ key: "governance", items: [{ id: "memory", tag: "" }, { id: "evaluation", tag: "" }, { id: "approvals", tag: "" }, { id: "scheduler", tag: "" }] },
```

Expected stored result:

```javascript
[
  { key: "operations", items: ["home", "dashboard", "chat", "workflow"] },
  { key: "knowledge", items: ["Trace moved", "skills", "mcp", "knowledge"] },
  { key: "governance", items: ["memory", "evaluation", "approvals", "scheduler"] },
  { key: "securityData", items: ["cve", "collect"] },
  { key: "settings", items: ["settings"] },
]
```

Run:

```bash
cd frontend && bun run test:shell
```

Expected: FAIL because App and Settings defaults still put Memory under Knowledge.

- [ ] **Step 2: Update App defaults**

Modify `frontend/src/App.vue`:

```typescript
const defaultSidebarNavGroupIds: Array<{ key: SidebarNavGroupKey; ids: NavId[] }> = [
  { key: "operations", ids: ["home", "dashboard", "chat", "workflow"] },
  { key: "knowledge", ids: ["skills", "mcp", "knowledge"] },
  { key: "governance", ids: ["trace", "memory", "evaluation", "approvals", "scheduler"] },
  { key: "securityData", ids: ["cve", "collect"] },
  { key: "settings", ids: ["settings"] },
]
```

- [ ] **Step 3: Update Settings defaults**

Modify `frontend/src/components/Settings.vue`:

```typescript
const defaultNavigationGroups = computed<NavigationGroupConfig[]>(() => [
  {
    key: "operations",
    items: ["Home", "Dashboard", "Chat", "Workflow"].map((id) => ({ id, tag: "" })),
  },
  {
    key: "knowledge",
    items: ["Skills", "MCP", "Knowledge"].map((id) => ({ id, tag: "" })),
  },
  {
    key: "governance",
    items: ["Trace", "Memory", "Evaluation", "Approvals", "Scheduler"].map((id) => ({ id, tag: "" })),
  },
  {
    key: "securityData",
    items: ["CVE", "Collect"].map((id) => ({ id, tag: "" })),
  },
  {
    key: "settings",
    items: ["Settings"].map((id) => ({ id, tag: "" })),
  },
])
```

- [ ] **Step 4: Tighten sidebar nav CSS**

Modify `frontend/src/style.css`:

```css
.ag-nav {
	padding: 10px;
}

.ag-nav-list {
	display: grid;
	gap: 2px;
}

.ag-nav-divider {
	height: 1px;
	margin: 8px 0;
	background: var(--ag-sidebar-border);
}

.ag-nav-item {
	display: flex;
	width: 100%;
	min-height: 36px;
	align-items: center;
	gap: 8px;
	border: 1px solid transparent;
	border-radius: 8px;
	padding: 5px 7px;
	color: var(--ag-sidebar-text);
	text-align: left;
	transition:
		border-color 0.16s ease,
		background 0.16s ease,
		color 0.16s ease;
}

.ag-nav-icon {
	display: grid;
	width: 24px;
	height: 24px;
	flex: 0 0 auto;
	place-items: center;
	border: 1px solid var(--ag-sidebar-border);
	border-radius: 7px;
	background: var(--ag-sidebar-icon);
	color: var(--ag-sidebar-muted);
}
```

Keep `.ag-nav-label` font size unchanged unless Playwright shows text crowding.

- [ ] **Step 5: Run nav/frontend gates**

```bash
cd frontend && bun run test:shell
cd frontend && bun run test:auth
cd frontend && bun run build
```

Expected: all commands pass.

- [ ] **Step 6: Commit navigation defaults**

```bash
git add frontend/src/App.vue frontend/src/components/Settings.vue frontend/src/style.css frontend/src/modules/shellNavigation.test.mjs
git commit -m "feat: tighten sidebar navigation layout"
```

---

### Task 6: Integration Verification And Browser Evidence

**Files:**
- Modify only if verification exposes defects in files changed by Tasks 1-5.

**Interfaces:**
- Consumes all prior task deliverables.
- Produces final verification evidence and screenshots.

- [ ] **Step 1: Run backend focused tests**

```bash
uv run pytest api/tests/test_knowledge_lifecycle.py api/tests/test_knowledge_ingest_runtime.py api/tests/test_knowledge_projection.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run backend static gates**

```bash
uv run ruff check api/persistence/knowledge_sources.py api/routes/knowledge.py api/services/knowledge_service.py api/services/knowledge_ingest_service.py api/tests/test_knowledge_lifecycle.py api/tests/test_knowledge_ingest_runtime.py
uv run ty check api/persistence/knowledge_sources.py api/routes/knowledge.py api/services/knowledge_service.py api/services/knowledge_ingest_service.py api/tests/test_knowledge_lifecycle.py api/tests/test_knowledge_ingest_runtime.py
```

Expected: both commands pass.

- [ ] **Step 3: Run frontend gates**

```bash
cd frontend && bun run test:shell
cd frontend && bun run test:auth
cd frontend && bun run build
```

Expected: all commands pass.

- [ ] **Step 4: Run whitespace gate**

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 5: Start pre-prod server**

```bash
AGNO_BOOTSTRAP_ADMIN_EMAIL=admin@example.com AGNO_BOOTSTRAP_ADMIN_PASSWORD='AdminPass123!' uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
```

Expected log includes:

```text
Application startup complete
```

Keep the server running for browser verification.

- [ ] **Step 6: Use Playwright for 1920x1080 verification**

Use the `playwright-cli` skill or local Playwright tooling to:

1. Open `http://127.0.0.1:8001`.
2. Log in with `admin@example.com` / `AdminPass123!`.
3. Navigate to Knowledge.
4. Capture the full Knowledge page at 1920x1080.
5. Open the Add Drawer and capture it.
6. Upload a `.md` file and confirm the new document is selected.
7. Update that document with another `.md` file and confirm the returned document remains selected.
8. Update the document with `.csv` content and confirm the UI stays responsive.
9. Upload a `.json` file, update it with `.js`, and confirm the UI stays responsive.
10. Capture the sidebar showing Memory directly under Trace.
11. Inspect console output; expected error and warning count is 0.

Expected screenshots:

```text
tmp/knowledge-workbench-1920.png
tmp/knowledge-ingest-drawer-1920.png
tmp/knowledge-navigation-1920.png
```

- [ ] **Step 7: Fix verification defects in smallest relevant file set**

If a verification command fails, do not broaden the scope. Fix only the file set that owns the failing behavior, then rerun the exact failed command plus its enclosing gate.

- [ ] **Step 8: Final commit if verification fixes were required**

If Step 7 changed files:

```bash
git add <changed files>
git commit -m "fix: polish knowledge update verification"
```

If Step 7 did not change files, do not create an empty commit.
