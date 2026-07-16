import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { getApprovals, resolveApproval, resolveSubmissionApproval, resumeApproval } from './api'

const submission = (id: string) => ({
  id,
  kind: 'upload',
  status: 'pending',
  resource_type: 'skill',
  created_at: 1,
  submitted_by: { id: 'u1', email: 'a@b.c' },
})

describe('getApprovals', () => {
  it('pages upload submissions with data/meta totals', async () => {
    server.use(
      http.get('/api/approvals/submissions', ({ request }) => {
        const url = new URL(request.url)
        const page = Number(url.searchParams.get('page') ?? '1')
        const limit = Number(url.searchParams.get('limit') ?? '20')
        const start = (page - 1) * limit
        const rows = Array.from({ length: Math.min(limit, Math.max(0, 25 - start)) }, (_, i) =>
          submission(`s${start + i}`),
        )
        return HttpResponse.json({
          data: rows,
          meta: { page, limit, total_count: 25, total_pages: 3 },
        })
      }),
    )

    const first = await getApprovals({ status: 'pending', kind: 'upload', page: 1, limit: 10 })
    expect(first.data.map((item) => item.id)).toEqual(
      Array.from({ length: 10 }, (_, i) => `s${i}`),
    )
    expect(first.meta.total_count).toBe(25)

    const second = await getApprovals({ status: 'pending', kind: 'upload', page: 2, limit: 10 })
    expect(second.data.map((item) => item.id)).toEqual(
      Array.from({ length: 10 }, (_, i) => `s${10 + i}`),
    )
  })

  it('loads kind=all via server combined list', async () => {
    server.use(
      http.get('/api/approvals', ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get('combined')).toBe('true')
        expect(url.searchParams.get('status')).toBe('pending')
        expect(url.searchParams.get('page')).toBe('1')
        expect(url.searchParams.get('limit')).toBe('10')
        return HttpResponse.json({
          data: [
            submission('u0'),
            submission('u1'),
            {
              id: 'h0',
              status: 'pending',
              source_type: 'agent',
              created_at: 1,
            },
            {
              id: 'h1',
              status: 'pending',
              source_type: 'agent',
              created_at: 1,
            },
          ],
          meta: { page: 1, limit: 10, total_count: 4, total_pages: 1, search_time_ms: 0 },
        })
      }),
    )

    const result = await getApprovals({ status: 'pending', kind: 'all', page: 1, limit: 10 })
    expect(result.data.map((item) => item.id)).toEqual(['u0', 'u1', 'h0', 'h1'])
    expect(result.meta.total_count).toBe(4)
  })
})

describe('resolve/resume normalization', () => {
  it('returns normalized approval without casting invalid payloads', async () => {
    server.use(
      http.post('/api/approvals/appr-1/resolve', () =>
        HttpResponse.json({
          id: 'appr-1',
          status: 'approved',
          source_type: 'workflow',
          created_at: 1,
        }),
      ),
    )
    const row = await resolveApproval('appr-1', 'approved')
    expect(row).toMatchObject({ id: 'appr-1', status: 'approved', source_type: 'workflow' })
  })

  it('throws when resolve payload is missing id', async () => {
    server.use(http.post('/api/approvals/appr-1/resolve', () => HttpResponse.json({ status: 'approved' })))
    await expect(resolveApproval('appr-1', 'approved')).rejects.toThrow(/invalid approval payload/)
  })

  it('normalizes resume and submission resolve responses', async () => {
    server.use(
      http.post('/api/approvals/appr-2/resume', () =>
        HttpResponse.json({ id: 'appr-2', status: 'approved', source_type: 'agent', created_at: 1 }),
      ),
      http.post('/api/approvals/submissions/sub-1/resolve', () =>
        HttpResponse.json({
          id: 'sub-1',
          status: 'rejected',
          resource_type: 'skill',
          rejection_reason: 'bad zip',
          created_at: 1,
        }),
      ),
    )
    await expect(resumeApproval('appr-2')).resolves.toMatchObject({ id: 'appr-2', status: 'approved' })
    await expect(resolveSubmissionApproval('sub-1', 'rejected', 'bad zip')).resolves.toMatchObject({
      id: 'sub-1',
      status: 'rejected',
      rejection_reason: 'bad zip',
    })
  })
})
