import dayjs from 'dayjs'
import { screen } from '@testing-library/react'
import { setupUser } from '@/test/user'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '@/shared/i18n'
import { renderWithQuery } from '@/test/render'
import { buildConversationItems, filterConversationItems, ChatTaskPanel } from './ChatTaskPanel'
import type { ChatSession } from './types'

const sessions = {
  data: [] as ChatSession[],
  isLoading: false,
  isError: false,
  isFetching: false,
  hasNextPage: false,
  isFetchingNextPage: false,
  fetchNextPage: vi.fn<() => Promise<unknown>>(),
  refetch: vi.fn<() => Promise<unknown>>(),
}

const chat = {
  sessionId: null as string | null,
  sessions,
  sessionSearch: '',
  debouncedSessionSearch: '',
  setSessionSearch: vi.fn<(value: string) => void>(),
  showArchived: false,
  setShowArchived: vi.fn<(value: boolean) => void>(),
  setSession: vi.fn<(sessionId: string) => void>(),
  newChat: vi.fn<() => void>(),
  state: { requesting: false },
}

vi.mock('./useChat', () => ({ useChat: () => chat }))
vi.mock('@tanstack/react-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@tanstack/react-router')>()),
  useRouter: () => ({ history: { push: vi.fn(), replace: vi.fn() } }),
}))

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
      now
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
    sessions.data = []
    sessions.isLoading = false
    sessions.isError = false
    sessions.isFetching = false
    sessions.hasNextPage = false
    sessions.isFetchingNextPage = false
    sessions.fetchNextPage.mockReset()
    sessions.refetch.mockReset()
    chat.sessionId = null
    chat.sessionSearch = ''
    chat.debouncedSessionSearch = ''
    chat.setSession.mockReset()
    chat.setSessionSearch.mockReset()
    chat.newChat.mockReset()
  })

  it('exposes a controlled expand toggle without rendering hidden content', async () => {
    const user = setupUser()
    const onExpandedChange = vi.fn<(expanded: boolean) => void>()
    renderWithQuery(<ChatTaskPanel expanded={false} onExpandedChange={onExpandedChange} variant="sider" />)

    const toggle = screen.getByRole('button', { name: '最近对话' })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByText('新建对话')).toBeNull()
    await user.click(toggle)
    expect(onExpandedChange).toHaveBeenCalledWith(true)
  })

  it('opens conversations while notifying a mobile drawer to close', async () => {
    const user = setupUser()
    const onNavigate = vi.fn<() => void>()
    sessions.data = [
      {
        session_id: 'session-1',
        title: '资产风险分析',
        preview: '分析资产风险',
        created_at: dayjs().unix(),
        updated_at: dayjs().unix(),
      },
    ]
    renderWithQuery(
      <ChatTaskPanel expanded onExpandedChange={vi.fn<(expanded: boolean) => void>()} onNavigate={onNavigate} variant="drawer" />
    )

    expect(screen.queryByText('新建对话')).toBeNull()
    await user.click(screen.getByText('资产风险分析'))
    expect(chat.setSession).toHaveBeenCalledWith('session-1')
    expect(onNavigate).toHaveBeenCalledOnce()
  })

  it('renders an empty state and retries a failed sessions query', async () => {
    const user = setupUser()
    const { unmount } = renderWithQuery(<ChatTaskPanel expanded onExpandedChange={vi.fn<(expanded: boolean) => void>()} variant="sider" />)
    expect(screen.getByText('暂无对话')).toBeTruthy()

    unmount()
    sessions.isError = true
    renderWithQuery(<ChatTaskPanel expanded onExpandedChange={vi.fn<(expanded: boolean) => void>()} variant="sider" />)
    await user.click(screen.getByRole('button', { name: '重试' }))
    expect(sessions.refetch).toHaveBeenCalledOnce()
  })

  it('localizes the panel and date group labels', async () => {
    await i18n.changeLanguage('en-US')
    sessions.data = [
      {
        session_id: 'session-1',
        preview: 'Investigate CVE',
        created_at: dayjs().unix(),
        updated_at: dayjs().unix(),
      },
    ]
    renderWithQuery(<ChatTaskPanel expanded onExpandedChange={vi.fn<(expanded: boolean) => void>()} variant="sider" />)
    expect(screen.getByText('Recent conversations')).toBeTruthy()
    expect(screen.getByText('Today')).toBeTruthy()
  })
  it('loads more sessions when hasNextPage is true', async () => {
    const user = setupUser()
    sessions.data = [
      {
        session_id: 'session-1',
        preview: 'First page',
        created_at: dayjs().unix(),
        updated_at: dayjs().unix(),
      },
    ]
    sessions.hasNextPage = true
    renderWithQuery(<ChatTaskPanel expanded onExpandedChange={vi.fn<(expanded: boolean) => void>()} variant="sider" />)
    await user.click(screen.getByRole('button', { name: '加载更多' }))
    expect(sessions.fetchNextPage).toHaveBeenCalledOnce()
  })

  it('keeps search input when server results are empty', async () => {
    sessions.data = []
    chat.sessionSearch = 'no-match-xyz'
    chat.debouncedSessionSearch = 'no-match-xyz'
    renderWithQuery(<ChatTaskPanel expanded onExpandedChange={vi.fn<(expanded: boolean) => void>()} variant="sider" />)
    expect(screen.getByLabelText(i18n.t('shell:conversations.searchPlaceholder'))).toBeTruthy()
    expect(screen.getByText(i18n.t('shell:conversations.emptySearch'))).toBeTruthy()
  })

})
