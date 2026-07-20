import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '@/test/server'
import { setToken } from '@/shared/auth/storage'
import {
  getWorkflow,
  listExecutors,
  listWorkflowTemplates,
  listWorkflowTriggerHistory,
  listWorkflowVersions,
  listWorkflows,
} from './api'

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

describe('workflow list API', () => {
  it('returns data/meta envelope and loads a single workflow by id', async () => {
    setToken('token')
    server.use(
      http.get('/api/workflows', ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get('page')).toBe('1')
        expect(url.searchParams.get('limit')).toBe('100')
        return HttpResponse.json({
          data: [
            workflow('wf-1', 'One'),
          ],
          meta: { page: 1, limit: 100, total_count: 3, total_pages: 1, search_time_ms: 1 },
        })
      }),
      http.get('/api/workflows/wf-2', () =>
        HttpResponse.json(workflow('wf-2', 'Two', { version: 2, has_published: true, created_at: 2, updated_at: 2 })),
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
        HttpResponse.json(workflow('wf-invalid', 'Invalid', {
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
        })),
      ),
    )

    await expect(getWorkflow('wf-invalid')).rejects.toThrow('getWorkflow: invalid workflow payload')
  })

  it('rejects workflow records missing canonical top-level fields', async () => {
    setToken('token')
    const missingTriggers = workflow('wf-missing', 'Missing')
    Reflect.deleteProperty(missingTriggers, 'triggers')
    server.use(http.get('/api/workflows/wf-missing', () => HttpResponse.json(missingTriggers)))

    await expect(getWorkflow('wf-missing')).rejects.toThrow('getWorkflow: invalid workflow payload')
  })

  it('reads static catalogs from complete data/meta envelopes', async () => {
    setToken('token')
    server.use(
      http.get('/api/workflows/executors', () =>
        HttpResponse.json({
          data: [
            {
              ref: 'security-operations',
              kind: 'agent',
              name: 'Security Operations',
              description: 'Investigate alerts',
              category: 'operations',
              capabilities: 'skills,hitl',
              recommended_for: 'Alert triage',
              role: 'Analyst',
            },
          ],
          meta: { page: 1, limit: 1, total_count: 1, total_pages: 1, search_time_ms: 0 },
        }),
      ),
      http.get('/api/workflows/templates', () =>
        HttpResponse.json({
          data: [
            {
              id: 'triage',
              name: 'Triage',
              description: '',
              category: 'security',
              tags: [],
              definition: definition('Triage'),
            },
          ],
          meta: { page: 1, limit: 1, total_count: 1, total_pages: 1, search_time_ms: 0 },
        }),
      ),
    )

    await expect(listExecutors()).resolves.toMatchObject([{ ref: 'security-operations' }])
    await expect(listWorkflowTemplates()).resolves.toMatchObject([{ id: 'triage', name: 'Triage' }])
  })

  it('accepts sparse step HITL flags used by built-in templates', async () => {
    setToken('token')
    server.use(
      http.get('/api/workflows/templates', () =>
        HttpResponse.json({
          data: [
            {
              id: 'ir-triage',
              name: 'Incident triage (IR)',
              description: 'Classify severity',
              category: 'incident_response',
              tags: ['security'],
              definition: {
                name: 'Incident triage',
                description: 'Security IR',
                steps: [
                  {
                    id: 'triage',
                    type: 'step',
                    name: 'Triage alert',
                    executor: { kind: 'agent', ref: 'security-operations' },
                    instructions: 'Summarize the alert',
                    skills: ['cve-intel-skill'],
                    position: { x: 80, y: 80 },
                  },
                  {
                    id: 'severity',
                    type: 'condition',
                    name: 'Critical?',
                    evaluator: { cel: 'true' },
                    steps: [
                      {
                        id: 'contain',
                        type: 'step',
                        name: 'Contain',
                        executor: { kind: 'agent', ref: 'security-operations' },
                        instructions: 'Propose containment',
                        requires_confirmation: true,
                        confirmation_message: 'Approve containment?',
                        position: { x: 420, y: 40 },
                      },
                    ],
                    else: [
                      {
                        id: 'report',
                        type: 'step',
                        name: 'Report',
                        executor: { kind: 'agent', ref: 'safe-fallback' },
                        instructions: 'Write a note',
                        position: { x: 420, y: 200 },
                      },
                    ],
                    position: { x: 280, y: 80 },
                  },
                ],
              },
            },
          ],
          meta: { page: 1, limit: 1, total_count: 1, total_pages: 1, search_time_ms: 0 },
        }),
      ),
    )

    await expect(listWorkflowTemplates()).resolves.toMatchObject([
      {
        id: 'ir-triage',
        definition: {
          steps: [
            {
              id: 'triage',
              requires_confirmation: false,
              requires_user_input: false,
              requires_output_review: false,
            },
            {
              id: 'severity',
              steps: [{ id: 'contain', requires_confirmation: true }],
            },
          ],
        },
      },
    ])
  })

  it('rejects malformed static catalog rows instead of silently omitting or coercing them', async () => {
    setToken('token')
    server.use(
      http.get('/api/workflows/executors', () =>
        HttpResponse.json({
          data: [{ ref: 'security-operations', kind: 'agent', name: 'Security Operations', description: 'Investigate alerts' }],
          meta: { page: 1, limit: 1, total_count: 1, total_pages: 1, search_time_ms: 0 },
        }),
      ),
      http.get('/api/workflows/templates', () =>
        HttpResponse.json({
          data: [
            {
              id: 'triage',
              name: 'Triage',
              description: '',
              category: 'security',
              tags: ['security', 1],
              definition: definition('Triage'),
            },
          ],
          meta: { page: 1, limit: 1, total_count: 1, total_pages: 1, search_time_ms: 0 },
        }),
      ),
    )

    await expect(listExecutors()).rejects.toThrow('listExecutors: invalid workflow executor payload')
    await expect(listWorkflowTemplates()).rejects.toThrow('listWorkflowTemplates: invalid workflow template payload')
  })

  it('requires canonical workflow version rows', async () => {
    setToken('token')
    server.use(
      http.get('/api/workflows/wf-1/versions', () =>
        HttpResponse.json({
          data: [
            {
              id: 'version-1',
              version: 1,
              name: 'Draft',
              description: '',
              definition: definition('Draft'),
              created_at: 1,
              created_by: 'user-1',
            },
          ],
          meta: { page: 1, limit: 100, total_count: 1, total_pages: 1, search_time_ms: 0 },
        }),
      ),
    )

    await expect(listWorkflowVersions('wf-1')).rejects.toThrow(
      'listWorkflowVersions: invalid workflow version payload',
    )
  })

  it('requires canonical workflow trigger history rows', async () => {
    setToken('token')
    let malformed = false
    server.use(
      http.get('/api/workflows/wf-1/triggers/history', () =>
        HttpResponse.json({
          data: [
            malformed
              ? { id: 1, action: 'workflow.trigger.cron', source: 'cron', run_id: 'run-1', session_id: 'session-1', expression: '', created_at: '2026-07-19T00:00:00Z' }
              : { id: 1, action: 'workflow.trigger.cron', status: 'success', source: 'cron', run_id: 'run-1', session_id: 'session-1', expression: '', created_at: '2026-07-19T00:00:00Z' },
          ],
          meta: { page: 1, limit: 20, total_count: 1, total_pages: 1, search_time_ms: 0 },
        }),
      ),
    )

    await expect(listWorkflowTriggerHistory('wf-1')).resolves.toMatchObject({ data: [{ id: 1 }] })
    malformed = true
    await expect(listWorkflowTriggerHistory('wf-1')).rejects.toThrow(
      'listWorkflowTriggerHistory: invalid workflow trigger history payload',
    )
  })

})
