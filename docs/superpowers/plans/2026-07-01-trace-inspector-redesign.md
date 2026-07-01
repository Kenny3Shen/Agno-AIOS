# Trace Inspector Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Trace inspector so the header is compact, Info only shows input/output, Metadata owns span facts/raw attributes, JSON payloads are formatted, and light/dark mode follows global theme tokens.

**Architecture:** Keep the work inside the existing Vue Trace component and existing shell test. Add derived computed data for compact trace evidence and span metadata, then update CSS variables to use the global AgentOS theme tokens.

**Tech Stack:** Vue 3 `<script setup lang="ts">`, Element Plus, MarkdownIt, Node shell tests, Vite/vue-tsc.

## Global Constraints

- Preserve existing frontend structure in `frontend/`.
- Do not change backend trace API shape.
- Keep raw attributes available because database-backed tracing fields vary by provider.
- Use `uv run ruff check .` and `uv run ty check .` after code changes.
- Use Playwright/browser verification after frontend changes.

---

### Task 1: Lock Trace UI Structure With Shell Tests

**Files:**

- Modify: `frontend/src/uiShell.test.mjs`

**Interfaces:**

- Consumes: source text from `frontend/src/components/Trace.vue`
- Produces: assertions requiring `trace-evidence-strip`, `activeDetailTab`, `isJsonPayload`, and `trace-metadata-ledger`

- [x] **Step 1: Write the failing test**

Add assertions:

```js
assert.match(trace, /trace-evidence-strip/, "Trace run header must use compact copyable evidence chips instead of large Session/Run/Agent/Workflow cards")
assert.match(trace, /activeDetailTab/, "Trace span detail must expose an Info/Metadata tab state")
assert.match(trace, /isJsonPayload/, "Trace input and output sections must render JSON payloads as formatted code blocks")
assert.match(trace, /trace-metadata-ledger/, "Trace Metadata tab must collect span offsets, parent, events, ids, extracted metadata, and raw attributes")
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test:shell`

Expected: FAIL on missing `trace-evidence-strip`.

### Task 2: Update Trace Template And Script

**Files:**

- Modify: `frontend/src/components/Trace.vue`

**Interfaces:**

- Consumes: `TraceItem`, `SpanItem`, `ParsedSpanPayload`
- Produces: `selectedTraceEvidence`, `activeDetailTab`, `spanMetadataItems`, `isJsonPayload()`, `formatPayloadText()`, `renderPayloadMarkup()`

- [x] **Step 1: Replace trace fact cards**

Render `selectedTraceEvidence` as `.trace-evidence-strip` with `.trace-evidence-chip` buttons and `CopyDocument` icons.

- [x] **Step 2: Add Info/Metadata tab state**

Add:

```ts
const activeDetailTab = ref<"info" | "metadata">("info")
```

Reset it in `selectSpan()`.

- [x] **Step 3: Move span facts to Metadata**

Build `spanMetadataItems` from selected span facts and parsed metadata.

- [x] **Step 4: Render JSON payloads safely**

Use `<pre>` for JSON payloads and MarkdownIt only for non-JSON payloads.

- [x] **Step 5: Run frontend checks**

Run: `cd frontend && npm run test:shell`

Expected: PASS.

Run: `cd frontend && npm run build`

Expected: PASS.

### Task 3: Update Trace Theme Styles

**Files:**

- Modify: `frontend/src/components/Trace.vue`

**Interfaces:**

- Consumes: global CSS variables from `frontend/src/style.css`
- Produces: Trace-local variables mapped to `--ag-*` light/dark theme tokens

- [x] **Step 1: Map Trace variables to global theme tokens**

Use `--ag-frame`, `--ag-panel`, `--ag-panel-soft`, `--ag-border`, `--ag-text`, and related tokens as Trace defaults.

- [x] **Step 2: Replace hardcoded dark surfaces**

Use `var(--trace-panel)`, `var(--trace-panel-soft)`, `var(--trace-code-bg)`, and `var(--trace-code-text)` for header, hierarchy, detail, IO, metadata, events, and JSON blocks.

- [x] **Step 3: Keep responsive behavior**

Keep the existing breakpoint structure and make evidence chips wrap on mobile.

### Task 4: Final Verification

**Files:**

- Verify: repository root
- Verify: `frontend/`

- [ ] **Step 1: Run Python format/static checks**

Run: `uv run ruff check .`

Expected: PASS.

Run: `uv run ty check .`

Expected: PASS.

- [ ] **Step 2: Run frontend checks**

Run: `cd frontend && npm run test:shell`

Expected: PASS.

Run: `cd frontend && npm run build`

Expected: PASS.

- [ ] **Step 3: Browser verification**

Use Playwright to open the frontend and inspect the Trace page in light and dark modes. Capture or review screenshots and fix visible layout/runtime issues.
