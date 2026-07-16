import { screen } from '@testing-library/react'
import { user } from '@/test/user'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
import { ApprovalsPage } from './ApprovalsPage'

const switchKind = async (label: RegExp) => {
  await user.click(await screen.findByText(label))
}

const setStatus = async (label: RegExp) => {
  const statusSelect = document.querySelector('.ant-select-content[title], .ant-select-content-has-value')
  const target =
    Array.from(document.querySelectorAll('.ant-select')).find((el) =>
      el.textContent?.match(/Pending|已批准|已拒绝|全部状态|All statuses|Approved|Rejected|待/)
    ) ?? statusSelect?.closest('.ant-select')
  if (!target) throw new Error('status select not found')
  await user.click(target as HTMLElement)
  await user.click(await screen.findByText(label))
}

describe('ApprovalsPage', () => {
  it('defaults to pending workflow HITL on-call filter', async () => {
    server.use(
      http.get('/api/auth/users/me', () =>
        HttpResponse.json({ id: 'admin-1', email: 'admin@example.com', role: 'admin', scopes: ['admin'] })
      ),
      http.get('/api/approvals', ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get('status')).toBe('pending')
        expect(url.searchParams.get('source_type')).toBe('workflow')
        return HttpResponse.json({
          data: [],
          meta: { page: 1, limit: 20, total_pages: 0, total_count: 0, search_time_ms: 0 },
        })
      }),
      http.get('/api/approvals/submissions', () =>
        HttpResponse.json({ data: [], meta: { page: 1, limit: 20, total_pages: 0, total_count: 0, search_time_ms: 0 } })
      )
    )
    renderWithQuery(<ApprovalsPage />)
    expect(await screen.findByText(/工作流 HITL|Workflow HITL/)).toBeTruthy()
    expect(screen.getByText(/上传审批|Uploads/)).toBeTruthy()
  })

  it('shows submitted skill uploads and lets an administrator approve them', async () => {
    server.use(
      http.get('/api/auth/users/me', () =>
        HttpResponse.json({ id: 'admin-1', email: 'admin@example.com', role: 'admin', scopes: ['admin'] })
      ),
      http.get('/api/approvals', () =>
        HttpResponse.json({
          data: [],
          meta: { page: 1, limit: 100, total_pages: 0, total_count: 0, search_time_ms: 0 },
        })
      ),
      http.get('/api/approvals/submissions', () =>
        HttpResponse.json({
          meta: { page: 1, limit: 100, total_pages: 1, total_count: 1, search_time_ms: 0 },
          data: [
            {
              id: 'upload-1',
              status: 'pending',
              resource_type: 'skill',
              submitted_by: { id: 'member-1', email: 'member@example.com' },
              created_at: '2026-07-13T09:00:00Z',
              payload: { name: 'web-search', visibility: 'private', filename: 'web-search.zip' },
            },
          ],
        })
      ),
      http.get('/api/approvals/submissions/upload-1/skill-preview', () =>
        HttpResponse.json({
          entry_count: 2,
          files: [
            { name: 'SKILL.md', size: 36 },
            { name: 'scripts/search.py', size: 24 },
          ],
          previews: { 'SKILL.md': '# Web search' },
        })
      ),
      http.post('/api/approvals/submissions/upload-1/resolve', async ({ request }) => {
        expect(await request.json()).toEqual({ status: 'approved' })
        return HttpResponse.json({
          id: 'upload-1',
          status: 'approved',
          resource_type: 'skill',
          submitted_by: { id: 'member-1', email: 'member@example.com' },
          resolved_by: { id: 'admin-1', email: 'admin@example.com' },
          payload: { name: 'web-search' },
        })
      })
    )

    renderWithQuery(<ApprovalsPage />)
    await switchKind(/上传审批|Uploads/)

    expect(await screen.findByText('web-search')).toBeTruthy()
    await user.click(screen.getByText('web-search'))
    expect(screen.getByText('Decision')).toBeTruthy()
    expect(screen.getByText('People')).toBeTruthy()
    expect(screen.getByText('Request data')).toBeTruthy()
    expect(screen.getByText('member-1')).toBeTruthy()
    expect((await screen.findAllByText('SKILL.md')).length).toBeGreaterThan(0)
    await user.click(screen.getAllByText('SKILL.md').at(-1)!)
    expect(await screen.findByText('# Web search')).toBeTruthy()
    await user.click(screen.getByText('Markdown'))
    expect(await screen.findByRole('heading', { name: 'Web search' })).toBeTruthy()
    await user.click(screen.getByRole('button', { name: /批准/ }))
    expect(await screen.findByText('审批已approved')).toBeTruthy()
  })

  it('lets a regular user view only their submitted approval without resolution controls', async () => {
    server.use(
      http.get('/api/auth/users/me', () =>
        HttpResponse.json({
          id: 'member-1',
          email: 'member@example.com',
          role: 'user',
          scopes: ['approvals:read'],
        })
      ),
      http.get('/api/approvals', () =>
        HttpResponse.json({
          data: [],
          meta: { page: 1, limit: 100, total_pages: 0, total_count: 0, search_time_ms: 0 },
        })
      ),
      http.get('/api/approvals/submissions', ({ request }) => {
        const url = new URL(request.url)
        // Only return rejected row when status filter is empty or rejected
        const status = url.searchParams.get('status')
        if (status && status !== 'rejected') {
          return HttpResponse.json({
            data: [],
            meta: { page: 1, limit: 100, total_pages: 0, total_count: 0, search_time_ms: 0 },
          })
        }
        return HttpResponse.json({
          meta: { page: 1, limit: 100, total_pages: 1, total_count: 1, search_time_ms: 0 },
          data: [
            {
              id: 'upload-1',
              status: 'rejected',
              resource_type: 'mcp',
              submitted_by: { id: 'member-1', email: 'member@example.com' },
              resolved_by: { id: 'admin-1', email: 'admin@example.com' },
              rejection_reason: 'The server manifest is incomplete.',
              payload: { name: 'approved-server' },
            },
          ],
        })
      })
    )

    renderWithQuery(<ApprovalsPage />)
    await switchKind(/上传审批|Uploads/)
    await setStatus(/全部状态|All statuses/)

    await user.click(await screen.findByText('approved-server'))
    expect(screen.getByText('已拒绝')).toBeTruthy()
    expect(screen.getAllByText('The server manifest is incomplete.').length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: /批准/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /拒绝/ })).toBeNull()
  })

  it('shows a failed chat HITL resume and lets an administrator retry it', async () => {
    server.use(
      http.get('/api/auth/users/me', () =>
        HttpResponse.json({ id: 'admin-1', email: 'admin@example.com', role: 'admin', scopes: ['admin'] })
      ),
      http.get('/api/approvals', ({ request }) => {
        const url = new URL(request.url)
        const status = url.searchParams.get('status')
        // Default page is pending; resume case is approved — only when status empty/approved
        if (status === 'pending') {
          return HttpResponse.json({
            data: [],
            meta: { page: 1, limit: 100, total_pages: 0, total_count: 0, search_time_ms: 0 },
          })
        }
        return HttpResponse.json({
          data: [
            {
              id: 'approval-1',
              status: 'approved',
              tool_name: 'any_protected_tool',
              run_id: 'run-1',
              session_id: 'session-1',
              source_type: 'agent',
              agent_id: 'security-operations',
              run_status: 'ERROR',
              resolved_by: { id: 'admin-1', email: 'admin@example.com' },
            },
          ],
          meta: { page: 1, limit: 100, total_pages: 1, total_count: 1, search_time_ms: 0 },
        })
      }),
      http.get('/api/approvals/submissions', () =>
        HttpResponse.json({
          data: [],
          meta: { page: 1, limit: 100, total_pages: 0, total_count: 0, search_time_ms: 0 },
        })
      ),
      http.post('/api/approvals/approval-1/resume', () =>
        HttpResponse.json({
          id: 'approval-1',
          status: 'approved',
          tool_name: 'any_protected_tool',
          run_status: 'RUNNING',
        })
      )
    )

    renderWithQuery(<ApprovalsPage />)
    // "All" kind merges uploads + HITL without source_type filter
    await switchKind(/^全部$|^All$/)
    await setStatus(/全部状态|All statuses/)

    await user.click(await screen.findByText('any_protected_tool'))
    expect(screen.getByText('运行恢复失败')).toBeTruthy()
    expect(screen.getByText('运行状态')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '重试恢复' }))
    expect(await screen.findByText('已开始重试恢复运行。')).toBeTruthy()
  })
})
