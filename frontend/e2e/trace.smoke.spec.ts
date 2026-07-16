import { expect, test, type Route } from '@playwright/test'
import { openAuthed } from './fixtures'

const session = {
  session_id: 'sess-e2e',
  name: 'E2E Session',
  latest_start_time: '2026-07-16T12:00:00Z',
  trace_count: 1,
  run_count: 1,
  error_count: 0,
  status: 'OK',
  user_id: 'user-1',
}

const traceRow = {
  trace_id: 'trace-e2e-1',
  session_id: 'sess-e2e',
  run_id: 'run-e2e-1',
  name: 'E2E Run',
  status: 'OK',
  duration: '1.20s',
  start_time: '2026-07-16T12:00:00Z',
  end_time: '2026-07-16T12:00:01Z',
  input: 'root input preview',
}

const rootSpan = {
  span_id: 'span-root',
  name: 'E2E Run',
  status_code: 'OK',
  duration: '1.20s',
  start_time: '2026-07-16T12:00:00Z',
  parsed: {
    input: { format: 'text', text: 'e2e-root-input-unique', data: null },
    output: { format: 'text', text: 'e2e-root-output-unique', data: null },
  },
}

const childSpan = {
  span_id: 'span-child',
  parent_span_id: 'span-root',
  name: 'Child tool',
  status_code: 'OK',
  duration: '100ms',
  start_time: '2026-07-16T12:00:00Z',
  parsed: {
    input: { format: 'text', text: 'e2e-child-input-unique', data: null },
    output: { format: 'text', text: 'e2e-child-output-unique', data: null },
  },
}

const detail = {
  trace: traceRow,
  spans: [rootSpan, childSpan],
  tree: [{ span: rootSpan, children: [{ span: childSpan, children: [] }] }],
  spans_complete: true,
  span_count: 2,
}

const emptyMeta = { page: 1, limit: 20, total_pages: 1, total_count: 1, search_time_ms: 0 }

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

test.describe('trace critical path', () => {
  test('deep link Session → Run → Span shows tree and detail', async ({ page }) => {
    await openAuthed(page, '/dashboard', {
      handleApi: async ({ method, path, url, route }) => {
        if (method !== 'GET') return false

        if (path.endsWith('/api/chat/sessions')) {
          await fulfillJson(route, {
            data: [
              {
                session_id: 'sess-e2e',
                title: 'E2E Session',
                preview: 'preview',
                archived: false,
                user_id: 'user-1',
                created_at: 1720000000,
                updated_at: 1720000000,
              },
            ],
            meta: { page: 1, limit: 40, total_pages: 1, total_count: 1, search_time_ms: 0 },
          })
          return true
        }

        if (path.endsWith('/api/traces/sessions')) {
          await fulfillJson(route, { data: [session], meta: { ...emptyMeta, limit: 200, total_count: 1 } })
          return true
        }

        if (path.endsWith('/api/traces')) {
          // List for selected session
          const sessionId = url.searchParams.get('session_id') ?? ''
          const data = sessionId === 'sess-e2e' || !sessionId ? [traceRow] : []
          await fulfillJson(route, {
            data,
            meta: { page: 1, limit: 6, total_pages: 1, total_count: data.length, search_time_ms: 0 },
          })
          return true
        }

        if (path.startsWith('/api/traces/') && !path.endsWith('/sessions')) {
          const id = decodeURIComponent(path.slice('/api/traces/'.length))
          if (id === 'trace-e2e-1') {
            await fulfillJson(route, detail)
            return true
          }
          await fulfillJson(route, { trace: { ...traceRow, trace_id: id }, spans: [], tree: [], spans_complete: true, span_count: 0 })
          return true
        }

        return false
      },
    })

    // Deep link: selected session + active trace (Dashboard failure link contract).
    await page.goto('/#/trace?selected_session=sess-e2e&trace=trace-e2e-1', { waitUntil: 'domcontentloaded' })

    await expect(page.getByRole('heading', { name: '观测' })).toBeVisible()
    // Session list shows the deep-linked session selected.
    const sessionBtn = page.locator('.trace-choice', { hasText: 'E2E Session' })
    await expect(sessionBtn).toBeVisible()
    await expect(sessionBtn).toHaveAttribute('aria-pressed', 'true')

    // Runs & Spans tree titles are "Run root · …" / "Span · …" after detail fetch.
    const tree = page.locator('.run-span-tree')
    await expect(tree.getByText('Run root · E2E Run')).toBeVisible()

    // Expand collapsed ant Tree nodes so child span is clickable.
    const switcher = tree.locator('.ant-tree-switcher_close').first()
    if (await switcher.count()) {
      await switcher.click()
    }
    await expect(tree.getByText('Span · Child tool')).toBeVisible()

    // Root is auto-selected for deep-linked trace; detail Input shows root text.
    await expect(page.locator('.formatted-text').filter({ hasText: 'e2e-root-input-unique' })).toBeVisible()

    // Click child span to prove Span selection path.
    await tree.getByText('Span · Child tool').click()
    await expect(page.locator('.formatted-text').filter({ hasText: 'e2e-child-input-unique' })).toBeVisible()
  })

  test('ignores legacy session/run query aliases', async ({ page }) => {
    await openAuthed(page, '/dashboard', {
      handleApi: async ({ method, path, route }) => {
        if (method === 'GET' && path.endsWith('/api/traces/sessions')) {
          await fulfillJson(route, { data: [session], meta: { ...emptyMeta, limit: 200, total_count: 1 } })
          return true
        }
        if (method === 'GET' && path.endsWith('/api/traces')) {
          await fulfillJson(route, {
            data: [],
            meta: { page: 1, limit: 6, total_pages: 0, total_count: 0, search_time_ms: 0 },
          })
          return true
        }
        return false
      },
    })

    await page.goto('/#/trace?session=legacy-session&run=legacy-run', { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('heading', { name: '观测' })).toBeVisible()
    // Session ID filter must stay empty (legacy aliases not applied).
    await expect(page.getByPlaceholder('Session ID')).toHaveValue('')
    await expect(page.getByPlaceholder('Run ID')).toHaveValue('')
  })
})
