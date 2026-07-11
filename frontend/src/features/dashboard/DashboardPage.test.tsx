import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
import { DashboardPage } from './DashboardPage'

vi.mock('echarts-for-react', () => ({ default: () => <div data-testid="runtime-chart" /> }))

const overview = (audit = false) => ({
  generated_at: '2026-07-12T12:00:00Z',
  range: '24h',
  health: { status: 'ready' },
  metrics: { total_runs: 4, failed_runs: 1, failure_rate: 0.25, p50_duration_ms: 10, p95_duration_ms: 30, total_tokens: 12 },
  series: [{ timestamp: '2026-07-12T11:00:00Z', runs: 4, failed_runs: 1, p50_duration_ms: 10, p95_duration_ms: 30 }],
  distributions: { agent: [{ name: 'security-agent', value: 4 }], workflow: [], team: [] },
  recent_failures: [],
  snapshots: { evaluation: { total: 2, passed: 1, failed: 1, pass_rate: 0.5 } },
  ...(audit ? { audit: { recent: [{ id: 1, action: 'chat.run', resource_type: 'chat', resource_id: 'r1', actor_email: 'admin@example.com', status: 'success', created_at: '2026-07-12T11:00:00Z' }] } } : {}),
})

describe('runtime overview page', () => {
  it('changes the aggregate window instead of reusing the existing result', async () => {
    const requests: string[] = []
    server.use(http.get('/api/overview', ({ request }) => {
      requests.push(new URL(request.url).searchParams.get('range') ?? '')
      return HttpResponse.json(overview())
    }))
    renderWithQuery(<DashboardPage />)
    await waitFor(() => expect(requests).toContain('24h'))
    fireEvent.click(screen.getByText('7d'))
    await waitFor(() => expect(requests).toContain('7d'))
  })

  it('only renders audit activity when the authorized response includes it', async () => {
    server.use(http.get('/api/overview', () => HttpResponse.json(overview(true))))
    renderWithQuery(<DashboardPage />)
    expect(await screen.findByText('近期审计活动')).toBeTruthy()
    expect(screen.getByText('chat.run')).toBeTruthy()
  })
})
