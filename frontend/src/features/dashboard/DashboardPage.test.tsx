import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
import { DashboardPage } from './DashboardPage'

const routerMock = vi.hoisted(() => ({ push: vi.fn<(path: string) => void>() }))

vi.mock('@tanstack/react-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@tanstack/react-router')>()),
  useRouter: () => ({ history: { push: routerMock.push } }),
}))

vi.mock('echarts-for-react', () => ({
  default: ({ option }: { option: { animationDuration?: number; animationDurationUpdate?: number } }) => (
    <div
      data-testid="runtime-chart"
      data-animation-duration={option.animationDuration}
      data-update-animation-duration={option.animationDurationUpdate}
    />
  ),
}))

const overview = (audit = false): import('./types').RuntimeOverview => ({
  generated_at: '2026-07-12T12:00:00Z',
  range: '24h',
  health: { status: 'ready' },
  metrics: {
    total_runs: 4,
    failed_runs: 1,
    failure_rate: 0.25,
    p50_duration_ms: 10,
    p95_duration_ms: 30,
    input_tokens: 7,
    output_tokens: 5,
    total_tokens: 12,
  },
  series: [
    {
      timestamp: '2026-07-12T11:00:00Z',
      runs: 4,
      failed_runs: 1,
      p50_duration_ms: 10,
      p95_duration_ms: 30,
      input_tokens: 7,
      output_tokens: 5,
      total_tokens: 12,
    },
  ],
  distributions: { agent: [{ name: 'security-agent', value: 4 }], workflow: [], team: [] },
  recent_failures: [],
  snapshots: {
    evaluation: { total: 2, passed: 1, failed: 1, pass_rate: 0.5 },
    approvals: { pending: 2, approved: 5, rejected: 1 },
  },
  ...(audit
    ? {
        audit: {
          recent: [
            {
              id: 1,
              action: 'chat.run',
              resource_type: 'chat',
              resource_id: 'r1',
              actor_email: 'admin@example.com',
              status: 'success',
              created_at: '2026-07-12T11:00:00Z',
            },
          ],
        },
      }
    : {}),
})

describe('runtime overview page', () => {
  it('changes the aggregate window instead of reusing the existing result', async () => {
    const requests: string[] = []
    server.use(
      http.get('/api/overview', ({ request }) => {
        requests.push(new URL(request.url).searchParams.get('range') ?? '')
        return HttpResponse.json(overview())
      })
    )
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

  it('marks the first received data for staged entry and configures chart update animation', async () => {
    server.use(http.get('/api/overview', () => HttpResponse.json(overview())))
    const { container } = renderWithQuery(<DashboardPage />)

    await waitFor(() => expect(container.querySelector('.dashboard-page')?.classList.contains('dashboard-data-ready')).toBe(true))
    expect(screen.getAllByTestId('runtime-chart')).toHaveLength(3)
    expect(screen.getAllByTestId('runtime-chart')[0].getAttribute('data-animation-duration')).toBe('260')
    expect(screen.getAllByTestId('runtime-chart')[0].getAttribute('data-update-animation-duration')).toBe('260')
    expect(container.querySelector('.dashboard-health-indicator')?.classList.contains('is-pulsing')).toBe(false)
  })

  it('keeps token totals in the combined runtime timeline when the selected range has no token usage', async () => {
    const response = overview()
    response.metrics = { ...response.metrics, input_tokens: 0, output_tokens: 0, total_tokens: 0 }
    response.series = response.series.map((item) => ({ ...item, input_tokens: 0, output_tokens: 0, total_tokens: 0 }))
    server.use(http.get('/api/overview', () => HttpResponse.json(response)))
    renderWithQuery(<DashboardPage />)

    expect(await screen.findByText('输入 Token')).toBeTruthy()
    expect(screen.getByText('输出 Token')).toBeTruthy()
    expect(screen.getByText('运行时间轴与 Token 使用量')).toBeTruthy()
    expect(screen.queryByText('点击时间桶查看 Trace')).toBeNull()
    expect(screen.queryByText('当前窗口暂无 Token 使用记录')).toBeNull()
  })

  it('navigates to Trace with canonical query params from recent failures', async () => {
    routerMock.push.mockClear()
    const response = overview()
    response.recent_failures = [
      {
        trace_id: 'trace-fail-1',
        name: 'failed run',
        status: 'ERROR',
        duration_ms: 42,
        start_time: '2026-07-12T11:30:00Z',
        session_id: 'session-fail',
        run_id: 'run-fail',
        agent_id: 'security-agent',
      },
    ]
    server.use(http.get('/api/overview', () => HttpResponse.json(response)))
    renderWithQuery(<DashboardPage />)
    fireEvent.click(await screen.findByText('failed run'))
    await waitFor(() => {
      expect(routerMock.push).toHaveBeenCalled()
    })
    const target = String(routerMock.push.mock.calls.at(-1)?.[0] ?? '')
    expect(target.startsWith('/trace?')).toBe(true)
    const params = new URLSearchParams(target.slice(target.indexOf('?')))
    expect(params.get('session_id')).toBe('session-fail')
    expect(params.get('run_id')).toBe('run-fail')
    expect(params.get('selected_session')).toBe('session-fail')
    expect(params.get('trace')).toBe('trace-fail-1')
    expect(params.has('session')).toBe(false)
    expect(params.has('run')).toBe(false)
  })
})
