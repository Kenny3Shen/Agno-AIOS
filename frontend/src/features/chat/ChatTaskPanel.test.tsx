import dayjs from 'dayjs'
import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupUser } from '@/test/user'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '@/shared/i18n'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
import { buildConversationItems, filterConversationItems, ChatTaskPanel } from './ChatTaskPanel'
import type { ChatSession } from './types'

const historyPush = vi.fn<(path: string) => void>()

vi.mock('@tanstack/react-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@tanstack/react-router')>()),
  useRouter: () => ({ history: { push: historyPush, replace: vi.fn() } }),
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

describe('conversation list mapping', () => {
  it('filters conversations by title or session id', () => {
    const items = buildConversationItems([
      {
        session_id: 'abc-risk',
        preview: '分析资产风险',
        created_at: 1,
        updated_at: 2,
      },
      {
        session_id: 'other',
        preview: 'Hello',
        created_at: 1,
        updated_at: 3,
      },
    ])
    expect(filterConversationItems(items, '风险').map((item) => item.key)).toEqual(['abc-risk'])
    expect(filterConversationItems(items, 'OTHER').map((item) => item.key)).toEqual(['other'])
    expect(filterConversationItems(items, '  ').map((item) => item.key)).toEqual(['other', 'abc-risk'])
  })

  it('prefixes workflow sessions with [WF] for recents scanning', () => {
    const items = buildConversationItems([
      {
        session_id: 'wf-1',
        session_type: 'workflow',
        preview: 'IR triage',
        created_at: 1,
        updated_at: 2,
      },
      {
        session_id: 'agent-1',
        session_type: 'agent',
        preview: 'CVE lookup',
        created_at: 1,
        updated_at: 3,
      },
      {
        session_id: 'wf-2',
        session_type: 'workflow',
        title: '[WF] already tagged',
        preview: 'x',
        created_at: 1,
        updated_at: 4,
      },
    ])
    expect(items.find((item) => item.key === 'wf-1')?.label).toBe('[WF] IR triage')
    expect(items.find((item) => item.key === 'agent-1')?.label).toBe('CVE lookup')
    expect(items.find((item) => item.key === 'wf-2')?.label).toBe('[WF] already tagged')
  })

  it('sorts sessions by update time and assigns stable date group keys', () => {
    const now = dayjs('2026-07-13T12:00:00').valueOf()
    const items = buildConversationItems(
      [
        {
          session_id: 'earlier',
          preview: 'Earlier',
          created_at: dayjs('2026-07-10T08:00:00').unix(),
          updated_at: dayjs('2026-07-10T08:00:00').unix(),
        },
        {
          session_id: 'today',
          preview: 'Today',
          created_at: dayjs('2026-07-13T09:00:00').unix(),
          updated_at: dayjs('2026-07-13T09:00:00').unix(),
        },
        {
          session_id: 'yesterday',
          preview: 'Yesterday',
          created_at: dayjs('2026-07-12T09:00:00').unix(),
          updated_at: dayjs('2026-07-12T09:00:00').unix(),
        },
      ],
      now,
    )

    expect(items.map(({ key, group }) => ({ key, group }))).toEqual([
      { key: 'today', group: 'today' },
      { key: 'yesterday', group: 'yesterday' },
      { key: 'earlier', group: 'earlier' },
    ])
  })
})

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
      {
        session_id: 'session-1',
        title: '资产风险分析',
        preview: '分析资产风险',
        created_at: dayjs().unix(),
        updated_at: dayjs().unix(),
      },
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
      {
        session_id: 'session-1',
        preview: 'Investigate CVE',
        created_at: dayjs().unix(),
        updated_at: dayjs().unix(),
      },
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
              {
                session_id: 'session-1',
                preview: 'First page',
                created_at: dayjs().unix(),
                updated_at: dayjs().unix(),
              },
            ],
            meta: { page: 1, limit: 40, total_pages: 2, total_count: 41, search_time_ms: 0 },
          })
        }
        return HttpResponse.json({
          data: [
            {
              session_id: 'session-2',
              preview: 'Second page',
              created_at: dayjs().unix(),
              updated_at: dayjs().unix(),
            },
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

  it('keeps search input when server results are empty', async () => {
    const user = setupUser()
    mockSessions([
      {
        session_id: 'seed',
        preview: 'seed conversation',
        created_at: dayjs().unix(),
        updated_at: dayjs().unix(),
      },
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
