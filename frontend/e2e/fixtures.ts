import type { Page } from '@playwright/test'
import { expect } from '@playwright/test'

export const AUTH_TOKEN_STORAGE_KEY = 'agno-aios-auth-token'

export const adminUser = {
  id: 'user-1',
  email: 'admin@example.com',
  role: 'admin',
  is_superuser: true,
  is_active: true,
  scopes: [] as string[],
}

/** Limited operator: workspace chat only (capabilities/governance empty after filter). */
export const chatOnlyUser = {
  id: 'user-2',
  email: 'ops@example.com',
  role: 'user',
  is_superuser: false,
  is_active: true,
  scopes: ['sessions:write', 'sessions:read'],
}

export const overviewPayload = {
  range: '24h',
  generated_at: '2026-07-12T00:00:00.000Z',
  health: { status: 'ok' },
  metrics: {
    total_runs: 0,
    failure_rate: 0,
    p95_duration_ms: 0,
    input_tokens: 0,
    output_tokens: 0,
    total_tokens: 0,
  },
  series: [],
  distributions: {},
  snapshots: {
    approvals: { pending: 0, approved: 0, rejected: 0 },
    knowledge_documents: 0,
    memories: 0,
  },
  recent_failures: [],
}

const emptyPage = {
  data: [],
  meta: { page: 1, limit: 40, total_pages: 0, total_count: 0, search_time_ms: 0 },
}

type MockOptions = {
  user?: typeof adminUser
  /** Optional custom API handler; return true when fulfilled/aborted. */
  handleApi?: (args: {
    method: string
    path: string
    url: URL
    route: import('@playwright/test').Route
  }) => Promise<boolean> | boolean
}

/**
 * Mock TAIS API used by shell + dashboard + lightweight page mounts.
 * Specs stay offline; hash router still talks to same-origin /api.
 */
export async function mockApis(page: Page, options: MockOptions = {}) {
  const user = options.user ?? adminUser

  // Only mock backend REST under /api/* — do NOT match Vite modules like /src/shared/api/*.
  await page.route((url) => {
    try {
      return new URL(url).pathname.startsWith('/api/')
    } catch {
      return false
    }
  }, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const method = request.method()

    // Never hold open SSE: abort so AppFrame retry loop fails fast without blocking UI.
    if (path.includes('/notifications/stream')) {
      await route.abort('failed')
      return
    }

    if (options.handleApi) {
      const handled = await options.handleApi({ method, path, url, route })
      if (handled) return
    }

    if (method === 'POST' && path.endsWith('/api/auth/jwt/login')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ access_token: 'e2e-token', token_type: 'bearer' }),
      })
      return
    }

    if (method === 'GET' && path.endsWith('/api/auth/users/me')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(user),
      })
      return
    }

    if (method === 'GET' && path.endsWith('/api/overview')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(overviewPayload),
      })
      return
    }

    if (method === 'GET' && path.endsWith('/api/approvals/count')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ count: 0 }),
      })
      return
    }

    if (method === 'GET' && path.endsWith('/api/notifications')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ notifications: [], unread_count: 0 }),
      })
      return
    }

    if (method === 'GET' && path.endsWith('/api/chat/sessions')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(emptyPage),
      })
      return
    }

    if (method === 'GET' && path.endsWith('/api/models')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ models: [], active_model_id: null }),
      })
      return
    }

    if (method === 'GET' && path.endsWith('/api/settings/chat')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          enable_user_memories: false,
          add_history_to_context: true,
          num_history_runs: 3,
        }),
      })
      return
    }

    if (method === 'GET' && path.endsWith('/api/approvals')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(emptyPage),
      })
      return
    }

    if (method === 'GET' && (path.endsWith('/api/traces') || path.endsWith('/api/traces/sessions'))) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(emptyPage),
      })
      return
    }

    if (method === 'GET' && path.endsWith('/api/auth/oauth/providers')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ providers: [] }),
      })
      return
    }

    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(emptyPage),
      })
      return
    }

    await route.fulfill({ status: 204, body: '' })
  })
}

/** Seed auth token before first navigation (skips login form). */
export async function seedAuth(page: Page, token = 'e2e-token') {
  await page.addInitScript(
    ([key, value]) => {
      window.localStorage.setItem(key, value)
    },
    [AUTH_TOKEN_STORAGE_KEY, token] as const,
  )
}

export async function loginAs(page: Page, password = 'AdminPass123!') {
  await page.goto('/#/login', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('button', { name: /登\s*录/ })).toBeVisible()
  await page.getByLabel('密码').fill(password)
  await page.getByRole('button', { name: /登\s*录/ }).click()
  await expect(page).toHaveURL(/#\/dashboard/, { timeout: 15_000 })
}

export async function openAuthed(page: Page, hashPath = '/dashboard', options: MockOptions = {}) {
  await mockApis(page, options)
  await seedAuth(page)
  await page.goto(`/#${hashPath.startsWith('/') ? hashPath : `/${hashPath}`}`, { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.app-shell, .auth-page')).toBeVisible({ timeout: 15_000 })
}
