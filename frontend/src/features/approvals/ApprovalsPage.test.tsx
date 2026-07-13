import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
import { ApprovalsPage } from './ApprovalsPage'

describe('ApprovalsPage', () => {
  it('shows submitted skill uploads and lets an administrator approve them', async () => {
    server.use(
      http.get('/api/auth/users/me', () =>
        HttpResponse.json({ id: 'admin-1', email: 'admin@example.com', role: 'admin', scopes: ['admin'] })
      ),
      http.get('/api/approvals', () =>
        HttpResponse.json({
          approvals: [],
        })
      ),
      http.get('/api/approvals/submissions', () =>
        HttpResponse.json({
          approvals: [
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

    expect(await screen.findByText('Skill 上传')).toBeTruthy()
    await userEvent.click(screen.getByText('Skill 上传'))
    expect(screen.getByText('member-1')).toBeTruthy()
    expect(screen.getAllByText('member@example.com').length).toBeGreaterThan(0)
    expect(screen.getByText(/"name": "web-search"/)).toBeTruthy()
    expect((await screen.findAllByText('SKILL.md')).length).toBeGreaterThan(0)
    await userEvent.click(screen.getAllByText('SKILL.md').at(-1)!)
    expect(await screen.findByText('# Web search')).toBeTruthy()
    await userEvent.click(screen.getByText('Markdown'))
    expect(await screen.findByRole('heading', { name: 'Web search' })).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: /批准/ }))
    expect(await screen.findByText('审批已approved')).toBeTruthy()
    expect(screen.getByText('admin-1')).toBeTruthy()
    expect(screen.getByText('admin@example.com')).toBeTruthy()
  })

  it('lets a regular user view only their submitted approval without resolution controls', async () => {
    server.use(
      http.get('/api/auth/users/me', () =>
        HttpResponse.json({ id: 'member-1', email: 'member@example.com', role: 'user', scopes: ['approvals:read'] })
      ),
      http.get('/api/approvals', () => HttpResponse.json({ approvals: [] })),
      http.get('/api/approvals/submissions', () =>
        HttpResponse.json({
          approvals: [
            {
              id: 'upload-1',
              status: 'approved',
              resource_type: 'mcp',
              submitted_by: { id: 'member-1', email: 'member@example.com' },
              resolved_by: { id: 'admin-1', email: 'admin@example.com' },
              payload: { name: 'approved-server' },
            },
          ],
        })
      )
    )

    renderWithQuery(<ApprovalsPage />)

    await userEvent.click(await screen.findByText('MCP Server 上传'))
    expect(screen.getByText('已批准')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /批准/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /拒绝/ })).toBeNull()
  })
})
