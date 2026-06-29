# Frontend Vue Security Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch Agno AIOS back to the Vue frontend, add registration/login, refine the shell into an AI information-security middle platform, update Markdown docs, verify, and commit.

**Architecture:** Add a focused auth client and auth screen, then gate the existing Vue workspace in `App.vue`. Keep existing module components intact while improving the global shell, navigation taxonomy, copy, and operational metrics.

**Tech Stack:** Vue 3, Vite, TypeScript, Element Plus, UnoCSS, FastAPI Users JWT auth, Node/Fish environment, uv/ruff/ty, Playwright.

---

## File Structure

- Create `frontend/src/lib/authClient.ts`: auth API client and token storage helpers.
- Create `frontend/src/lib/authClient.test.mjs`: Node-compatible tests that verify auth endpoint shapes and storage behavior.
- Create `frontend/src/components/AuthScreen.vue`: login/register UI with OAuth provider discovery and security-middle-platform visual signature.
- Modify `frontend/src/types/index.ts`: add auth user, token, and OAuth provider types.
- Modify `frontend/src/App.vue`: gate workspace by auth state, refine navigation groups, add user/logout controls, update platform metrics.
- Modify `frontend/src/style.css`: add auth screen styles and shell polish.
- Modify `frontend/package.json`: add a test script that runs the auth client tests.
- Modify `README.md`: switch main frontend documentation from `frontend-react` to `frontend`.
- Keep generated `source/` out of the commit unless the final verification explicitly requires production assets to be included.

### Task 1: Auth Client TDD

**Files:**
- Create: `frontend/src/lib/authClient.test.mjs`
- Create: `frontend/src/lib/authClient.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/package.json`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/lib/authClient.test.mjs` with tests that import the future built JS module from `../../dist-test/authClient.js`. The tests should stub `fetch` and `localStorage`.

Required behaviors:

- `loginWithPassword` posts `email` and `password` as `application/x-www-form-urlencoded` to `/api/auth/jwt/login`.
- `registerWithPassword` posts JSON to `/api/auth/register`.
- `fetchCurrentUser` sends `Authorization: Bearer token`.
- `logout` clears token even if `/api/auth/jwt/logout` returns 500.

- [ ] **Step 2: Run red test**

Run:

```bash
fish -lc 'cd /home/shenss/python/Agno-AIOS/frontend && npm run test:auth'
```

Expected: FAIL because `frontend/dist-test/authClient.js` or exported functions do not exist.

- [ ] **Step 3: Implement auth client**

Create `frontend/src/lib/authClient.ts` with typed functions:

- `getStoredAuthToken`
- `storeAuthToken`
- `clearStoredAuthToken`
- `loginWithPassword`
- `registerWithPassword`
- `fetchCurrentUser`
- `fetchOAuthProviders`
- `requestOAuthAuthorization`
- `logout`

Use `/api` as the default base path and accept injectable `fetch` and storage for tests.

- [ ] **Step 4: Add auth types**

Add these interfaces to `frontend/src/types/index.ts`:

- `AuthTokenResponse`
- `AuthUser`
- `AuthCredentials`
- `OAuthProvider`
- `OAuthProvidersResponse`
- `OAuthAuthorizationResponse`

- [ ] **Step 5: Add test script**

Add scripts to `frontend/package.json`:

```json
"test:auth": "tsc src/lib/authClient.ts --target ES2022 --module ES2022 --moduleResolution bundler --lib ES2022,DOM --strict --outDir dist-test && node --test src/lib/authClient.test.mjs"
```

- [ ] **Step 6: Run green test**

Run:

```bash
fish -lc 'cd /home/shenss/python/Agno-AIOS/frontend && npm run test:auth'
```

Expected: PASS with four auth client tests.

### Task 2: Auth Screen

**Files:**
- Create: `frontend/src/components/AuthScreen.vue`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: Build the auth screen**

Create a Vue component with:

- Login/register segmented control.
- Email and password fields.
- Submit button with loading state.
- OAuth provider buttons when `/api/auth/oauth/providers` returns providers.
- Error alert for validation or HTTP failures.
- A right-side lineage matrix containing security/data-platform labels.

- [ ] **Step 2: Wire app auth state**

Modify `App.vue` so startup loads the stored token and calls `fetchCurrentUser`. Show `AuthScreen` until a valid user exists. On successful auth, set `currentUser`; on logout, call `logout`, clear user, and show auth again.

- [ ] **Step 3: Add session header controls**

In the authenticated header, add current user email and a logout icon/text button. Keep the theme toggle.

- [ ] **Step 4: Verify build**

Run:

```bash
fish -lc 'cd /home/shenss/python/Agno-AIOS/frontend && npm run build'
```

Expected: Vue type-check and Vite build exit 0.

### Task 3: Middle-Platform Shell Refinement

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: Refine navigation taxonomy**

Replace the current groups with:

- `安全运营`
- `数据底座`
- `AI 编排`
- `系统治理`

Map existing modules into these groups without deleting modules.

- [ ] **Step 2: Refine shell copy and metrics**

Update the platform subtitle, header chip, sidebar status, and metric cards to use:

- 数据汇聚
- 资产治理
- 漏洞情报
- Agent 编排
- Trace 观测
- 响应闭环

- [ ] **Step 3: Polish responsive layout**

Ensure mobile auth, sidebar overlay, header user controls, and metric strip do not overflow at narrow widths.

- [ ] **Step 4: Verify build**

Run:

```bash
fish -lc 'cd /home/shenss/python/Agno-AIOS/frontend && npm run build'
```

Expected: exit 0.

### Task 4: Markdown Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-06-29-frontend-vue-security-platform-design.md`
- Modify: `docs/superpowers/plans/2026-06-29-frontend-vue-security-platform.md`

- [ ] **Step 1: Update README frontend sections**

Replace React-first statements with Vue-first statements:

- Frontend stack is Vue 3, TypeScript, Element Plus, UnoCSS, Vite.
- Install/run/build commands use `frontend/`.
- `frontend-react/` is historical or experimental, not the main frontend.
- `frontend/` includes password login, registration, OAuth provider discovery, workspace auth gate, and AI information-security middle-platform shell.

- [ ] **Step 2: Add verification notes**

Document:

- `uv run ruff check .`
- `uv run ty check .`
- `fish -lc 'cd frontend && npm run build'`
- Playwright screenshot check.

### Task 5: Full Verification And Commit

**Files:**
- Commit only files changed for this goal.

- [ ] **Step 1: Run Python checks**

Run:

```bash
uv run ruff check .
uv run ty check .
```

Expected: exit 0 or report pre-existing unrelated failures with evidence.

- [ ] **Step 2: Run frontend tests and build**

Run:

```bash
fish -lc 'cd /home/shenss/python/Agno-AIOS/frontend && npm run test:auth && npm run build'
```

Expected: exit 0.

- [ ] **Step 3: Run Playwright**

Start the Vue dev server through Fish, then use Playwright to capture desktop and mobile screenshots of the auth screen and authenticated shell. If backend auth is unavailable, route/stub auth responses for the browser check.

- [ ] **Step 4: Inspect diff**

Run:

```bash
git diff -- frontend README.md docs/superpowers/specs/2026-06-29-frontend-vue-security-platform-design.md docs/superpowers/plans/2026-06-29-frontend-vue-security-platform.md
git status --short
```

Expected: goal changes are visible; unrelated existing changes remain unstaged.

- [ ] **Step 5: Commit aligned changes**

Run:

```bash
git add frontend README.md docs/superpowers/specs/2026-06-29-frontend-vue-security-platform-design.md docs/superpowers/plans/2026-06-29-frontend-vue-security-platform.md
git commit -m "feat: restore vue security platform frontend"
```

Expected: commit succeeds without staging unrelated `frontend-react/`, backend, or `source/` changes.

## Self-Review

- Spec coverage: auth, Vue frontend switch, old-page refinement, Markdown docs, verification, and git commit are covered.
- Placeholder scan: no TBD/TODO markers are present.
- Type consistency: auth type names in the plan match the planned `authClient.ts` exports and `types/index.ts` interfaces.
