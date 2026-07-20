import dayjs from 'dayjs'
import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupUser } from '@/test/user'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '@/shared/i18n'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
import { ChatTaskPanel } from './ChatTaskPanel'
import type { ChatSession } from './types'
import { chatSessionFixture } from './testFixtures'

const historyPush = vi.fn<(path: string) => void>()

vi.mock('@tanstack/react-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@tanstack/react-router')>()),
  useRouter: () => ({ history: { push: historyPush, replace: vi.fn<(path: string) => void>() } }),
  useRouterState: ({ select }: { select: (state: { location: { searchStr: string } }) => unknown }) =>
    select({ location: { searchStr: '' } }),
}))

const emptyMeta = { page: 1, limit: 40, total_pages: 0, total_count: 0, search_time_ms: 0 }

function mockSessions(data: ChatSession[], options?: { error?: boolean; totalPages?: number }) {
  server.use(
    http.get('/api/chat/sessions', () => {
      if (options?.error) {
        return HttpResponse.json({ detail: 'boom' }, { status: 500 })
      }
      return HttpResponse.json({
        data,
        meta: {
          ...emptyMeta,
          total_count: data.length,
          total_pages: options?.totalPages ?? (data.length ? 1 : 0),
        },
      })
    }),
  )
}

describe('ChatTaskPanel', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('zh-CN')
    historyPush.mockReset()
    mockSessions([])
  })

  it('shows conversation title and Conversations creation new chat', async () => {
    const onNewChat = vi.fn<() => void>()
    const user = setupUser()
    renderWithQuery(<ChatTaskPanel variant="page" onNewChat={onNewChat} />)

    expect(await screen.findByText('对话')).toBeTruthy()
    // Ant Design X mounts creation as a <button> inside <ul>; role queries can miss it in jsdom.
    const newChat = await screen.findByText('新对话')
    const trigger = newChat.closest('button') ?? newChat
    await user.click(trigger)
    expect(onNewChat).toHaveBeenCalledOnce()
  })

  it('opens conversations while notifying a mobile drawer to close', async () => {
    const user = setupUser()
    const onNavigate = vi.fn<() => void>()
    mockSessions([
      chatSessionFixture({
        session_id: 'session-1',
        title: '资产风险分析',
        preview: '分析资产风险',
        created_at: dayjs().unix(),
        updated_at: dayjs().unix(),
      }),
    ])
    renderWithQuery(
      <ChatTaskPanel onNavigate={onNavigate} variant="page" />,
    )

    expect(await screen.findByText('资产风险分析')).toBeTruthy()
    await user.click(screen.getByText('资产风险分析'))
    expect(historyPush).toHaveBeenCalledWith('/chat?session=session-1')
    expect(onNavigate).toHaveBeenCalledOnce()
  })

  it('renders an empty state and retries a failed sessions query', async () => {
    const user = setupUser()
    mockSessions([])
    const { unmount } = renderWithQuery(
      <ChatTaskPanel variant="page" />,
    )
    expect(await screen.findByText('暂无对话')).toBeTruthy()

    unmount()
    mockSessions([], { error: true })
    renderWithQuery(<ChatTaskPanel variant="page" />)
    const retry = await screen.findByRole('button', { name: '重试' })
    // After retry, serve success empty list so the query settles.
    mockSessions([])
    await user.click(retry)
    await waitFor(() => expect(screen.queryByRole('button', { name: '重试' })).toBeNull())
  })

  it('localizes the panel and date group labels', async () => {
    await i18n.changeLanguage('en-US')
    mockSessions([
      chatSessionFixture({
        session_id: 'session-1',
        preview: 'Investigate CVE',
        created_at: dayjs().unix(),
        updated_at: dayjs().unix(),
      }),
    ])
    renderWithQuery(<ChatTaskPanel variant="page" />)
    expect(await screen.findByText('Conversations')).toBeTruthy()
    expect(await screen.findByText('Investigate CVE')).toBeTruthy()
    expect(await screen.findByText('Today')).toBeTruthy()
  })

  it('loads more sessions when hasNextPage is true', async () => {
    const user = setupUser()
    let page = 0
    server.use(
      http.get('/api/chat/sessions', ({ request }) => {
        const params = new URL(request.url).searchParams
        page = Number(params.get('page') || '1')
        if (page === 1) {
          return HttpResponse.json({
            data: [
              chatSessionFixture({
                session_id: 'session-1',
                preview: 'First page',
                created_at: dayjs().unix(),
                updated_at: dayjs().unix(),
              }),
            ],
            meta: { page: 1, limit: 40, total_pages: 2, total_count: 41, search_time_ms: 0 },
          })
        }
        return HttpResponse.json({
          data: [
            chatSessionFixture({
              session_id: 'session-2',
              preview: 'Second page',
              created_at: dayjs().unix(),
              updated_at: dayjs().unix(),
            }),
          ],
          meta: { page: 2, limit: 40, total_pages: 2, total_count: 41, search_time_ms: 0 },
        })
      }),
    )
    renderWithQuery(<ChatTaskPanel variant="page" />)
    expect(await screen.findByText('First page')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '加载更多' }))
    expect(await screen.findByText('Second page')).toBeTruthy()
  })

  it('keeps first page visible when load-more fails', async () => {
    const user = setupUser()
    server.use(
      http.get('/api/chat/sessions', ({ request }) => {
        const page = Number(new URL(request.url).searchParams.get('page') || '1')
        if (page === 1) {
          return HttpResponse.json({
            data: [
              chatSessionFixture({
                session_id: 'session-1',
                preview: 'First page stays',
                created_at: dayjs().unix(),
                updated_at: dayjs().unix(),
              }),
            ],
            meta: { page: 1, limit: 40, total_pages: 2, total_count: 41, search_time_ms: 0 },
          })
        }
        return HttpResponse.json({ detail: 'page 2 boom' }, { status: 500 })
      }),
    )
    renderWithQuery(<ChatTaskPanel variant="page" />)
    expect(await screen.findByText('First page stays')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '加载更多' }))
    expect(await screen.findByText(i18n.t('shell:conversations.loadMoreFailed'))).toBeTruthy()
    // Must not replace the whole panel with the initial load-failed state.
    expect(screen.getByText('First page stays')).toBeTruthy()
    expect(screen.queryByText(i18n.t('shell:conversations.loadFailed'))).toBeNull()
  })

  it('keeps search input when server results are empty', async () => {
    const user = setupUser()
    mockSessions([
      chatSessionFixture({
        session_id: 'seed',
        preview: 'seed conversation',
        created_at: dayjs().unix(),
        updated_at: dayjs().unix(),
      }),
    ])
    renderWithQuery(<ChatTaskPanel variant="page" />)
    const search = await screen.findByLabelText(i18n.t('shell:conversations.searchPlaceholder'))
    // Client-side filter after debounce matches; no need to change server payload.
    await user.clear(search)
    await user.type(search, 'no-match-xyz')
    await waitFor(
      () => {
        expect(screen.getByText(i18n.t('shell:conversations.emptySearch'))).toBeTruthy()
      },
      { timeout: 2500 },
    )
    expect(screen.getByLabelText(i18n.t('shell:conversations.searchPlaceholder'))).toBeTruthy()
  })
})
