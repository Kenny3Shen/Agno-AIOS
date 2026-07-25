import { expect, test, type Route } from '@playwright/test'
import { openAuthed } from './fixtures'

const workflowPending = {
  id: 'appr-wf-e2e-1',
  status: 'pending',
  source_type: 'workflow',
  source_name: 'IR triage',
  tool_name: 'workflow.step:confirm',
  pause_type: 'confirmation',
  workflow_id: 'wf-e2e-1',
  run_id: 'run-e2e-1',
  session_id: 'sess-e2e-1',
  created_at: '2026-07-16T12:00:00Z',
  tool_args: { message: 'E2E approve this step?' },
}

const hitlEnvelope = {
  data: [workflowPending],
  meta: { page: 1, limit: 20, total_pages: 1, total_count: 1, search_time_ms: 0 },
}

const emptyEnvelope = {
  data: [],
  meta: { page: 1, limit: 20, total_pages: 0, total_count: 0, search_time_ms: 0 },
}

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

test.describe('approvals critical path', () => {
  test('default on-call filter lists pending workflow HITL and deep-links drawer', async ({ page }) => {
    let listCalls = 0
    await openAuthed(page, '/dashboard', {
      handleApi: async ({ method, path, url, route }) => {
        if (method === 'GET' && path.endsWith('/api/approvals/count')) {
          await fulfillJson(route, { count: 1 })
          return true
        }
        if (method === 'GET' && path.endsWith('/api/approvals')) {
          listCalls += 1
          // Default on-call: pending + workflow HITL (source_type=workflow).
          expect(url.searchParams.get('status')).toBe('pending')
          expect(url.searchParams.get('source_type')).toBe('workflow')
          await fulfillJson(route, hitlEnvelope)
          return true
        }
        if (method === 'GET' && path.endsWith(`/api/approvals/${workflowPending.id}`)) {
          await fulfillJson(route, workflowPending)
          return true
        }
        if (method === 'GET' && path.endsWith('/api/approvals/submissions')) {
          await fulfillJson(route, emptyEnvelope)
          return true
        }
        return false
      },
    })

    await page.goto('/#/approvals', { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('heading', { name: '审批' })).toBeVisible()
    await expect(page.getByText('仅 pending 工作流步骤；通知可深链打开。')).toBeVisible()

    // Segmented default is 工作流 HITL; row shows step tool name + pending tag.
    await expect(page.getByText('workflow.step:confirm')).toBeVisible()
    await expect(page.getByRole('button', { name: /查看审批 appr-wf-e2e/ })).toBeVisible()
    await expect(page.locator('.ant-tag', { hasText: /待处理|Pending/i })).toBeVisible()

    // Deep link opens the approval drawer.
    await page.goto(`/#/approvals?approval_id=${workflowPending.id}`, { waitUntil: 'domcontentloaded' })
    const drawer = page.getByRole('dialog', { name: /审批详情|Approval detail/i })
    await expect(drawer).toBeVisible({ timeout: 10_000 })
    await expect(drawer.getByText('workflow.step:confirm')).toBeVisible()
    // Request data PayloadViewer includes tool_args.message.
    await expect(drawer.getByText('E2E approve this step?')).toBeVisible()
    expect(listCalls).toBeGreaterThan(0)
  })

  test('approves a pending workflow HITL from the detail drawer', async ({ page }) => {
    let resolveCalls = 0
    let listStatus = 'pending'

    await openAuthed(page, '/dashboard', {
      handleApi: async ({ method, path, url, route }) => {
        if (method === 'GET' && path.endsWith('/api/approvals/count')) {
          await fulfillJson(route, { count: listStatus === 'pending' ? 1 : 0 })
          return true
        }
        if (method === 'GET' && path.endsWith('/api/approvals')) {
          expect(url.searchParams.get('status')).toBe('pending')
          expect(url.searchParams.get('source_type')).toBe('workflow')
          await fulfillJson(route, listStatus === 'pending' ? hitlEnvelope : emptyEnvelope)
          return true
        }
        if (method === 'GET' && path.endsWith(`/api/approvals/${workflowPending.id}`)) {
          await fulfillJson(
            route,
            listStatus === 'pending'
              ? workflowPending
              : {
                  ...workflowPending,
                  status: 'approved',
                  resolved_by: { id: 'user-1', email: 'admin@example.com' },
                  resolved_at: '2026-07-16T12:05:00Z',
                },
          )
          return true
        }
        if (method === 'GET' && path.endsWith('/api/approvals/submissions')) {
          await fulfillJson(route, emptyEnvelope)
          return true
        }
        if (method === 'POST' && path.endsWith(`/api/approvals/${workflowPending.id}/resolve`)) {
          resolveCalls += 1
          const body = route.request().postDataJSON() as { status?: string }
          expect(body.status).toBe('approved')
          listStatus = 'approved'
          await fulfillJson(route, {
            ...workflowPending,
            status: 'approved',
            resolved_by: { id: 'user-1', email: 'admin@example.com' },
            resolved_at: '2026-07-16T12:05:00Z',
          })
          return true
        }
        return false
      },
    })

    await page.goto(`/#/approvals?approval_id=${workflowPending.id}`, { waitUntil: 'domcontentloaded' })
    const drawer = page.getByRole('dialog', { name: /审批详情|Approval detail/i })
    await expect(drawer).toBeVisible({ timeout: 10_000 })
    await expect(drawer.getByText('E2E approve this step?')).toBeVisible()

    // Confirmation pause_type approves immediately (no user_input modal).
    await drawer.getByRole('button', { name: /批\s*准/ }).click()

    await expect.poll(() => resolveCalls, { timeout: 10_000 }).toBe(1)
    await expect(page.getByText(/审批已approved|Approval approved/i)).toBeVisible({ timeout: 10_000 })
  })
})
