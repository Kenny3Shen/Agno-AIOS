import { expect, test, type Route } from '@playwright/test'
import { openAuthed } from './fixtures'

const workflow = {
  id: 'wf-e2e-1',
  name: 'E2E Workflow',
  description: 'smoke',
  enabled: true,
  version: 1,
  published_version: 1,
  published_at: 1720000000,
  has_published: true,
  owner_user_id: 'user-1',
  definition: {
    name: 'E2E Workflow',
    description: 'smoke',
    steps: [
      {
        id: 'step-1',
        type: 'step',
        name: 'Triage',
        executor: { kind: 'agent', ref: 'security-operations' },
        instructions: 'triage the alert',
      },
    ],
  },
  triggers: {
    webhook: { enabled: false, secret: '' },
    cron: { enabled: false, expression: '', last_run_at: 0 },
  },
  created_at: 1720000000,
  updated_at: 1720000000,
}

const listEnvelope = {
  data: [workflow],
  meta: { page: 1, limit: 50, total_pages: 1, total_count: 1, search_time_ms: 0 },
}

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

test.describe('workflow critical path', () => {
  test('deep link loads saved workflow into studio', async ({ page }) => {
    let listCalls = 0
    await openAuthed(page, '/dashboard', {
      handleApi: async ({ method, path, route }) => {
        if (method === 'GET' && path.endsWith('/api/workflows')) {
          listCalls += 1
          await fulfillJson(route, listEnvelope)
          return true
        }
        if (method === 'GET' && path.endsWith(`/api/workflows/${workflow.id}`)) {
          await fulfillJson(route, workflow)
          return true
        }
        if (method === 'GET' && path.endsWith('/api/workflows/executors')) {
          await fulfillJson(route, {
            data: [
              {
                ref: 'security-operations',
                kind: 'agent',
                name: 'Security Operations',
                description: '',
              },
            ],
          })
          return true
        }
        if (method === 'GET' && path.endsWith('/api/workflows/templates')) {
          await fulfillJson(route, { data: [] })
          return true
        }
        if (method === 'GET' && path.endsWith('/api/skills')) {
          await fulfillJson(route, { skills: [] })
          return true
        }
        if (method === 'GET' && path.includes(`/api/workflows/${workflow.id}/versions`)) {
          await fulfillJson(route, {
            data: [],
            meta: { page: 1, limit: 20, total_pages: 0, total_count: 0, search_time_ms: 0 },
          })
          return true
        }
        if (method === 'GET' && path.includes(`/api/workflows/${workflow.id}/triggers/history`)) {
          await fulfillJson(route, {
            data: [],
            meta: { page: 1, limit: 20, total_pages: 0, total_count: 0, search_time_ms: 0 },
          })
          return true
        }
        return false
      },
    })

    await page.goto(`/#/workflow?workflow_id=${workflow.id}`, { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('heading', { name: '工作流' })).toBeVisible()
    await expect(page.getByPlaceholder('工作流名称')).toHaveValue('E2E Workflow', { timeout: 10_000 })
    await expect(page.locator('.wf-flow-node__title', { hasText: 'Triage' })).toBeVisible()
    expect(listCalls).toBeGreaterThan(0)
  })
})
