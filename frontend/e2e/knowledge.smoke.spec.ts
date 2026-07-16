import { expect, test, type Route } from '@playwright/test'
import { openAuthed } from './fixtures'

const document = {
  id: 'doc-e2e-1',
  title: 'E2E Knowledge Doc',
  source: 'e2e',
  chunks: 1,
  created_at: '2026-07-16T12:00:00Z',
  updated_at: '2026-07-16T12:00:00Z',
  status: 'ready',
  visibility: 'private',
  owner_user_id: 'user-1',
  can_manage: true,
  metadata: {},
}

const emptyList = {
  data: [],
  meta: { page: 1, limit: 12, total_pages: 0, total_count: 0, search_time_ms: 0 },
  status: { rag_settings: { search_type: 'hybrid' } },
}

const listed = {
  data: [document],
  meta: { page: 1, limit: 12, total_pages: 1, total_count: 1, search_time_ms: 0 },
  status: { rag_settings: { search_type: 'hybrid' } },
}

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

function progressSse() {
  // Full body is fine for smoke: client consumes all events then closes drawer.
  // Intermediate step paint is covered by UpdateProgress unit tests.
  const events = [
    ['progress', { stage: 'parse', status: 'running', message: 'parsing' }],
    ['progress', { stage: 'parse', status: 'completed', message: 'parsed' }],
    ['progress', { stage: 'vectorize', status: 'running', message: 'vectorizing' }],
    ['progress', { stage: 'vectorize', status: 'completed', message: 'vectorized' }],
    ['progress', { stage: 'cleanup', status: 'running', message: 'cleanup' }],
    ['progress', { stage: 'cleanup', status: 'completed', message: 'cleaned' }],
    ['progress.completed', { stage: 'done', status: 'completed', message: 'done', document }],
  ] as const
  return events
    .map(([event, data]) => ['event: ' + event, 'data: ' + JSON.stringify(data), ''].join('\n'))
    .join('\n')
}

test.describe('knowledge critical path', () => {
  test('text ingest streams to completion and lists document', async ({ page }) => {
    let listCalls = 0
    let streamPosts = 0
    await openAuthed(page, '/dashboard', {
      handleApi: async ({ method, path, url, route }) => {
        if (path.endsWith('/api/knowledge') && method === 'GET') {
          listCalls += 1
          await fulfillJson(route, listCalls > 1 ? listed : emptyList)
          return true
        }
        if (path.endsWith('/api/knowledge/status') && method === 'GET') {
          await fulfillJson(route, { rag_settings: { search_type: 'hybrid' } })
          return true
        }
        if (path.endsWith('/api/knowledge/documents/text') && method === 'POST') {
          expect(url.searchParams.get('stream')).toBe('true')
          streamPosts += 1
          await route.fulfill({
            status: 200,
            headers: {
              'Content-Type': 'text/event-stream',
              'Cache-Control': 'no-cache',
            },
            body: progressSse(),
          })
          return true
        }
        return false
      },
    })

    await page.goto('/#/knowledge', { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('heading', { name: '知识库' })).toBeVisible()

    await page.getByRole('button', { name: /添加文档/ }).click()
    const drawer = page.getByRole('dialog', { name: '添加知识文档' })
    await expect(drawer).toBeVisible()

    await drawer.getByRole('tab', { name: '文本' }).click()
    // antd Button inserts spaces in CJK labels (same as login "登 录").
    const submit = drawer.getByRole('button', { name: /入\s*库/ })
    await expect(submit).toBeVisible()

    await drawer.getByRole('textbox', { name: /标题/ }).fill('E2E Knowledge Doc')
    await drawer.getByRole('textbox', { name: /内容/ }).fill('hello knowledge progress e2e')

    await submit.click()

    // Stream completion closes drawer and refreshes the list.
    await expect(drawer).toBeHidden({ timeout: 15_000 })
    await expect(page.getByRole('row', { name: /E2E Knowledge Doc/ }).getByRole('cell', { name: 'E2E Knowledge Doc', exact: true })).toBeVisible()
    expect(streamPosts).toBe(1)
  })
})
