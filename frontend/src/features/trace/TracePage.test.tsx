import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
import { TracePage } from './TracePage'
import type { Trace, TraceSessionSummary } from './types'

const routerMock = vi.hoisted(() => ({ push: vi.fn(), searchStr: '' }))

vi.mock('@tanstack/react-router', async (importOriginal) => ({
  ...await importOriginal<typeof import('@tanstack/react-router')>(),
  useRouter: () => ({ history: { push: routerMock.push } }),
  useRouterState: ({ select }: { select: (state: { location: { searchStr: string } }) => unknown }) => select({ location: { searchStr: routerMock.searchStr } }),
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

const tracesFor = (sessionId: string, page: number): Trace[] => {
  const owner = sessionId || 'all'
  const items = Array.from({ length: 7 }, (_, index) => ({
    trace_id: `${owner}-trace-${index + 1}`,
    session_id: sessionId || `s${index + 1}`,
    run_id: `${owner}-run-${index + 1}`,
    name: `Run ${index + 1}`,
    status: 'OK',
    duration_ms: 1000 + index,
    start_time: `2026-07-${String(20 - index).padStart(2, '0')}T12:00:00Z`,
    end_time: '',
  }))
  return items.slice((page - 1) * 6, page * 6)
}

let traceRequests: URLSearchParams[] = []

const cardByTitle = (title: string) => {
  const card = screen.getByText(title).closest('.ant-card')
  if (!card) throw new Error(`Unable to find ${title} card`)
  return card as HTMLElement
}

const clickPage = async (card: HTMLElement, page: number) => {
  await userEvent.click(within(card).getByTitle(String(page)))
}

describe('TracePage interactions', () => {
  beforeEach(() => {
    routerMock.push.mockReset()
    routerMock.searchStr = ''
    traceRequests = []
    server.use(
      http.get('/api/auth/users/me', () => HttpResponse.json({ id: 'user-1', email: 'user@example.com', role: 'user', scopes: ['traces:read'], is_active: true })),
      http.get('/api/chat/sessions', () => HttpResponse.json([])),
      http.get('/api/traces/sessions', () => HttpResponse.json({ items: traceSessions, total_count: traceSessions.length, page: 1, limit: 200 })),
      http.get('/api/traces', ({ request }) => {
        const url = new URL(request.url)
        const params = new URLSearchParams(url.search)
        traceRequests.push(params)
        const page = Number(params.get('page') ?? '1')
        return HttpResponse.json({ items: tracesFor(params.get('session_id') ?? '', page), total_count: 7, page, limit: 6 })
      }),
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

  it('selects a Session through selected_session without filling the Session ID input', async () => {
    renderWithQuery(<TracePage />)

    expect(await screen.findByText('Session 1')).toBeTruthy()
    const sessionInput = screen.getByPlaceholderText('Session ID') as HTMLInputElement
    await clickPage(cardByTitle('Sessions'), 2)
    await userEvent.click(await screen.findByRole('button', { name: /Session 9/ }))

    expect(sessionInput.value).toBe('')
    expect(routerMock.push).toHaveBeenLastCalledWith('/trace?selected_session=s9')
    await waitFor(() => expect(traceRequests.some((params) => params.get('session_id') === 's9')).toBe(true))
  })

  it('submits Session ID searches as filters and clears selected_session', async () => {
    const user = userEvent.setup()
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

    expect(await screen.findByText(/Run 1/)).toBeTruthy()
    await clickPage(cardByTitle('Runs & Spans'), 2)

    await waitFor(() => expect(traceRequests.some((params) => params.get('page') === '2')).toBe(true))
    const pageTwoRequests = traceRequests.filter((params) => params.get('page') === '2')
    const pageTwoRequest = pageTwoRequests[pageTwoRequests.length - 1]
    expect(routerMock.push).not.toHaveBeenCalled()
    expect(pageTwoRequest?.has('run_id')).toBe(false)
  })
})
