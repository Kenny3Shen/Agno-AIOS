# Knowledge AI Workspace Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the existing Knowledge page into a modern AI workspace without removing any existing RAG management capability.

**Architecture:** Keep all logic in `frontend/src/components/Knowledge.vue` and reuse the existing `useKnowledgeApi()` contract. Add frontend-only computed view models and drawers/dialogs for preview and metadata. Use shell tests to guard the required page structure.

**Tech Stack:** Vue 3 `<script setup lang="ts">`, Element Plus, Node shell tests, Vite/vue-tsc, existing FastAPI knowledge endpoints.

## Global Constraints

- Do not remove existing Knowledge functions.
- Do not require backend API changes.
- Advanced controls may remain disabled when the backend has no save endpoint.
- Re-Embedding must be visible but disabled with a tooltip until a backend endpoint exists.
- Run `uv run ruff check .`, `uv run ty check .`, `cd frontend && npm run test:shell`, `cd frontend && npm run build`, and Playwright verification.

---

### Task 1: Add Red Tests For New Knowledge Information Architecture

**Files:**

- Modify: `frontend/src/uiShell.test.mjs`

**Interfaces:**

- Consumes: `components/Knowledge.vue` source text
- Produces: assertions for the new workspace structure

- [x] **Step 1: Write failing tests**

Add assertions requiring:

```js
/knowledge-workflow-shell/
/knowledge-stat-dashboard/
/knowledge-upload-pipeline/
/retrieval-playground/
/advanced-configuration/
/document-preview-drawer/
```

- [x] **Step 2: Run test to verify failure**

Run: `cd frontend && npm run test:shell`

Expected: FAIL before implementation.

### Task 2: Rewrite Knowledge Template Around The RAG Workflow

**Files:**

- Modify: `frontend/src/components/Knowledge.vue`

**Interfaces:**

- Consumes: existing refs/reactive state and API methods
- Produces: sections named Upload, Statistics, Retrieval Playground, Documents, Advanced Configuration

- [ ] **Step 1: Rebuild top-level layout**

Create `.knowledge-workflow-shell`, `.knowledge-stat-dashboard`, `.knowledge-workspace-grid`, `.retrieval-playground`, `.knowledge-documents-section`, and `.advanced-configuration`.

- [ ] **Step 2: Keep existing upload modes**

Keep `activeIngestTab`, browser file upload, text form, and server path form.

- [ ] **Step 3: Move reader cards to Advanced**

Render `chunkProfiles` inside Advanced Configuration instead of default upload area.

### Task 3: Add Frontend View Models And Interactions

**Files:**

- Modify: `frontend/src/components/Knowledge.vue`

**Interfaces:**

- Produces:
  - `statisticsCards`
  - `advancedInfoRows`
  - `documentType()`
  - `documentSize()`
  - `embeddingStatus()`
  - `ingestTask`
  - `previewDocument`
  - `metadataDocument`
  - `retryIngestTask()`

- [ ] **Step 1: Add ingestion task state**

Track current stage, status, message, and retry handler for upload/text/path operations.

- [ ] **Step 2: Add document preview/metadata state**

Use Element Plus drawer/dialog to show existing document fields and metadata.

- [ ] **Step 3: Add retrieval summaries**

Show retrieved chunks, score, source, and a lightweight answer/reference summary derived from search results.

### Task 4: Restyle As AI Workspace

**Files:**

- Modify: `frontend/src/components/Knowledge.vue`

**Interfaces:**

- Consumes: global `--ag-*` tokens
- Produces: consistent cards, badges, hover, empty states, dark/light support

- [ ] **Step 1: Replace old dense panel style**

Use fewer panels, more white space, and compact badges.

- [ ] **Step 2: Add responsive behavior**

Use top statistics, middle upload/playground two-column layout, bottom documents, and collapsed advanced configuration.

### Task 5: Verify

**Files:**

- Verify: repository root and `frontend/`

- [ ] **Step 1: Run shell/build checks**

Run: `cd frontend && npm run test:shell`

Expected: PASS.

Run: `cd frontend && npm run build`

Expected: PASS.

- [ ] **Step 2: Run Python checks**

Run: `uv run ruff check .`

Expected: PASS.

Run: `uv run ty check .`

Expected: PASS.

- [ ] **Step 3: Playwright verification**

Mock auth and knowledge APIs, inspect Knowledge in light/dark modes, and verify no console/runtime errors.
