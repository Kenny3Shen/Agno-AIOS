import { useState } from 'react'
import { screen, waitFor, within } from '@testing-library/react'
import { user } from '@/test/user'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
import { TracePage } from './TracePage'
import type { TraceSessionSummary } from './types'

const routerMock = vi.hoisted(() => ({ push: vi.fn<(path: string) => void>(), searchStr: '' }))

vi.mock('@tanstack/react-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@tanstack/react-router')>()),
  useRouter: () => ({ history: { push: routerMock.push } }),
  useRouterState: ({ select }: { select: (state: { location: { searchStr: string } }) => unknown }) =>
    select({ location: { searchStr: routerMock.searchStr } }),
}))

const traceSessions: TraceSessionSummary[] = Array.from({ length: 9 }, (_, index) => ({
  session_id: `s${index + 1}`,
  name: `Session ${index + 1}`,
  latest_start_time: `2026-07-${String(20 - index).padStart(2, '0')}T12:00:00Z`,
  trace_count: 7,
  run_count: 7,
  error_count: 0,
  status: 'OK',
  user_id: 'user-1',
}))

const tracesFor = (sessionId: string, page: number) => {
  const owner = sessionId || 'all'
  const items = Array.from({ length: 7 }, (_, index) => ({
    trace_id: `${owner}-trace-${index + 1}`,
    session_id: sessionId || `s${index + 1}`,
    run_id: `${owner}-run-${index + 1}`,
    name: `Run ${index + 1}`,
    status: 'OK',
    duration: `${((1000 + index) / 1000).toFixed(2)}s`,
    start_time: `2026-07-${String(20 - index).padStart(2, '0')}T12:00:00Z`,
    end_time: '',
  }))
  return items.slice((page - 1) * 6, page * 6)
}

const traceDetail = (traceId: string) => {
  const runNumber = traceId.match(/-(\d+)$/)?.[1] ?? '1'
  const root = {
    span_id: `${traceId}-root`,
    name: `Run ${runNumber}`,
    status_code: 'OK',
    duration: '1.00s',
    start_time: '2026-07-20T12:00:00Z',
    parsed: { input: `root input ${runNumber}` },
  }
  const child = {
    span_id: `${traceId}-child`,
    parent_span_id: root.span_id,
    name: `Child ${runNumber}`,
    status_code: 'OK',
    duration: '100ms',
    start_time: '2026-07-20T12:00:00Z',
    parsed: { input: `child input ${runNumber}` },
  }
  return { trace: { trace_id: traceId }, spans: [root, child], tree: [{ span: root, children: [{ span: child, children: [] }] }] }
}

let traceRequests: URLSearchParams[] = []

const cardByTitle = (title: string) => {
  const card = screen.getByText(title).closest('.ant-card')
  if (!card) throw new Error(`Unable to find ${title} card`)
  return card as HTMLElement
}

const clickPage = async (card: HTMLElement, page: number) => {
  await user.click(within(card).getByTitle(String(page)))
}

const RouteHarness = () => {
  const [, setVersion] = useState(0)
  return (
    <>
      <TracePage />
      <button type="button" onClick={() => setVersion((version) => version + 1)}>
        Sync route
      </button>
    </>
  )
}

describe('TracePage interactions', () => {
  beforeEach(() => {
    routerMock.push.mockReset()
    routerMock.searchStr = ''
    traceRequests = []
    server.use(
      http.get('/api/auth/users/me', () =>
        HttpResponse.json({ id: 'user-1', email: 'user@example.com', role: 'user', scopes: ['traces:read'], is_active: true })
      ),
      http.get('/api/chat/sessions', () => HttpResponse.json({ data: [], meta: { page: 1, limit: 40, total_pages: 0, total_count: 0, search_time_ms: 0 } })),
      http.get('/api/traces/sessions', ({ request }) => {
        const url = new URL(request.url)
        const page = Number(url.searchParams.get('page') ?? '1')
        const limit = Number(url.searchParams.get('limit') ?? '8')
        const start = (page - 1) * limit
        return HttpResponse.json({
          data: traceSessions.slice(start, start + limit),
          meta: {
            page,
            limit,
            total_count: traceSessions.length,
            total_pages: Math.ceil(traceSessions.length / limit),
            search_time_ms: 0,
          },
        })
      }),
      http.get('/api/traces', ({ request }) => {
        const url = new URL(request.url)
        const params = new URLSearchParams(url.search)
        traceRequests.push(params)
        const page = Number(params.get('page') ?? '1')
        return HttpResponse.json({
          data: tracesFor(params.get('session_id') ?? '', page),
          meta: { page, limit: 6, total_count: 7, total_pages: 2, search_time_ms: 0 },
        })
      }),
      http.get('/api/traces/:traceId', ({ params }) => HttpResponse.json(traceDetail(String(params.traceId))))
    )
  })

  it('changes the Session page without writing Session ID filter state', async () => {
    renderWithQuery(<TracePage />)

    expect(await screen.findByText('Session 1')).toBeTruthy()
    const sessionInput = screen.getByPlaceholderText('Session ID') as HTMLInputElement
    await clickPage(cardByTitle('Sessions'), 2)

    expect(await screen.findByText('Session 9')).toBeTruthy()
    expect(sessionInput.value).toBe('')
    expect(routerMock.push).not.toHaveBeenCalled()
  })

  it('keeps Runs & Spans empty until a Session or Run ID is selected', async () => {
    renderWithQuery(<TracePage />)

    expect(await screen.findByText('Session 1')).toBeTruthy()
    expect(within(cardByTitle('Runs & Spans')).queryByText(/Run 1/)).toBeNull()
    expect(traceRequests).toHaveLength(0)
  })

  it('selects a Session through selected_session without filling the Session ID input', async () => {
    renderWithQuery(<RouteHarness />)

    expect(await screen.findByText('Session 1')).toBeTruthy()
    const sessionInput = screen.getByPlaceholderText('Session ID') as HTMLInputElement
    await clickPage(cardByTitle('Sessions'), 2)
    await user.click(await screen.findByRole('button', { name: /Session 9/ }))

    expect(sessionInput.value).toBe('')
    expect(routerMock.push).toHaveBeenLastCalledWith('/trace?selected_session=s9')
    await waitFor(() => expect(traceRequests.some((params) => params.get('session_id') === 's9')).toBe(true))

    routerMock.searchStr = '?selected_session=s9'
    await user.click(screen.getByRole('button', { name: 'Sync route' }))

    expect((await screen.findByRole('button', { name: /Session 9/ })).getAttribute('aria-pressed')).toBe('true')
    expect(within(cardByTitle('Sessions')).queryByText('Session 1')).toBeNull()
  })

  it('submits Session ID searches as filters and clears selected_session', async () => {
    renderWithQuery(<TracePage />)

    const sessionInput = await screen.findByPlaceholderText('Session ID')
    await user.type(sessionInput, 'manual-session')
    await user.click(screen.getByRole('button', { name: /查询/ }))

    const pushed = String(routerMock.push.mock.calls.at(-1)?.[0] ?? '')
    const query = new URLSearchParams(pushed.split('?')[1] ?? '')
    expect(query.get('session_id')).toBe('manual-session')
    expect(query.has('selected_session')).toBe(false)
  })

  it('changes the Run page without selecting a run or writing run_id', async () => {
    renderWithQuery(<TracePage />)

    await user.click(await screen.findByRole('button', { name: /Session 1/ }))
    expect(await within(cardByTitle('Runs & Spans')).findByText(/Run 1/)).toBeTruthy()
    routerMock.push.mockClear()
    await clickPage(cardByTitle('Runs & Spans'), 2)

    await waitFor(() => expect(traceRequests.some((params) => params.get('page') === '2')).toBe(true))
    const pageTwoRequests = traceRequests.filter((params) => params.get('page') === '2')
    const pageTwoRequest = pageTwoRequests[pageTwoRequests.length - 1]
    expect(routerMock.push).not.toHaveBeenCalled()
    expect(pageTwoRequest?.has('run_id')).toBe(false)
  })

  it('renders root spans as the top-level Run summaries and preserves span detail selection', async () => {
    renderWithQuery(<TracePage />)

    await user.click(await screen.findByRole('button', { name: /Session 1/ }))
    const runsCard = cardByTitle('Runs & Spans')
    const root = await within(runsCard).findByText('Run root · Run 1')
    expect(within(runsCard).queryByText('Run · Run 1')).toBeNull()
    const rootRow = root.closest('.run-tree-node')
    expect(rootRow?.textContent).toContain('OK')
    expect(rootRow?.textContent).toContain('1.00s')

    await user.click(root)
    expect(await screen.findByText('root input 1')).toBeTruthy()
    const rootNode = root.closest('.ant-tree-treenode')
    const switcher = rootNode?.querySelector('.ant-tree-switcher')
    if (!switcher) throw new Error('Expected root span to be expandable')
    await user.click(switcher)
    const child = await within(runsCard).findByText('Span · Child 1')
    await user.click(child)
    expect(await within(cardByTitle('Detail')).findByText('child input 1')).toBeTruthy()
  })
})
