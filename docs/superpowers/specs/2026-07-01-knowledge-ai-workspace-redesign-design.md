# Knowledge AI Workspace Redesign Design

## Goal

Redesign the existing Knowledge / RAG page into a modern AI workspace while preserving every current capability and backend API contract.

## Product Context

The target user is an operator building and validating a RAG knowledge base. They need a clear workflow from uploading content to checking index health, managing documents, validating retrieval, and inspecting advanced settings only when needed.

## Design Direction

Subject: RAG knowledge workspace for Agno AIOS security operations.

Audience: normal users who upload and search knowledge, plus advanced users who tune readers, chunking, retrieval, and metadata.

Single job: make the complete RAG lifecycle visible without turning the page into a dense admin console.

Color token system:

- Canvas `#F7F9FC`
- Panel `#FFFFFF`
- Soft surface `#EEF3F7`
- Ink `#15171C`
- Muted slate `#626C78`
- Ready green `#2DA76C`
- Embedding blue `#2F77D4`
- Parsing orange `#C88A22`
- Failed red `#DF3F36`

Type:

- Keep the existing app type stack for consistency.
- Use mono only for ids, chunk scores, storage names, model names, and source paths.

Layout:

```text
Header
┌ Knowledge title/actions ┐

Statistics Dashboard
┌ Documents ┐ ┌ Chunks ┐ ┌ Embedding Model ┐ ┌ Vector DB ┐ ┌ Storage ┐ ┌ Status ┐

Workspace
┌ Upload knowledge ────────────┐ ┌ Retrieval Playground ─────────────┐
│ upload/text/path tabs        │ │ Question, controls, retrieved hits │
│ auto reader note             │ │ score/source/content/reference     │
│ task progress timeline       │ │ answer placeholder from retrieval  │
└──────────────────────────────┘ └────────────────────────────────────┘

Documents
┌ Search/filter + table with name/type/size/chunks/status/time/tags/source/actions ┐

Advanced Configuration
┌ collapsed by default: Reader, chunk profiles, search params, advanced info ┐
```

Signature:

The page uses a visible RAG pipeline rail: Uploading → Parsing → Chunking → Embedding → Completed. It turns async ingestion into a product workflow instead of a spinner-only admin action.

Self-critique:

The generic fix would only rearrange cards and add more badges. This design reduces top-level card count, hides developer-heavy details by default, and makes the default path suitable for non-expert users. The one intentional visual risk is making the upload/pipeline card the page's operational hero, because it matches the user's first action and the RAG lifecycle.

## Scope

In scope:

- Keep file upload, text import, and server path import.
- Keep existing status, document listing, deletion, clear, search, and RAG setting display.
- Move Reader/chunk profiles and developer fields into Advanced Configuration.
- Present status as Statistics Dashboard cards.
- Add frontend task progress for upload/import operations.
- Add Retry for failed frontend ingestion actions.
- Improve document table columns using existing fields and metadata.
- Add Preview and Metadata actions using frontend-only drawers/dialogs.
- Show Re-Embedding as a disabled action with tooltip because no backend endpoint exists yet.
- Improve loading, empty states, hover feedback, badges, and dark/light consistency.

Out of scope:

- New backend preview API.
- New backend re-embedding API.
- Editable metadata persistence.
- Real answer generation in Retrieval Playground. The page can show an answer/reference summary derived from retrieved chunks until an answer API exists.

## Data Flow

The page continues to use `useKnowledgeApi()`:

- `fetchKnowledge()` populates `status` and `documents`.
- `addTextDocument()` handles browser-uploaded text and manual text input.
- `addFileDocument()` handles server path import.
- `deleteKnowledgeDocument()` deletes a document.
- `clearKnowledge()` clears all documents.
- `searchKnowledge()` powers Retrieval Playground.

Frontend-only derived data:

- `statisticsCards` maps status/documents into user-facing cards.
- `advancedInfoRows` moves Schema, Dimension, Runtime, Candidates, Suffixes, database paths, and device into Advanced Information.
- `documentRows` derives document type, size, tags, embedding status, updated time, and source from existing document metadata.
- `ingestTask` tracks task phase and retry function for upload/text/path submissions.

## Testing

- Extend `frontend/src/uiShell.test.mjs` for Knowledge workspace markers:
  - `knowledge-workflow-shell`
  - `knowledge-stat-dashboard`
  - `knowledge-upload-pipeline`
  - `retrieval-playground`
  - `advanced-configuration`
  - `document-preview-drawer`
- Run `cd frontend && npm run test:shell`.
- Run `cd frontend && npm run build`.
- Run repository checks:
  - `uv run ruff check .`
  - `uv run ty check .`
- Use Playwright with mocked auth/knowledge APIs to inspect light/dark layout.

## Acceptance Criteria

- Top-level flow reads Upload, Statistics, Documents, Retrieval Playground, Advanced Configuration.
- Reader cards no longer dominate the default upload area.
- Statistics are cards; developer-heavy fields are under Advanced Information.
- Documents table includes document name, type, size, chunks, embedding status, updated time, tags, source, and actions.
- Retrieval Playground shows question controls, retrieved chunks, score, source, content, answer/reference summary.
- Advanced Configuration is collapsed by default and contains reader, chunk strategy, parser/OCR/metadata, and RAG parameters.
- Long-running operations show loading/progress and can retry after failure.
- Existing business actions still call the same API functions.
