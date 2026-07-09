# Frontend Modular Atomic Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the largest frontend Vue pages into orchestration shells backed by focused workflow components, composables, and shared UnoCSS atomic primitives.

**Architecture:** Shared visual atoms live in `frontend/uno.config.ts` and `frontend/src/components/common/*`. Page shells keep route-level wiring while child components own panels, lists, dialogs, viewers, and command bars; composables own state transitions and API orchestration. Old source contracts that preserved page-local class names are replaced by contracts for module boundaries and reusable primitives.

**Tech Stack:** Vue 3 SFC, TypeScript, UnoCSS, Element Plus, markdown-it, Bun test scripts.

## Global Constraints

- Do not change backend APIs or payload formats.
- Do not change package dependencies or `frontend/package.json`.
- Do not rewrite the entire application shell or router.
- Do not preserve old page-local class names or DOM shape when they only existed for scoped CSS compatibility.
- Use TDD: write or rewrite the source-contract test first, verify it fails, then implement.
- Use `frontend/uno.config.ts` for repeated chip/status/empty/header/row/code-panel style atoms.
- Keep scoped CSS only for complex layout, deep third-party overrides, Markdown/Payload content, Trace visualization, or page-specific interactions that are less readable as utility strings.
- Run `cd frontend && bun run test:shell`, `cd frontend && bun run test:auth`, and `cd frontend && bun run build` after each implemented phase.
- For UI phases, run Playwright at 1920x1080 for touched pages and add narrow viewport screenshots where layout risk exists.

---

### Task 1: Shared Atomic Foundation Contracts

**Files:**
- Modify: `frontend/src/modules/utilityFirstPrimitivesSourceContracts.test.mjs`
- Modify: `frontend/src/modules/testSource.mjs`

**Interfaces:**
- Consumes: source files as text via `readOptionalSource`.
- Produces: contract checks for `DataChip.vue`, `StatusDot.vue`, `SectionHeader.vue`, `MarkdownViewer.vue`, `PayloadViewer.vue`, and new UnoCSS shortcuts.

- [ ] **Step 1: Write the failing test**

Add source readers in `frontend/src/modules/utilityFirstPrimitivesSourceContracts.test.mjs`:

```js
const dataChip = readOptionalSource("components/common/DataChip.vue")
const statusDot = readOptionalSource("components/common/StatusDot.vue")
const sectionHeader = readOptionalSource("components/common/SectionHeader.vue")
const markdownViewer = readOptionalSource("components/common/MarkdownViewer.vue")
const payloadViewer = readOptionalSource("components/common/PayloadViewer.vue")
```

Add shortcut assertions:

```js
for (const shortcut of [
  "ag-data-chip",
  "ag-status-dot",
  "ag-section-header",
  "ag-surface-row",
  "ag-field-label",
  "ag-code-panel",
  "ag-empty-compact",
]) {
  assert.match(
    unoConfig,
    new RegExp(`['"]${shortcut}['"]`),
    `UnoCSS config must expose the shared ${shortcut} shortcut`,
  )
}
```

Add component assertions:

```js
for (const [name, source] of [
  ["DataChip", dataChip],
  ["StatusDot", statusDot],
  ["SectionHeader", sectionHeader],
  ["MarkdownViewer", markdownViewer],
  ["PayloadViewer", payloadViewer],
]) {
  assert.ok(source.length > 0, `${name}.vue must exist in components/common`)
  assert.match(source, /<script setup lang="ts">/, `${name}.vue must use typed script setup`)
}

assert.match(dataChip, /defineProps<\{[\s\S]*label: string[\s\S]*value: string \| number/, "DataChip must accept label and value props")
assert.match(dataChip, /ag-data-chip/, "DataChip must consume the shared data chip shortcut")
assert.match(statusDot, /ag-status-dot/, "StatusDot must consume the shared status dot shortcut")
assert.match(statusDot, /aria-label/, "StatusDot must expose an accessible label")
assert.match(sectionHeader, /ag-section-header/, "SectionHeader must consume the shared section header shortcut")
assert.match(sectionHeader, /\$slots\.actions/, "SectionHeader must provide an actions slot")
assert.match(markdownViewer, /import MarkdownIt from "markdown-it"/, "MarkdownViewer must centralize markdown-it rendering")
assert.match(markdownViewer, /v-html="renderedHtml"/, "MarkdownViewer must render sanitized markdown output through a computed value")
assert.match(payloadViewer, /import MarkdownViewer from "\.\/MarkdownViewer\.vue"/, "PayloadViewer must reuse MarkdownViewer for markdown mode")
assert.match(payloadViewer, /copyToClipboard/, "PayloadViewer must expose copy behavior")
assert.match(payloadViewer, /type PayloadViewMode = "text" \| "json" \| "markdown"/, "PayloadViewer must support text, json, and markdown modes")
assert.match(payloadViewer, /ag-code-panel/, "PayloadViewer must consume the shared code panel shortcut")
assert.match(payloadViewer, /ag-empty-compact/, "PayloadViewer must use the compact empty primitive")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && bun run test:shell`

Expected: FAIL because the new shortcuts and common viewer components do not exist yet.

### Task 2: Shared Atomic Foundation Implementation

**Files:**
- Modify: `frontend/uno.config.ts`
- Create: `frontend/src/components/common/DataChip.vue`
- Create: `frontend/src/components/common/StatusDot.vue`
- Create: `frontend/src/components/common/SectionHeader.vue`
- Create: `frontend/src/components/common/MarkdownViewer.vue`
- Create: `frontend/src/components/common/PayloadViewer.vue`

**Interfaces:**
- Produces:
  - `DataChip` props: `label: string`, `value: string | number`, `tone?: "blue" | "green" | "yellow" | "red" | "muted"`, `title?: string`.
  - `StatusDot` props: `label: string`, `tone?: "blue" | "green" | "yellow" | "red" | "muted"`.
  - `SectionHeader` props: `title: string`, `subtitle?: string`, `count?: string | number`, `statusLabel?: string`, `statusTone?: "blue" | "green" | "yellow" | "red" | "muted"`.
  - `MarkdownViewer` props: `content: string`.
  - `PayloadViewer` props: `value?: unknown`, `text?: string`, `mode?: PayloadViewMode`, `emptyText?: string`, `copyLabel?: string`, `expandLabel?: string`, `collapseLabel?: string`, `maxCollapsedHeight?: number`.

- [ ] **Step 1: Implement shortcuts**

Add these shortcuts in `frontend/uno.config.ts`:

```ts
'ag-data-chip':
  'inline-flex min-w-0 max-w-full items-center gap-1.5 rounded-[var(--ag-radius-control)] border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] px-2 py-[5px] text-[11px] leading-none text-[var(--ag-muted-strong)]',
'ag-status-dot':
  'inline-block size-2 shrink-0 rounded-full bg-[var(--ag-muted)] ring-2 ring-[var(--ag-panel)]',
'ag-section-header':
  'flex min-w-0 items-start justify-between gap-3 border-b border-[var(--ag-border)] pb-2',
'ag-surface-row':
  'min-w-0 rounded-[var(--ag-radius-panel)] border border-[var(--ag-border)] bg-[var(--ag-panel)] p-3 transition-colors hover:border-[color-mix(in_srgb,var(--ag-blue)_38%,var(--ag-border))] hover:bg-[var(--ag-blue-soft)]',
'ag-field-label':
  'text-[11px] font-760 uppercase tracking-[0.08em] text-[var(--ag-muted)]',
'ag-code-panel':
  'min-w-0 overflow-hidden rounded-[var(--ag-radius-panel)] border border-[var(--ag-border)] bg-[var(--ag-code-bg)] text-[var(--ag-code-text)]',
'ag-empty-compact':
  'grid min-h-[88px] place-items-center rounded-[var(--ag-radius-panel)] border border-dashed border-[var(--ag-border)] bg-[var(--ag-panel-soft)] px-4 py-3 text-center text-xs text-[var(--ag-muted)]',
```

- [ ] **Step 2: Implement components**

Create the five common components with typed props, shared shortcuts, and no page-local class dependencies. `MarkdownViewer.vue` may keep a small scoped style block for rich content typography because Markdown child selectors are content-specific. `PayloadViewer.vue` must use utility classes plus `MarkdownViewer` and `copyToClipboard`.

- [ ] **Step 3: Run focused verification**

Run: `cd frontend && bun run test:shell`

Expected: PASS for the updated source-contract suite.

- [ ] **Step 4: Commit**

```bash
git add frontend/uno.config.ts frontend/src/components/common frontend/src/modules/utilityFirstPrimitivesSourceContracts.test.mjs frontend/src/modules/testSource.mjs
git commit -m "feat: add shared atomic viewer primitives"
```

### Task 3: Memory Workbench Modularization

**Files:**
- Modify: `frontend/src/components/MemoryControl.vue`
- Create: `frontend/src/components/memory/MemoryQueryPanel.vue`
- Create: `frontend/src/components/memory/MemoryUserQueue.vue`
- Create: `frontend/src/components/memory/MemoryListPanel.vue`
- Create: `frontend/src/components/memory/MemoryDetailPanel.vue`
- Create: `frontend/src/components/memory/MemoryEditDialog.vue`
- Create: `frontend/src/composables/useMemoryWorkbenchController.ts`
- Modify: `frontend/src/modules/surfaceLayoutSourceContracts.test.mjs`

**Interfaces:**
- Consumes: `DataChip`, `StatusDot`, `SectionHeader`, `PayloadViewer`, `EmptyState`, `PanelHeader`.
- Produces: `useMemoryWorkbenchController()` returning all existing Memory page state, derived labels, permissions, and action methods currently owned by `MemoryControl.vue`.

- [ ] **Step 1: Write failing source-contracts**

Replace old Memory DOM/class assertions in `surfaceLayoutSourceContracts.test.mjs` with checks that `MemoryControl.vue` imports the five memory child components, imports `useMemoryWorkbenchController`, and does not define duplicate local chip/status/empty/header CSS:

```js
for (const component of [
  "MemoryQueryPanel",
  "MemoryUserQueue",
  "MemoryListPanel",
  "MemoryDetailPanel",
  "MemoryEditDialog",
]) {
  assert.match(memoryControl, new RegExp(`import ${component} from "\\./memory/${component}\\.vue"`), `Memory page must import ${component}`)
}
assert.match(memoryControl, /useMemoryWorkbenchController/, "Memory page must delegate state to useMemoryWorkbenchController")
assert.doesNotMatch(memoryControl, /\.memory-context-chip\s*\{/, "Memory page must not keep local context chip CSS")
assert.doesNotMatch(memoryControl, /\.memory-empty-state\s*\{/, "Memory page must not keep local empty state CSS")
```

- [ ] **Step 2: Verify red**

Run: `cd frontend && bun run test:shell`

Expected: FAIL because Memory child components and controller do not exist.

- [ ] **Step 3: Extract controller and panels**

Move Memory API orchestration, filters, pagination, permission checks, edit/delete state, source input rendering mode, and labels into `useMemoryWorkbenchController.ts`. Move template regions into the five child components. Use `PayloadViewer` for source input and metadata payloads.

- [ ] **Step 4: Verify green**

Run: `cd frontend && bun run test:shell`

Expected: PASS.

### Task 4: Agent Evals Modularization

**Files:**
- Modify: `frontend/src/components/AgentEvals.vue`
- Create: `frontend/src/components/evals/AgentEvalsCommandBar.vue`
- Create: `frontend/src/components/evals/EvalCasesTab.vue`
- Create: `frontend/src/components/evals/EvalRunsTab.vue`
- Create: `frontend/src/components/evals/EvalFailuresTab.vue`
- Create: `frontend/src/components/evals/EvalTrendsPanel.vue`
- Create: `frontend/src/components/evals/AgentEvalDetailPanel.vue`
- Create: `frontend/src/composables/useAgentEvalsWorkbench.ts`
- Modify: `frontend/src/modules/agentEvalTraceSourceContracts.test.mjs`

**Interfaces:**
- Consumes: `DataChip`, `StatusDot`, `SectionHeader`, `PayloadViewer`, `MetricChip`, `StatusChip`.
- Produces: `useAgentEvalsWorkbench()` returning suites, cases, runs, failures, trends, active tabs, selection state, and mutating actions currently in `AgentEvals.vue`.

- [ ] **Step 1: Write failing source-contracts**

Add assertions that `AgentEvals.vue` imports all eval child components and `useAgentEvalsWorkbench`, and does not keep local chip/status/header duplication.

- [ ] **Step 2: Verify red**

Run: `cd frontend && bun run test:shell`

Expected: FAIL because eval child components and controller do not exist.

- [ ] **Step 3: Extract controller and tabs**

Move API orchestration into `useAgentEvalsWorkbench.ts`. Split command bar, cases, runs, failures, trends, and details into child components. Use `PayloadViewer` for payload/result blocks.

- [ ] **Step 4: Verify green**

Run: `cd frontend && bun run test:shell`

Expected: PASS.

### Task 5: Settings Workbench Modularization

**Files:**
- Modify: `frontend/src/components/Settings.vue`
- Create: `frontend/src/components/settings/SettingsRuntimePanel.vue`
- Create: `frontend/src/components/settings/SettingsModelPanel.vue`
- Create: `frontend/src/components/settings/SettingsNavigationPanel.vue`
- Create: `frontend/src/composables/useSettingsNavigationLayout.ts`
- Modify: `frontend/src/modules/navigationSettingsSourceContracts.test.mjs`

**Interfaces:**
- Consumes: `SectionHeader`, `DataChip`, `StatusDot`, `EmptyState`.
- Produces: `useSettingsNavigationLayout()` returning grouped navigation state, active settings section, runtime/model loading states, and update methods.

- [ ] **Step 1: Write failing source-contracts**

Add assertions that `Settings.vue` imports the three settings child components and `useSettingsNavigationLayout`, and removes duplicated local card/chip/header styles that match shared primitives.

- [ ] **Step 2: Verify red**

Run: `cd frontend && bun run test:shell`

Expected: FAIL because settings child components and layout composable do not exist.

- [ ] **Step 3: Extract settings panels**

Move runtime status, model configuration, and navigation settings into focused components. Keep Element Plus form bindings in the child panel that owns the form.

- [ ] **Step 4: Verify green**

Run: `cd frontend && bun run test:shell`

Expected: PASS.

### Task 6: Workflow Builder Modularization

**Files:**
- Modify: `frontend/src/components/Workflow.vue`
- Create: `frontend/src/components/workflow/WorkflowPalette.vue`
- Create: `frontend/src/components/workflow/WorkflowCanvas.vue`
- Create: `frontend/src/components/workflow/WorkflowInspector.vue`
- Create: `frontend/src/components/workflow/WorkflowStepCard.vue`
- Modify: `frontend/src/modules/workflowBuilder.test.mjs`
- Modify: `frontend/src/modules/utilityFirstPrimitivesSourceContracts.test.mjs`

**Interfaces:**
- Consumes: `DataChip`, `StatusDot`, `SectionHeader`, `PayloadViewer`, existing `workflowBuilder.ts` helpers.
- Produces: Workflow page shell that imports the four child components and keeps builder state compatible with existing `workflowBuilder.test.mjs`.

- [ ] **Step 1: Write failing source-contracts**

Add assertions that `Workflow.vue` imports the four workflow child components and removes duplicated local metric/status/empty/header CSS.

- [ ] **Step 2: Verify red**

Run: `cd frontend && bun run test:shell`

Expected: FAIL because workflow child components do not exist.

- [ ] **Step 3: Extract builder UI**

Move step palette, canvas/list, selected step inspector, and repeated step card markup into the four child components. Keep algorithmic helpers in `workflowBuilder.ts`.

- [ ] **Step 4: Verify green**

Run: `cd frontend && bun run test:shell`

Expected: PASS.

### Task 7: Chat Modularization

**Files:**
- Modify: `frontend/src/components/Chat.vue`
- Create: `frontend/src/components/chat/ChatMessageList.vue`
- Create: `frontend/src/components/chat/ChatMessageCard.vue`
- Create: `frontend/src/components/chat/ChatComposer.vue`
- Create: `frontend/src/components/chat/ChatModelSelect.vue`
- Create: `frontend/src/composables/useChatScrollState.ts`
- Create: `frontend/src/composables/useChatMarkdownRenderer.ts`
- Modify: `frontend/src/modules/shellCoreSourceContracts.test.mjs`

**Interfaces:**
- Consumes: `MarkdownViewer`, `PayloadViewer`, `StatusDot`, `DataChip`.
- Produces:
  - `useChatMarkdownRenderer()` centralizes markdown rendering, inline table normalization, code copy enhancement, and image zoom binding.
  - `useChatScrollState()` centralizes bottom detection, scroll-to-bottom, and sticky streaming scroll behavior.

- [ ] **Step 1: Write failing source-contracts**

Add assertions that `Chat.vue` imports the four chat child components and both chat composables, that markdown rendering no longer lives directly in `Chat.vue`, and that complex Markdown display uses `MarkdownViewer`.

- [ ] **Step 2: Verify red**

Run: `cd frontend && bun run test:shell`

Expected: FAIL because chat child components and composables do not exist.

- [ ] **Step 3: Extract markdown and scroll composables**

Move `MarkdownIt` setup, inline table normalization, code-copy enhancement, image zoom binding, bottom detection, and scroll actions out of `Chat.vue`.

- [ ] **Step 4: Extract chat child components**

Move message list, message card, composer, and model select into child components while preserving streaming, copy, raw run copy, source/thinking collapse, model loading, session events, and blocked-content handling.

- [ ] **Step 5: Verify green**

Run: `cd frontend && bun run test:shell`

Expected: PASS.

### Task 8: Style Debt Sweep and Visual Verification

**Files:**
- Modify: `frontend/src/components/MCP.vue`
- Modify: `frontend/src/components/Dashboard.vue`
- Modify: `frontend/src/components/knowledge/*`
- Modify: `frontend/src/styles/page-workbench.css`
- Modify: related source-contract tests

**Interfaces:**
- Consumes: all shared primitives from Tasks 1-2.
- Produces: removal of remaining repeated chip/status/empty/header CSS where shared primitives are clearer.

- [ ] **Step 1: Write source-contract sweep checks**

Add assertions that remaining pages do not define duplicated local chip/status/empty/header CSS when they can import shared common primitives.

- [ ] **Step 2: Verify red when duplicate CSS still exists**

Run: `cd frontend && bun run test:shell`

Expected: FAIL for duplicated local style rules that the sweep will remove.

- [ ] **Step 3: Replace repeated styles**

Use `DataChip`, `StatusDot`, `SectionHeader`, `EmptyState`, `PanelHeader`, and UnoCSS shortcuts in MCP, Dashboard, Knowledge children, and page workbench surfaces.

- [ ] **Step 4: Run full frontend verification**

Run:

```bash
cd frontend && bun run test:shell
cd frontend && bun run test:auth
cd frontend && bun run build
```

Expected: all commands exit 0.

- [ ] **Step 5: Run visual verification**

Start the app:

```bash
cd frontend && bun run dev -- --host 0.0.0.0
```

Use Playwright at `1920x1080` for Memory, Agent Evals, Settings, Workflow, Chat, MCP, Dashboard, and Knowledge. Capture narrow viewport screenshots for Memory, Agent Evals, Workflow, and Chat because their panel layouts are highest risk. Fix any obvious overlap, clipped text, or unusable controls before completion.
