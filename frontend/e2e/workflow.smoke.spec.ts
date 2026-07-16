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
          await fulfillJson(route, { data: [], meta: { page: 1, limit: 1, total_pages: 0, total_count: 0, search_time_ms: 0 } })
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

  test('run streams SSE events into run log', async ({ page }) => {
    let runPosts = 0
    await openAuthed(page, '/dashboard', {
      handleApi: async ({ method, path, route }) => {
        if (method === 'GET' && path.endsWith('/api/workflows')) {
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
          await fulfillJson(route, {
            data: [],
            meta: { page: 1, limit: 1, total_pages: 0, total_count: 0, search_time_ms: 0 },
          })
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
        if (method === 'GET' && path.endsWith('/api/models')) {
          await fulfillJson(route, {
            active_model_id: 'model-1',
            models: [
              {
                id: 'model-1',
                name: 'E2E Model',
                provider: 'openai',
                model_id: 'gpt-test',
                base_url: '',
                api_key: 'sk-test',
                api_protocol: 'chat-completions',
                structured_output_mode: 'native',
                description: '',
                enabled: true,
                builtin: false,
                configured: true,
              },
            ],
          })
          return true
        }
        if (method === 'POST' && path.endsWith(`/api/workflows/${workflow.id}/runs`)) {
          runPosts += 1
          await route.fulfill({
            status: 200,
            headers: {
              'Content-Type': 'text/event-stream',
              'Cache-Control': 'no-cache',
            },
            body: [
              'event: workflow.started',
              'data: {"run_id":"run-e2e-wf-1","session_id":"sess-e2e-wf-1","name":"E2E Workflow"}',
              '',
              'event: step.completed',
              'data: {"run_id":"run-e2e-wf-1","step_id":"step-1","step_name":"Triage","content":"triage complete e2e"}',
              '',
              'event: workflow.completed',
              'data: {"run_id":"run-e2e-wf-1","session_id":"sess-e2e-wf-1","content":"workflow done e2e"}',
              '',
            ].join('\n'),
          })
          return true
        }
        return false
      },
    })

    await page.goto(`/#/workflow?workflow_id=${workflow.id}`, { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('heading', { name: '工作流' })).toBeVisible()
    await expect(page.getByPlaceholder('工作流名称')).toHaveValue('E2E Workflow', { timeout: 10_000 })

    // Run panel input + toolbar Run.
    const input = page.getByPlaceholder(/运行输入|告警摘要/)
    await expect(input).toBeVisible()
    await input.fill('e2e workflow alert summary')

    await page.getByRole('button', { name: 'play-circle 运行' }).click()

    // Run log shows terminal + step events from the SSE stream.
    await expect.poll(() => runPosts, { timeout: 5_000 }).toBe(1)
    await expect(page.getByText('workflow.completed').first()).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('step.completed').first()).toBeVisible()
    // step_name is preferred over content/message in the run log list.
    await expect(page.getByText('Triage').first()).toBeVisible()
  })

  test('pause surfaces approval CTA then resolve closes HITL', async ({ page }) => {
    const approvalId = 'appr-wf-pause-1'
    const runId = 'run-e2e-wf-pause'
    const sessionId = 'sess-e2e-wf-pause'
    let runPosts = 0
    let resolveCalls = 0
    let listStatus = 'pending'

    const pendingApproval = {
      id: approvalId,
      status: 'pending',
      source_type: 'workflow',
      source_name: 'E2E Workflow',
      tool_name: 'workflow.step:confirm',
      pause_type: 'confirmation',
      workflow_id: workflow.id,
      run_id: runId,
      session_id: sessionId,
      created_at: '2026-07-16T12:00:00Z',
      tool_args: { message: 'E2E HITL confirm step?' },
    }
    const hitlEnvelope = {
      data: [pendingApproval],
      meta: { page: 1, limit: 20, total_pages: 1, total_count: 1, search_time_ms: 0 },
    }
    const emptyEnvelope = {
      data: [],
      meta: { page: 1, limit: 20, total_pages: 0, total_count: 0, search_time_ms: 0 },
    }

    await openAuthed(page, '/dashboard', {
      handleApi: async ({ method, path, url, route }) => {
        if (method === 'GET' && path.endsWith('/api/workflows')) {
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
          await fulfillJson(route, {
            data: [],
            meta: { page: 1, limit: 1, total_pages: 0, total_count: 0, search_time_ms: 0 },
          })
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
        if (method === 'GET' && path.endsWith('/api/models')) {
          await fulfillJson(route, {
            active_model_id: 'model-1',
            models: [
              {
                id: 'model-1',
                name: 'E2E Model',
                provider: 'openai',
                model_id: 'gpt-test',
                base_url: '',
                api_key: 'sk-test',
                api_protocol: 'chat-completions',
                structured_output_mode: 'native',
                description: '',
                enabled: true,
                builtin: false,
                configured: true,
              },
            ],
          })
          return true
        }
        if (method === 'POST' && path.endsWith(`/api/workflows/${workflow.id}/runs`)) {
          runPosts += 1
          await route.fulfill({
            status: 200,
            headers: {
              'Content-Type': 'text/event-stream',
              'Cache-Control': 'no-cache',
            },
            body: [
              `event: workflow.started`,
              `data: {"run_id":"${runId}","session_id":"${sessionId}","name":"E2E Workflow"}`,
              '',
              `event: step.started`,
              `data: {"run_id":"${runId}","step_id":"step-1","step_name":"Triage"}`,
              '',
              `event: workflow.paused`,
              `data: {"run_id":"${runId}","session_id":"${sessionId}","step_id":"step-1","step_name":"Triage","approval_id":"${approvalId}","pause_type":"confirmation","content":"waiting for approval"}`,
              '',
            ].join('\n'),
          })
          return true
        }

        // Approvals APIs used after Studio deep-link.
        if (method === 'GET' && path.endsWith('/api/approvals/count')) {
          await fulfillJson(route, { count: listStatus === 'pending' ? 1 : 0 })
          return true
        }
        if (method === 'GET' && path.endsWith('/api/approvals')) {
          // On-call default: pending workflow HITL.
          if (url.searchParams.get('source_type') === 'workflow' || !url.searchParams.get('source_type')) {
            await fulfillJson(route, listStatus === 'pending' ? hitlEnvelope : emptyEnvelope)
            return true
          }
          await fulfillJson(route, emptyEnvelope)
          return true
        }
        if (method === 'GET' && path.endsWith(`/api/approvals/${approvalId}`)) {
          await fulfillJson(
            route,
            listStatus === 'pending'
              ? pendingApproval
              : {
                  ...pendingApproval,
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
        if (method === 'POST' && path.endsWith(`/api/approvals/${approvalId}/resolve`)) {
          resolveCalls += 1
          const body = route.request().postDataJSON() as { status?: string }
          expect(body.status).toBe('approved')
          listStatus = 'approved'
          await fulfillJson(route, {
            ...pendingApproval,
            status: 'approved',
            resolved_by: { id: 'user-1', email: 'admin@example.com' },
            resolved_at: '2026-07-16T12:05:00Z',
          })
          return true
        }
        return false
      },
    })

    // 1) Studio run pauses with HITL.
    await page.goto(`/#/workflow?workflow_id=${workflow.id}`, { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('heading', { name: '工作流' })).toBeVisible()
    await expect(page.getByPlaceholder('工作流名称')).toHaveValue('E2E Workflow', { timeout: 10_000 })

    const input = page.getByPlaceholder(/运行输入|告警摘要/)
    await expect(input).toBeVisible()
    await input.fill('e2e pause for hitl')
    await page.getByRole('button', { name: 'play-circle 运行' }).click()

    await expect.poll(() => runPosts, { timeout: 5_000 }).toBe(1)
    await expect(page.getByText('workflow.paused').first()).toBeVisible({ timeout: 10_000 })
    // Top CTA + run-log row both expose Open approval after pause.
    const openApproval = page.getByRole('button', { name: /打开审批|Open approval/ }).first()
    await expect(openApproval).toBeVisible()
    await openApproval.click()

    // 2) Approvals drawer deep-linked by approval_id.
    await expect(page).toHaveURL(new RegExp(`approval_id=${approvalId}`))
    const drawer = page.getByRole('dialog', { name: 'Approval detail' })
    await expect(drawer).toBeVisible({ timeout: 10_000 })
    await expect(drawer.getByText('E2E HITL confirm step?')).toBeVisible()
    await expect(drawer.getByText('workflow.step:confirm')).toBeVisible()

    // 3) Approve confirmation HITL (server continues in background; UI resolves).
    await drawer.getByRole('button', { name: /批\s*准/ }).click()
    await expect.poll(() => resolveCalls, { timeout: 10_000 }).toBe(1)
    await expect(page.getByText(/审批已approved|Approval approved/i)).toBeVisible({ timeout: 10_000 })
  })

})
