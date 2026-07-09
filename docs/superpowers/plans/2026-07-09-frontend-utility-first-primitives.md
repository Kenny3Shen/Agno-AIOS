# Frontend Utility-First Primitives Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce reusable UnoCSS and Vue presentation primitives, then migrate `Skills.vue` and `Workflow.vue` away from repeated scoped CSS.

**Architecture:** Shared styling moves into UnoCSS shortcuts and small common components. The target pages keep their existing data flow and replace duplicated presentation markup with common primitives.

**Tech Stack:** Vue 3 SFC, TypeScript, UnoCSS, Element Plus, Bun test scripts.

## Global Constraints

- Do not change `frontend/package.json`.
- Use existing Vue, Element Plus, and UnoCSS stack.
- Keep changes behavior-neutral.
- Do not migrate `Knowledge.vue`, `Chat.vue`, `MemoryControl.vue`, or shell pages in this pass.

---

### Task 1: Source Contract Test

**Files:**
- Create: `frontend/src/modules/utilityFirstPrimitivesSourceContracts.test.mjs`

**Interfaces:**
- Consumes: existing source files as text.
- Produces: failing checks that require shared shortcuts and common primitives.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/modules/utilityFirstPrimitivesSourceContracts.test.mjs` with checks for `ag-metric-chip`, `ag-status-chip`, `MetricChip.vue`, `StatusChip.vue`, `EmptyState.vue`, `PanelHeader.vue`, and usage in `Skills.vue` / `Workflow.vue`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && bun run test:shell`

Expected: FAIL because the new common components and shortcuts do not exist yet.

### Task 2: UnoCSS Shortcuts and Common Components

**Files:**
- Modify: `frontend/uno.config.ts`
- Create: `frontend/src/components/common/MetricChip.vue`
- Create: `frontend/src/components/common/StatusChip.vue`
- Create: `frontend/src/components/common/EmptyState.vue`
- Create: `frontend/src/components/common/PanelHeader.vue`

**Interfaces:**
- Produces:
  - `MetricChip` props: `label: string`, `value: string | number`, `tone?: "blue" | "green" | "yellow" | "red" | "muted"`.
  - `StatusChip` props: `tone?: "blue" | "green" | "yellow" | "red" | "muted"`.
  - `EmptyState` props: `loading?: boolean`, `icon?: Component`.
  - `PanelHeader` props: `title: string`, `subtitle?: string`.

- [ ] **Step 1: Implement shortcuts**

Add shortcuts for metric chips, status chips, empty states, icon buttons, and panel headers using existing `--ag-*` tokens.

- [ ] **Step 2: Implement common components**

Create the four SFCs using utility classes and slots.

- [ ] **Step 3: Run source contract test**

Run: `cd frontend && bun run test:shell`

Expected: still FAIL until page usage is migrated.

### Task 3: Migrate Low-Risk Pages

**Files:**
- Modify: `frontend/src/components/Skills.vue`
- Modify: `frontend/src/components/Workflow.vue`

**Interfaces:**
- Consumes: common components from Task 2.
- Produces: behavior-equivalent pages using shared primitives.

- [ ] **Step 1: Replace repeated metric/status/empty markup**

Use `MetricChip`, `StatusChip`, `EmptyState`, and utility shortcuts in `Skills.vue` and `Workflow.vue`.

- [ ] **Step 2: Remove obsolete scoped CSS blocks**

Delete duplicated `.skill-context-chip`, `.workflow-context-chip`, and `.skills-state` style rules that are replaced by common primitives.

- [ ] **Step 3: Verify tests and build**

Run:

```bash
cd frontend && bun run test:shell
cd frontend && bun run build
```

Expected: both commands pass.
