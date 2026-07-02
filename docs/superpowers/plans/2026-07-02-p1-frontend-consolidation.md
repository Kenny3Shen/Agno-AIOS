# P1 Frontend Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove confirmed dead code, centralize shared frontend state, add design tokens and i18n, and refresh docs without weakening the P0 security guarantees.

**Architecture:** Keep the active Vue 3 frontend and FastAPI backend. Add Pinia stores around shell/auth/session/trace state, add vue-i18n for Chinese and English UI text, and consolidate surface styling through CSS tokens consumed by existing components.

**Tech Stack:** Vue 3, TypeScript, Vite/Rolldown, Element Plus, UnoCSS, Pinia, vue-i18n, markdown-it, Mermaid, FastAPI, uv, ruff, ty.

## Global Constraints

- Work in `/home/shenss/python/Agno-AIOS` on `master`; the former `security-first-rbac` worktree has been fast-forward merged.
- Do not edit generated `source/assets/*` directly.
- Do not delete active code unless `rg` shows no active runtime reference and `npm run build` passes after deletion.
- Keep Chinese as the default UI locale.
- Preserve backend RBAC and user isolation behavior from P0.
- Use `uv run ruff check .` and `uv run ty check .` after Python changes and during final verification.
- Use Playwright CLI after frontend/backend changes.

---

## File Structure

### Create

- `frontend/src/stores/auth.ts`: authenticated user, role-derived permission helpers, login/logout mutation points.
- `frontend/src/stores/shell.ts`: active module, sidebar state, theme, locale, compact mode.
- `frontend/src/stores/sessions.ts`: chat session list, current session id, loading/error state.
- `frontend/src/stores/traces.ts`: trace queue, selected trace id, trace filters, loading/error state.
- `frontend/src/i18n/index.ts`: vue-i18n setup and locale switching helper.
- `frontend/src/i18n/locales/zh-CN.ts`: Chinese messages.
- `frontend/src/i18n/locales/en-US.ts`: English messages.
- `frontend/src/styles/tokens.css`: shared CSS variables for surface, border, radius, padding, shadow, and semantic colors.

### Modify

- `frontend/src/main.ts`: install Pinia and i18n, import design tokens before app styles.
- `frontend/src/App.vue`: consume stores/i18n for shell/auth/session/trace state and top-level copy.
- `frontend/src/components/AuthScreen.vue`: consume i18n text and auth store handoff.
- `frontend/src/components/Chat.vue`: consume shared session state and i18n for common labels/toasts.
- `frontend/src/components/Trace.vue`: consume trace store filters and i18n for common labels/toasts.
- `frontend/src/components/MCP.vue`: consume tokenized panel styling and i18n for common labels/toasts.
- `frontend/src/components/Skills.vue`: consume tokenized panel styling and i18n for common labels/toasts.
- `frontend/src/style.css`: reduce repeated panel/surface values after `tokens.css` exists.
- `frontend/package.json`: add `pinia` and `vue-i18n`, remove dependencies only when unused.
- `frontend/bun.lock`: update through Bun dependency commands.
- `README.md`: remove stale `frontend-react/` description and document Bun/Pinia/i18n.
- `AGENTS.md`: document the active frontend package manager and verification commands.

### Delete When Verified Unused

- `frontend-react/`
- `frontend/src/assets/vue.svg`
- `frontend/src/composables/useMessage.ts`
- `frontend/src/composables/useDebounce.ts`

---

### Task 1: Cleanup Audit and Dead-Code Deletion

**Files:**
- Delete: `frontend-react/`
- Delete: `frontend/src/assets/vue.svg`
- Delete: `frontend/src/composables/useMessage.ts`
- Delete: `frontend/src/composables/useDebounce.ts`
- Modify: `README.md`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: current package scripts in `frontend/package.json`.
- Produces: a Vue-only repository structure with no active import references to deleted files.

- [ ] **Step 1: Confirm active references before deleting**

Run:

```bash
rg -n "frontend-react|useMessage|useDebounce|vue\\.svg" \
  --glob '!frontend/node_modules/**' \
  --glob '!source/assets/**' \
  --glob '!api/data/**' \
  --glob '!logs/**' .
```

Expected:

- `frontend-react` appears only in docs or README text.
- `useMessage`, `useDebounce`, and `vue.svg` have no active imports in `frontend/src`.

- [ ] **Step 2: Remove verified dead code**

Run:

```bash
git rm -r frontend-react
git rm frontend/src/assets/vue.svg frontend/src/composables/useMessage.ts frontend/src/composables/useDebounce.ts
```

Expected: only the verified dead-code paths are staged as deletions.

- [ ] **Step 3: Update repository documentation**

Edit `README.md`:

```text
Remove the frontend-react tree entry.
Change frontend package manager text from npm to Bun where installation commands are shown.
Add a short note that Pinia and vue-i18n are the standard frontend state/copy foundations.
```

Edit `AGENTS.md`:

```text
Record that frontend dependencies are managed from frontend/ with Bun when changing frontend/package.json.
Keep npm script commands valid for existing test/build scripts unless scripts are renamed.
```

- [ ] **Step 4: Verify cleanup**

Run:

```bash
cd frontend
npm run test:shell
npm run test:auth
npm run build
```

Expected: all commands pass.

- [ ] **Step 5: Commit cleanup**

Run:

```bash
git status --short
git add README.md AGENTS.md frontend
git commit -m "chore: remove unused frontend code"
```

Expected: one cleanup commit with only verified dead-code and docs changes.

---

### Task 2: Add Pinia and Centralize Shared State

**Files:**
- Create: `frontend/src/stores/auth.ts`
- Create: `frontend/src/stores/shell.ts`
- Create: `frontend/src/stores/sessions.ts`
- Create: `frontend/src/stores/traces.ts`
- Modify: `frontend/src/main.ts`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/components/Chat.vue`
- Modify: `frontend/src/components/Trace.vue`
- Modify: `frontend/package.json`
- Modify: `frontend/bun.lock`

**Interfaces:**
- Produces: `useAuthStore()`, `useShellStore()`, `useSessionStore()`, `useTraceStore()`.
- Consumes: existing `User`, `ChatSession`, `TraceRecord`, and API helpers from `frontend/src/types/index.ts` and `frontend/src/composables/useApi.ts`.

- [ ] **Step 1: Add Pinia**

Run:

```bash
cd frontend
/home/shenss/.bun/bin/bun add pinia
```

Expected: `frontend/package.json` contains `pinia` and `frontend/bun.lock` is updated.

- [ ] **Step 2: Install Pinia in the Vue app**

Modify `frontend/src/main.ts` with this structure:

```ts
import { createPinia } from "pinia"

const app = createApp(App)
app.use(createPinia())
app.use(ElementPlus, { locale: zhCn })
```

Expected: app plugins install before component registration and mount.

- [ ] **Step 3: Create auth store**

Create `frontend/src/stores/auth.ts`:

```ts
import { computed, ref } from "vue"
import { defineStore } from "pinia"
import type { User } from "../types"

export type UserRole = "admin" | "user" | "guest"

export const useAuthStore = defineStore("auth", () => {
  const currentUser = ref<User | null>(null)
  const authBooting = ref(true)
  const userMenuOpen = ref(false)

  const role = computed<UserRole>(() => currentUser.value?.role ?? "guest")
  const canWrite = computed(() => role.value !== "guest")
  const canAdmin = computed(() => role.value === "admin")

  function setCurrentUser(user: User | null) {
    currentUser.value = user
  }

  function setAuthBooting(value: boolean) {
    authBooting.value = value
  }

  function setUserMenuOpen(value: boolean) {
    userMenuOpen.value = value
  }

  return {
    currentUser,
    authBooting,
    userMenuOpen,
    role,
    canWrite,
    canAdmin,
    setCurrentUser,
    setAuthBooting,
    setUserMenuOpen,
  }
})
```

- [ ] **Step 4: Create shell store**

Create `frontend/src/stores/shell.ts`:

```ts
import { computed, ref } from "vue"
import { defineStore } from "pinia"

export type LocaleCode = "zh-CN" | "en-US"

export const useShellStore = defineStore("shell", () => {
  const activeTab = ref("home")
  const isDark = ref(true)
  const sidebarOpen = ref(false)
  const isSidebarCompact = ref(false)
  const chatSessionsExpanded = ref(true)
  const traceQueueExpanded = ref(true)
  const locale = ref<LocaleCode>("zh-CN")

  const shellThemeClass = computed(() => (isDark.value ? "dark" : "light"))

  function setActiveTab(tab: string) {
    activeTab.value = tab
  }

  function toggleTheme() {
    isDark.value = !isDark.value
  }

  function setLocale(value: LocaleCode) {
    locale.value = value
    document.documentElement.lang = value
  }

  return {
    activeTab,
    isDark,
    sidebarOpen,
    isSidebarCompact,
    chatSessionsExpanded,
    traceQueueExpanded,
    locale,
    shellThemeClass,
    setActiveTab,
    toggleTheme,
    setLocale,
  }
})
```

- [ ] **Step 5: Create session and trace stores**

Create `frontend/src/stores/sessions.ts` and `frontend/src/stores/traces.ts` with ref state plus setter methods. Keep network calls in existing API helpers during this task, unless moving a call removes duplicated page code.

Required session exports:

```ts
export const useSessionStore = defineStore("sessions", () => ({
  chatSessions,
  currentChatSessionId,
  loadingSessions,
  sessionError,
  setChatSessions,
  setCurrentChatSessionId,
  setLoadingSessions,
  setSessionError,
}))
```

Required trace exports:

```ts
export const useTraceStore = defineStore("traces", () => ({
  traceQueueItems,
  currentTraceId,
  loadingTraceQueue,
  traceFilters,
  traceError,
  setTraceQueueItems,
  setCurrentTraceId,
  setLoadingTraceQueue,
  setTraceFilters,
  setTraceError,
}))
```

- [ ] **Step 6: Refactor `App.vue` to consume stores**

Move these App-local refs to stores:

```ts
currentUser
authBooting
userMenuOpen
activeTab
isDark
sidebarOpen
isSidebarCompact
chatSessionsExpanded
traceQueueExpanded
chatSessions
currentChatSessionId
loadingSessions
traceQueueItems
currentTraceId
loadingTraceQueue
```

Keep DOM-only refs such as resize state and dropdown element refs in `App.vue`.

- [ ] **Step 7: Verify state refactor**

Run:

```bash
cd frontend
npm run test:shell
npm run test:auth
npm run build
```

Expected: all commands pass and TypeScript reports no missing store properties.

- [ ] **Step 8: Commit Pinia state foundation**

Run:

```bash
git add frontend/src/main.ts frontend/src/App.vue frontend/src/components/Chat.vue frontend/src/components/Trace.vue frontend/src/stores frontend/package.json frontend/bun.lock
git commit -m "feat: centralize frontend shell state"
```

Expected: one commit with Pinia setup and shared state migration.

---

### Task 3: Add i18n Foundation

**Files:**
- Create: `frontend/src/i18n/index.ts`
- Create: `frontend/src/i18n/locales/zh-CN.ts`
- Create: `frontend/src/i18n/locales/en-US.ts`
- Modify: `frontend/src/main.ts`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/components/AuthScreen.vue`
- Modify: `frontend/src/components/Chat.vue`
- Modify: `frontend/src/components/Trace.vue`
- Modify: `frontend/src/components/MCP.vue`
- Modify: `frontend/src/components/Skills.vue`
- Modify: `frontend/package.json`
- Modify: `frontend/bun.lock`

**Interfaces:**
- Produces: `i18n`, `setI18nLocale(locale: LocaleCode)`, and locale dictionaries keyed by stable dot paths.
- Consumes: `useShellStore().locale`.

- [ ] **Step 1: Add vue-i18n**

Run:

```bash
cd frontend
/home/shenss/.bun/bin/bun add vue-i18n
```

Expected: `frontend/package.json` contains `vue-i18n` and lockfile changes are limited to dependency resolution.

- [ ] **Step 2: Create locale dictionaries**

Create message keys for:

```ts
shell.brand
shell.authChecking
shell.nav.*
shell.sessions.*
shell.traces.*
common.actions.*
common.status.*
auth.*
chat.*
trace.*
mcp.*
skills.*
```

The Chinese file must preserve the current default labels. The English file must use concise product UI labels.

- [ ] **Step 3: Install i18n**

Modify `frontend/src/main.ts`:

```ts
import { i18n } from "./i18n"

app.use(createPinia())
app.use(i18n)
app.use(ElementPlus, { locale: zhCn })
```

- [ ] **Step 4: Add locale switching to shell**

In `App.vue`, render a compact language toggle in the top bar:

```vue
<el-segmented
  v-model="selectedLocale"
  :options="localeOptions"
  size="small"
/>
```

Wire `selectedLocale` to `shellStore.setLocale()` and `setI18nLocale()`.

- [ ] **Step 5: Migrate high-value copy**

Replace direct string literals in the shell, Auth, Chat, Trace, MCP, and Skills for common labels, actions, toasts, empty states, and error text with `t("key.path")`.

Keep API data, model names, trace ids, session ids, and user-provided text untranslated.

- [ ] **Step 6: Verify i18n**

Run:

```bash
cd frontend
npm run test:shell
npm run test:auth
npm run build
```

Expected: all commands pass, default UI remains Chinese, and locale switching changes migrated copy.

- [ ] **Step 7: Commit i18n foundation**

Run:

```bash
git add frontend/src/main.ts frontend/src/App.vue frontend/src/components/AuthScreen.vue frontend/src/components/Chat.vue frontend/src/components/Trace.vue frontend/src/components/MCP.vue frontend/src/components/Skills.vue frontend/src/i18n frontend/package.json frontend/bun.lock
git commit -m "feat: add frontend i18n foundation"
```

---

### Task 4: Consolidate Design Tokens

**Files:**
- Create: `frontend/src/styles/tokens.css`
- Modify: `frontend/src/main.ts`
- Modify: `frontend/src/style.css`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/components/Chat.vue`
- Modify: `frontend/src/components/Trace.vue`
- Modify: `frontend/src/components/MCP.vue`
- Modify: `frontend/src/components/Skills.vue`

**Interfaces:**
- Produces: CSS custom properties under `:root` and `.dark`.
- Consumes: existing component class names.

- [ ] **Step 1: Create token stylesheet**

Create `frontend/src/styles/tokens.css` with:

```css
:root {
  --ag-bg-app: #eef3f7;
  --ag-bg-panel: #ffffff;
  --ag-bg-panel-muted: #f7fafc;
  --ag-border-default: #c2d0dc;
  --ag-border-strong: #8aa1b2;
  --ag-radius-panel: 8px;
  --ag-radius-control: 6px;
  --ag-space-md: 16px;
  --ag-shadow-panel: 0 16px 40px rgba(15, 23, 42, 0.12);
}

.dark {
  --ag-bg-app: #071014;
  --ag-bg-panel: #0e171f;
  --ag-bg-panel-muted: #111d26;
  --ag-border-default: #20313d;
  --ag-border-strong: #335166;
  --ag-shadow-panel: 0 16px 40px rgba(0, 0, 0, 0.34);
}
```

- [ ] **Step 2: Import tokens before app styles**

Modify `frontend/src/main.ts`:

```ts
import "./styles/tokens.css"
import "./style.css"
```

- [ ] **Step 3: Replace repeated shell and panel values**

Update shell/right-panel/component CSS to use:

```css
background: var(--ag-bg-panel);
border: 1px solid var(--ag-border-default);
border-radius: var(--ag-radius-panel);
box-shadow: var(--ag-shadow-panel);
```

Apply first to Chat, Trace, MCP, Skills, and global shell classes that currently duplicate these values.

- [ ] **Step 4: Verify visual and build behavior**

Run:

```bash
cd frontend
npm run test:shell
npm run build
```

Use Playwright CLI to capture dark and light mode screenshots for Chat, Trace, MCP, and Skills.

Expected: light-mode Skills panel has a visible border, right-side panels share the same tone model, and no text overlaps.

- [ ] **Step 5: Commit design token consolidation**

Run:

```bash
git add frontend/src/main.ts frontend/src/style.css frontend/src/styles frontend/src/App.vue frontend/src/components/Chat.vue frontend/src/components/Trace.vue frontend/src/components/MCP.vue frontend/src/components/Skills.vue
git commit -m "style: consolidate frontend design tokens"
```

---

### Task 5: Dependency and Documentation Finalization

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/bun.lock`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/agent-os-control-plane.md`

**Interfaces:**
- Consumes: final package graph after Tasks 1-4.
- Produces: current docs and dependency metadata.

- [ ] **Step 1: Audit unused dependencies**

Run:

```bash
rg -n "markdown-it|highlight\\.js|mermaid|element-plus|@element-plus/icons-vue|unocss|pinia|vue-i18n" frontend/src frontend/*.config.* frontend/package.json
```

Expected: each dependency in `frontend/package.json` has a live runtime, test, or build reference.

- [ ] **Step 2: Apply low-risk dependency cleanup**

If a dependency has no live reference, remove it with:

```bash
cd frontend
/home/shenss/.bun/bin/bun remove <package-name>
```

Expected: no package is removed unless the audit shows zero live references and build passes.

- [ ] **Step 3: Update docs**

Update:

```text
README.md: active frontend stack, Bun install command, Pinia state layer, vue-i18n locale layer, no frontend-react tree.
AGENTS.md: WSL2 Ubuntu 24.04, uv/ruff/ty, Bun dependency management, npm scripts for frontend checks, Playwright CLI validation.
docs/agent-os-control-plane.md: mention that shell state and locale state are centralized and right-panel copy is reduced.
```

- [ ] **Step 4: Run final verification**

Run:

```bash
uv run ruff check .
uv run ty check .
cd frontend
npm run test:shell
npm run test:auth
npm run build
```

Run Playwright CLI against the built or dev frontend:

```text
Validate login shell, theme toggle, locale toggle, Chat streaming surfaces, code-copy button, Trace session_id filter, MCP panel, Skills panel, and clipboard fallback.
```

Expected: all command checks pass and Playwright console has no application errors.

- [ ] **Step 5: Commit final docs/dependency pass**

Run:

```bash
git add README.md AGENTS.md docs/agent-os-control-plane.md frontend/package.json frontend/bun.lock source/index.html source/assets
git commit -m "docs: update frontend consolidation guidance"
```

Expected: final commit documents the active architecture and regenerated build output when present.
