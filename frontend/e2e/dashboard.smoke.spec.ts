import { expect, test, type Route } from '@playwright/test'
import { openAuthed, overviewPayload } from './fixtures'

const failure = {
  trace_id: 'trace-dash-fail',
  name: 'Dashboard failed run',
  status: 'ERROR',
  duration_ms: 1280,
  start_time: '2026-07-16T12:00:00Z',
  session_id: 'sess-dash-fail',
  run_id: 'run-dash-fail',
  agent_id: 'security-operations',
}

const session = {
  session_id: 'sess-dash-fail',
  name: 'Dashboard Fail Session',
  latest_start_time: '2026-07-16T12:00:00Z',
  trace_count: 1,
  run_count: 1,
  error_count: 1,
  status: 'ERROR',
  user_id: 'user-1',
}

const traceRow = {
  trace_id: 'trace-dash-fail',
  session_id: 'sess-dash-fail',
  run_id: 'run-dash-fail',
  name: 'Dashboard failed run',
  status: 'ERROR',
  duration: '1.28s',
  start_time: '2026-07-16T12:00:00Z',
  input: 'dash failure input',
}

const rootSpan = {
  span_id: 'span-dash-root',
  name: 'Dashboard failed run',
  status_code: 'ERROR',
  duration: '1.28s',
  start_time: '2026-07-16T12:00:00Z',
  parsed: {
    input: { format: 'text', text: 'dash-fail-root-input', data: null },
    output: { format: 'text', text: 'dash-fail-root-output', data: null },
  },
}

const detail = {
  trace: traceRow,
  spans: [rootSpan],
  tree: [{ span: rootSpan, children: [] }],
  spans_complete: true,
  span_count: 1,
}

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

test.describe('dashboard critical path', () => {
  test('recent failure navigates to Trace with canonical query and opens run', async ({ page }) => {
    await openAuthed(page, '/dashboard', {
      handleApi: async ({ method, path, url, route }) => {
        if (method === 'GET' && path.endsWith('/api/overview')) {
          await fulfillJson(route, {
            ...overviewPayload,
            recent_failures: [failure],
          })
          return true
        }

        if (method !== 'GET') return false

        if (path.endsWith('/api/chat/sessions')) {
          await fulfillJson(route, {
            data: [
              {
                session_id: 'sess-dash-fail',
                preview: 'Dashboard Fail Session',
                title: 'Dashboard Fail Session',
                archived: false,
                created_at: 1,
                updated_at: 2,
              },
            ],
            meta: { page: 1, limit: 40, total_pages: 1, total_count: 1, search_time_ms: 0 },
          })
          return true
        }

        if (path.endsWith('/api/traces/sessions')) {
          await fulfillJson(route, {
            data: [session],
            meta: { page: 1, limit: 200, total_pages: 1, total_count: 1, search_time_ms: 0 },
          })
          return true
        }

        if (path.endsWith('/api/traces')) {
          const sessionId = url.searchParams.get('session_id') ?? ''
          const runId = url.searchParams.get('run_id') ?? ''
          // Deep link from dashboard sets both filters; list must honor them.
          const match =
            (!sessionId || sessionId === 'sess-dash-fail') &&
            (!runId || runId === 'run-dash-fail')
          await fulfillJson(route, {
            data: match ? [traceRow] : [],
            meta: {
              page: 1,
              limit: 6,
              total_pages: match ? 1 : 0,
              total_count: match ? 1 : 0,
              search_time_ms: 0,
            },
          })
          return true
        }

        if (path.startsWith('/api/traces/') && !path.endsWith('/sessions')) {
          const id = decodeURIComponent(path.slice('/api/traces/'.length))
          if (id === 'trace-dash-fail') {
            await fulfillJson(route, detail)
            return true
          }
          await fulfillJson(route, {
            trace: { ...traceRow, trace_id: id },
            spans: [],
            tree: [],
            spans_complete: true,
            span_count: 0,
          })
          return true
        }

        return false
      },
    })

    await expect(page.getByRole('heading', { name: '运行概览' })).toBeVisible()
    await page.getByText('Dashboard failed run', { exact: true }).click()

    await expect(page).toHaveURL(/#\/trace\?/)
    const hash = page.url().split('#')[1] ?? ''
    const params = new URLSearchParams(hash.includes('?') ? hash.slice(hash.indexOf('?') + 1) : '')
    expect(params.get('session_id')).toBe('sess-dash-fail')
    expect(params.get('run_id')).toBe('run-dash-fail')
    expect(params.get('selected_session')).toBe('sess-dash-fail')
    expect(params.get('trace')).toBe('trace-dash-fail')
    expect(params.has('session')).toBe(false)
    expect(params.has('run')).toBe(false)

    await expect(page.getByRole('heading', { name: '观测' })).toBeVisible()
    const sessionBtn = page.locator('.trace-choice', { hasText: 'Dashboard Fail Session' })
    await expect(sessionBtn).toBeVisible()
    await expect(sessionBtn).toHaveAttribute('aria-pressed', 'true')
    await expect(page.locator('.run-span-tree').getByText('Run root · Dashboard failed run')).toBeVisible()
    await expect(page.locator('.formatted-text').filter({ hasText: 'dash-fail-root-input' })).toBeVisible()
  })
})
