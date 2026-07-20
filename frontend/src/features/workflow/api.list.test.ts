import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '@/test/server'
import { setToken } from '@/shared/auth/storage'
import { getWorkflow, listWorkflows } from './api'

const definition = (name: string) => ({
  name,
  description: '',
  steps: [
    {
      id: 'triage',
      type: 'step',
      name: 'Triage',
      executor: { kind: 'agent', ref: 'security-operations' },
      instructions: '',
      requires_confirmation: false,
      requires_user_input: false,
      requires_output_review: false,
    },
  ],
})

const workflow = (id: string, name: string, overrides: Record<string, unknown> = {}) => ({
  id,
  name,
  description: '',
  owner_user_id: 'user-1',
  definition: definition(name),
  triggers: {
    webhook: { enabled: false, secret: '' },
    cron: { enabled: false, expression: '', last_run_at: 0 },
  },
  enabled: true,
  version: 1,
  published_version: null,
  published_at: null,
  has_published: false,
  next_cron_at: null,
  created_at: 1,
  updated_at: 1,
  ...overrides,
})

describe('workflow list API (critical)', () => {
  it('returns data/meta envelope and loads a single workflow by id', async () => {
    setToken('token')
    server.use(
      http.get('/api/workflows', ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get('page')).toBe('1')
        expect(url.searchParams.get('limit')).toBe('100')
        return HttpResponse.json({
          data: [workflow('wf-1', 'One')],
          meta: { page: 1, limit: 100, total_count: 3, total_pages: 1, search_time_ms: 1 },
        })
      }),
      http.get('/api/workflows/wf-2', () =>
        HttpResponse.json(
          workflow('wf-2', 'Two', { version: 2, has_published: true, created_at: 2, updated_at: 2 }),
        ),
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

  it('forwards library search q', async () => {
    setToken('token')
    server.use(
      http.get('/api/workflows', ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get('q')).toBe('triage')
        return HttpResponse.json({
          data: [],
          meta: { page: 1, limit: 100, total_count: 0, total_pages: 0, search_time_ms: 0 },
        })
      }),
    )
    const list = await listWorkflows(1, 100, 'triage')
    expect(list.data).toEqual([])
  })

  it('rejects malformed definitions instead of silently repairing nodes or choices', async () => {
    setToken('token')
    server.use(
      http.get('/api/workflows/wf-invalid', () =>
        HttpResponse.json(
          workflow('wf-invalid', 'Invalid', {
            definition: {
              name: 'Invalid',
              description: '',
              steps: [
                { type: 'step', name: 'Missing node id', executor: { kind: 'agent', ref: 'security-operations' } },
                { id: 'missing-type', name: 'Missing type', executor: { kind: 'agent', ref: 'security-operations' } },
                { id: 'missing-executor', type: 'step', name: 'Missing executor' },
                {
                  id: 'router',
                  type: 'router',
                  name: 'Route',
                  selector: { cel: 'input' },
                  choices: [
                    { name: 'missing-choice-id', steps: [] },
                    { id: 'valid-choice', name: 'valid', steps: [] },
                  ],
                },
              ],
            },
          }),
        ),
      ),
    )

    await expect(getWorkflow('wf-invalid')).rejects.toThrow('getWorkflow: invalid workflow payload')
  })
})
