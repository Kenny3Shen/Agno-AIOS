# API Composables Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the aggregate frontend API surface into real same-level domain modules without adding empty nesting.

**Architecture:** Shared request/error helpers live in `useApiCore.ts`. Each domain composable file owns its current endpoint logic. Pages import the domain composable they use directly; there is no aggregate API barrel.

**Tech Stack:** Vue 3 Composition API, TypeScript, Vite, Bun source-contract tests.

## Global Constraints

- No nested API module directories in this step.
- No pass-through domain wrapper files.
- Components import domain composables directly.
- Endpoint paths, payload shapes, loading/error refs, and fallback messages remain unchanged.

---

### Task 1: Add Source Contract

**Files:**
- Create: `frontend/src/modules/apiComposablesSourceContracts.test.mjs`
- Modify: `frontend/src/modules/testSource.mjs`
- Modify: `frontend/src/uiShell.test.mjs`

**Interfaces:**
- Produces: source-contract coverage for domain composable files and direct page imports.

- [x] **Step 1: Write failing source-contract test**

Run: `cd frontend && /home/shenss/.bun/bin/bun run test:shell`

Expected: FAIL because `composables/useApiCore.ts` does not exist.

### Task 2: Split API Composable Modules

**Files:**
- Create: `frontend/src/composables/useApiCore.ts`
- Create: `frontend/src/composables/useSecurityDataApi.ts`
- Create: `frontend/src/composables/useChatApi.ts`
- Create: `frontend/src/composables/useMemoryControlApi.ts`
- Create: `frontend/src/composables/useApprovalsApi.ts`
- Create: `frontend/src/composables/useSchedulerApi.ts`
- Create: `frontend/src/composables/useSettingsApi.ts`
- Create: `frontend/src/composables/useTraceApi.ts`
- Create: `frontend/src/composables/useSkillsApi.ts`
- Create: `frontend/src/composables/useMcpApi.ts`
- Create: `frontend/src/composables/useKnowledgeApi.ts`
- Create: `frontend/src/composables/useAgentEvalsApi.ts`
- Delete: `frontend/src/composables/useApi.ts`

**Interfaces:**
- Consumes: existing hook signatures from the aggregate API file.
- Produces: same hook names exported from domain modules and imported directly by pages.

- [x] **Step 1: Move shared helpers**

Move `ApiFallbackKey`, `useApiMessage`, `messageFromUnknown`, `messageFromResponse`, and `cleanParam` into `useApiCore.ts`.

- [x] **Step 2: Move domain hooks**

Move each existing hook body into its domain file with only the imports it needs.

- [x] **Step 3: Remove `useApi.ts`**

Delete the aggregate API barrel and update pages to import the domain composable they use.

- [x] **Step 4: Verify source contract passes**

Run: `cd frontend && /home/shenss/.bun/bin/bun run test:shell`

Expected: PASS.

### Task 3: Verification

**Files:**
- All files above.

**Interfaces:**
- Produces: verified no-empty-nesting split.

- [x] **Step 1: Type/build verification**

Run:

```bash
cd frontend
/home/shenss/.bun/bin/bun run test:shell
/home/shenss/.bun/bin/bun run test:auth
/home/shenss/.bun/bin/bun run build
```

- [x] **Step 2: Diff hygiene**

Run: `git diff --check`

Expected: no output.
