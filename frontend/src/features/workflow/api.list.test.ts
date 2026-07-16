import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '@/test/server'
import { AUTH_TOKEN_STORAGE_KEY } from '@/shared/auth/storage'
import { getWorkflow, listWorkflows } from './api'

describe('workflow list API', () => {
  it('returns data/meta envelope and loads a single workflow by id', async () => {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, 'token')
    server.use(
      http.get('/api/workflows', ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get('page')).toBe('1')
        expect(url.searchParams.get('limit')).toBe('100')
        return HttpResponse.json({
          data: [
            {
              id: 'wf-1',
              name: 'One',
              description: '',
              definition: { name: 'One', description: '', steps: [] },
              version: 1,
              has_published: false,
              created_at: 1,
              updated_at: 1,
            },
          ],
          meta: { page: 1, limit: 100, total_count: 3, total_pages: 1, search_time_ms: 1 },
        })
      }),
      http.get('/api/workflows/wf-2', () =>
        HttpResponse.json({
          id: 'wf-2',
          name: 'Two',
          description: '',
          definition: { name: 'Two', description: '', steps: [] },
          version: 2,
          has_published: true,
          created_at: 2,
          updated_at: 2,
        }),
      ),
    )

    const list = await listWorkflows(1, 100)
    expect(list.data).toHaveLength(1)
    expect(list.meta.total_count).toBe(3)
    expect(list.data[0]?.id).toBe('wf-1')

    const row = await getWorkflow('wf-2')
    expect(row.id).toBe('wf-2')
    expect(row.name).toBe('Two')
  })
})
