# Knowledge UI, Per-Upload Update Flow, and Navigation Design

## Scope

This phase covers three related changes:

- Rework the Knowledge page into a document-first workbench.
- Replace the existing source-replacement interaction with a unified Add/Update Drawer and a stronger document-level incremental replace flow.
- Tighten sidebar navigation spacing and move Memory under Trace in the default navigation layout.

Trace session detail gaps are explicitly out of scope for this phase. The known sessions that have Chat history but missing Trace run detail will be handled in a separate follow-up design.

## Current Context

The current `Knowledge.vue` mixes upload, retrieval, document table, metadata dialog, source replacement dialog, and global RAG settings in one component. The backend already has a `replace_document_source_async()` flow that inserts a new source version and deletes the old content when the new version is found. That direction matches the desired user experience, but the implementation needs stricter cross-type coverage and cleanup guarantees.

Agno Knowledge uses content ingestion, chunking/embedding, and retrieval as separate steps, with readers and chunkers selected per content source. The local Agno implementation generates `Content.id` from a content hash, and PgVector row IDs include the content hash. Because of that, this phase will not force a stable doc ID across updates.

## UX Design

The first screen of Knowledge becomes a document management workbench:

- Left side: document list with document name, status, visibility, and actions.
- Right side: metadata panel for the currently selected document.
- Bottom: retrieval playground retained from the existing page.

The document list owns filtering, refresh, clear, visibility, preview, update, rebuild, and delete actions. The metadata panel replaces the current metadata dialog and shows selected document details plus a JSON metadata viewer.

The global advanced RAG settings section is removed from the page-level bottom area. Advanced ingestion controls move into the Add/Update Drawer as per-request controls.

## Drawer Design

Add and Update share one right-side Drawer:

- Add mode supports file upload, manual text, and server path import.
- Update mode focuses on file upload and preserves the existing document title and visibility by default.
- The primary action text changes by mode: Add or Update.
- The upload pipeline status remains visible in the Drawer while work is running.
- The Drawer cannot be closed accidentally while a mutation is in progress without an explicit cancel/confirm behavior.

Advanced controls are collapsed by default. When collapsed, backend defaults are used. When expanded, users may override this request only:

- `chunk_size`
- `chunk_overlap`
- `code_chunk_size`
- `semantic_threshold`
- `reader_strategy`, defaulting to automatic selection from filename

These values do not mutate global RAG settings. The resolved reader, strategy, and effective numeric options are recorded in document metadata for auditability.

## Frontend Components

`Knowledge.vue` remains the page entry point and orchestrator. It should be split into focused local components:

- `KnowledgeDocumentList`: list, filters, refresh, clear, row actions, visibility updates.
- `KnowledgeMetadataPanel`: selected document summary and metadata JSON.
- `KnowledgeIngestDrawer`: add/update Drawer, file/text/path inputs, per-request advanced controls, upload pipeline.
- `KnowledgeRetrievalPlayground`: retrieval query and result preview.

The page owns the canonical document array and selected document ID. Selection rules:

- On initial load, select the first visible document.
- If filtering hides the current selected document, select the first visible document.
- After add, select the newly created document.
- After update, remove the old document ID, add or refresh the returned new document, and select the new document.
- After delete, select the next visible document or clear the selection.

## Backend API Design

Add optional per-request ingest options to the relevant Knowledge request models:

- Text document creation.
- Server path document creation.
- Source update.

Use a shared request model such as `KnowledgeIngestOptionsRequest` with optional fields for the advanced Drawer controls. Backend defaults remain the source of truth when fields are omitted.

The Knowledge lifecycle should accept an optional resolved ingest options object for:

- `add_text_document_async()`
- `add_file_document_async()`
- `replace_document_source_async()`

Reader construction should merge defaults from current RAG settings with per-request overrides, then resolve the reader profile from filename unless a valid `reader_strategy` override is supplied.

## Update Semantics

Updates use document-level incremental replacement:

1. Validate the old document exists and the actor can manage it.
2. Read and validate the new file content and suffix.
3. Insert the new content with the resolved reader/chunker configuration.
4. Confirm the new content row can be found.
5. Store the new source snapshot.
6. Delete the old document's vector rows, content row, and source snapshot.
7. Return the new document payload.

This deliberately does not perform chunk-level diffing. Cross-type updates such as JSON to JS or Markdown to CSV can change reader selection and chunk boundaries completely, so chunk-level reuse would be fragile and would increase stale chunk risk.

The old document must not be deleted until the new version is inserted and readable. If old-document cleanup fails after the new version is inserted, the API should report a clear error rather than silently claiming a clean update. Tests must cover that stale vectors/content/source snapshots are not left behind on the successful path.

The update flow may return a new doc ID. The UI hides unnecessary ID churn by selecting the returned document and preserving user-facing title and visibility.

## Navigation Design

Default sidebar layout changes:

- Operations: Home, Dashboard, Chat, Workflow.
- Knowledge: Skills, MCP, Knowledge.
- Governance: Trace, Memory, Evaluation, Approvals, Scheduler.
- Security Data: CVE, Collect.
- Settings: Settings.

Existing user-customized `NAV_TAGS` layouts remain respected. The Settings navigation defaults must be updated to match the App defaults so new users and reset layouts are consistent.

Navigation density is tightened by reducing the combined effect of:

- `.ag-nav` padding.
- `.ag-nav-list` gap.
- `.ag-nav-divider` margin.
- `.ag-nav-item` minimum height and padding.
- Sidebar nav icon dimensions.

The design should keep a usable click target and preserve existing permission logic, active state behavior, compact sidebar behavior, and mobile drawer behavior.

## Testing and Verification

Backend tests should cover:

- First upload for multiple suffixes, including Markdown, CSV, JSON, JS, and plain text.
- Same-type update.
- Cross-type update, including JSON to JS and Markdown to CSV.
- Per-request advanced options applying to the inserted document metadata and reader configuration.
- Old vector rows, old content rows, and old source snapshots are deleted on successful update.
- Old document remains when new insertion fails.
- Unauthorized update does not initialize the Knowledge runtime or mutate records.

Frontend source-contract and shell tests should cover:

- Document-first layout exists.
- Metadata panel replaces the metadata dialog interaction.
- Add and Update use the same Drawer.
- Drawer advanced controls are collapsed by default.
- Update success selects the returned new document.
- Navigation default order places Memory directly below Trace.
- Existing stored navigation layouts still win over defaults.

Manual/browser verification should cover:

- `uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8001`.
- Knowledge page screenshot at 1920x1080.
- Drawer screenshot at 1920x1080.
- Sidebar navigation screenshot at 1920x1080.
- File upload/update smoke for multiple suffixes, including first upload, same-type update, and cross-type update.
- No apparent UI overlap, no fake-dead page state, and no browser console errors.

Required automated gates for implementation:

- `uv run ruff check <changed backend files>`
- `uv run ty check <changed backend files>`
- Relevant `uv run pytest ...`
- `cd frontend && bun run test:shell`
- `cd frontend && bun run test:auth`
- `cd frontend && bun run build`
- `git diff --check`
