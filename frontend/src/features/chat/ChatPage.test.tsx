import { screen } from '@testing-library/react'
import { setupUser } from '@/test/user'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithQuery } from '@/test/render'
import { ChatPage } from './ChatPage'
import type { Message } from './types'

const longModelName = 'enterprise-security-analysis-model-with-an-intentionally-long-display-name'

class IntersectionObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

const chat = {
  state: { messages: [], input: '', requesting: false, error: null, selectedModelId: 'long', reasoningEffort: null, searchKnowledge: true, liveSearch: false, enableTools: true },
  sessionId: null as string | null,
  sessions: { data: [] },
  agents: { data: [] },
  selectedAgentId: null as string | null,
  activeSessionMeta: undefined as
    | {
        session_id: string
        preview: string
        title?: string | null
        created_at: number
        updated_at: number
        archived?: boolean
      }
    | undefined,
  sessionMetaLoading: false,
  sessionMetaFailed: false,
  sessionMetaError: null as Error | null,
  sessionMetaRefetch: vi.fn<() => void>(),
  sessionMissing: false,
  teamSessionChecking: false,
  teamSessionUnavailable: false,
  attachments: [] as File[],
  setAttachments: vi.fn<(attachments: File[]) => void>(),
  history: {
    data: [] as unknown[],
    isError: false,
    isLoading: false,
    isPending: false,
    isFetching: false,
    error: null as Error | null,
    refetch: vi.fn<() => void>(),
  },
  models: {
    isLoading: false,
    data: {
      active_model_id: 'long',
      models: [
        {
          id: 'short',
          name: 'GPT Mini',
          model_id: 'gpt-mini',
          provider: 'openai',
          api_protocol: 'responses',
          structured_output_mode: 'native',
          base_url: '',
          api_key: '',
          description: '',
          enabled: true,
          builtin: false,
          configured: true,
        },
        {
          id: 'long',
          name: longModelName,
          model_id: 'security-model',
          provider: 'openai',
          api_protocol: 'responses',
          structured_output_mode: 'native',
          base_url: '',
          api_key: '',
          description: '',
          enabled: true,
          builtin: false,
          configured: true,
        },
      ],
    },
  },
  selectedModel: {
    id: 'long',
    name: longModelName,
    model_id: 'security-model',
    provider: 'openai',
    api_protocol: 'responses',
    structured_output_mode: 'native',
    base_url: '',
    api_key: '',
    description: '',
    enabled: true,
    builtin: false,
    configured: true,
  },
  dispatch: vi.fn<(action: unknown) => void>(),
  setSession: vi.fn<(sessionId: string) => void>(),
  setModel: vi.fn<(modelId: string) => void>(),
  setEnableTools: vi.fn<(enabled: boolean) => void>(),
  setSearchKnowledge: vi.fn<(enabled: boolean) => void>(),
  setLiveSearch: vi.fn<(enabled: boolean) => void>(),
  setReasoningEffort: vi.fn<(effort: string) => void>(),
  submit: vi.fn<(value?: string) => void>(),
  retry: vi.fn<(messageId: string) => void>(),
  newChat: vi.fn<() => void>(),
  cancel: vi.fn<() => void>(),
}

vi.mock('@tanstack/react-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@tanstack/react-router')>()),
  useRouter: () => ({
    history: {
      push: vi.fn<(path: string) => void>(),
      replace: vi.fn<(path: string) => void>(),
    },
  }),
  useRouterState: ({ select }: { select: (state: { location: { searchStr: string; pathname: string } }) => unknown }) =>
    select({ location: { searchStr: '', pathname: '/chat' } }),
  // useBlocker needs a real RouterProvider; no-op in unit tests.
  useBlocker: () => undefined,
}))
vi.mock('./ChatTaskPanel', () => ({ ChatTaskPanel: () => null }))
vi.mock('./useChat', () => ({ useChat: () => chat }))
const { unarchiveSessionMock } = vi.hoisted(() => ({
  unarchiveSessionMock: vi.fn<() => Promise<{ success: boolean; archived: boolean }>>(
    async () => ({ success: true, archived: false }),
  ),
}))
vi.mock('./api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api')>()),
  unarchiveSession: unarchiveSessionMock,
}))

beforeEach(() => {
  HTMLElement.prototype.scrollTo = vi.fn<(...args: unknown[]) => void>()
  vi.stubGlobal('IntersectionObserver', IntersectionObserverMock)
  chat.teamSessionChecking = false
  chat.teamSessionUnavailable = false
})

describe('chat model settings', () => {
  beforeEach(() => {
    ;(chat.state as { reasoningEffort: string | null }).reasoningEffort = null
    ;(chat.state as { requesting: boolean }).requesting = false
    chat.dispatch.mockClear()
    chat.setModel.mockClear()
    chat.setReasoningEffort.mockClear()
    chat.cancel.mockClear()
    chat.setReasoningEffort.mockImplementation((effort) => {
      ;(chat.state as { reasoningEffort: string | null }).reasoningEffort = effort
    })
  })

  it('keeps the full selected model name available in the model settings menu', async () => {
    const user = setupUser()
    renderWithQuery(<ChatPage />)

    expect(document.querySelector('.model-select-value')?.getAttribute('title')).toBe(longModelName)
    await user.click(screen.getByRole('button', { name: '模型与推理强度' }))
    expect(await screen.findByText('模型')).toBeTruthy()
  })

  it('keeps the model menu open after selecting a model', async () => {
    const user = setupUser()
    renderWithQuery(<ChatPage />)

    await user.click(screen.getByRole('button', { name: '模型与推理强度' }))
    await user.click(await screen.findByText('GPT Mini'))
    expect(chat.setModel).toHaveBeenCalledWith('short')
    expect(screen.getByText('模型')).toBeTruthy()
  })

  it('changes reasoning effort from the cascader menu', async () => {
    const user = setupUser()
    renderWithQuery(<ChatPage />)

    await user.click(screen.getByRole('button', { name: '模型与推理强度' }))
    await user.click(await screen.findByText('推理强度'))
    await user.click(await screen.findByText('High'))
    expect(chat.setReasoningEffort).toHaveBeenCalledWith('high')
  })

  it('offers focused security investigation starters that populate the composer', async () => {
    const user = setupUser()
    renderWithQuery(<ChatPage />)

    await user.click(screen.getByRole('button', { name: /分析最新 CVE 对现有资产的影响/ }))
    expect(chat.dispatch).toHaveBeenCalledWith({ type: 'input', value: '分析最新 CVE 对现有资产的影响' })
    expect(screen.getByText('从哪里开始调查？')).toBeTruthy()
  })
})

describe('chat stop shortcuts', () => {
  beforeEach(() => {
    ;(chat.state as { requesting: boolean }).requesting = false
    chat.cancel.mockClear()
  })

  it('stops generation when Escape is pressed during a request', () => {
    ;(chat.state as { requesting: boolean }).requesting = true
    renderWithQuery(<ChatPage />)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(chat.cancel).toHaveBeenCalledTimes(1)
  })

  it('does not stop when Escape is pressed while idle', () => {
    ;(chat.state as { requesting: boolean }).requesting = false
    renderWithQuery(<ChatPage />)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(chat.cancel).not.toHaveBeenCalled()
  })
  it('does not stop when Escape is pressed while a modal is open', () => {
    ;(chat.state as { requesting: boolean }).requesting = true
    const wrap = document.createElement('div')
    wrap.className = 'ant-modal-wrap'
    document.body.appendChild(wrap)
    try {
      renderWithQuery(<ChatPage />)
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
      expect(chat.cancel).not.toHaveBeenCalled()
    } finally {
      wrap.remove()
    }
  })
})

describe('chat history load failure', () => {
  beforeEach(() => {
    chat.sessionId = 'session-err'
    chat.history.isError = true
    chat.history.isFetching = false
    chat.history.error = new Error('history boom')
    chat.history.refetch = vi.fn<() => void>()
    chat.state.messages = []
    chat.state.requesting = false
  })

  it('shows history error with retry when load fails', async () => {
    const user = setupUser()
    renderWithQuery(<ChatPage />)
    const alert = screen.getByRole('alert')
    expect(alert.textContent || '').toMatch(/无法加载会话历史/)
    expect(alert.textContent || '').toContain('history boom')
    const retry = alert.querySelector('button')
    expect(retry).toBeTruthy()
    await user.click(retry as HTMLButtonElement)
    expect(chat.history.refetch).toHaveBeenCalled()
  })
})

describe('chat history loading state', () => {
  beforeEach(() => {
    chat.sessionId = 'session-loading'
    chat.history.isError = false
    chat.history.isLoading = true
    chat.history.isPending = true
    chat.history.isFetching = true
    chat.history.error = null
    chat.state.messages = []
    chat.state.requesting = false
  })

  it('shows loading instead of welcome while history fetches', () => {
    renderWithQuery(<ChatPage />)
    expect(screen.getByRole('status').textContent || '').toMatch(/loading|加载/i)
    expect(screen.queryByText('从哪里开始调查？')).toBeNull()
  })
})


describe('chat missing session', () => {
  beforeEach(() => {
    chat.sessionId = 'gone'
    chat.sessionMissing = true
    chat.sessionMetaLoading = false
    chat.history.isError = false
    chat.history.isLoading = false
    chat.history.isPending = false
    chat.history.isFetching = false
    chat.state.messages = []
    chat.state.requesting = false
    chat.newChat.mockClear()
  })

  it('shows not-found instead of welcome when session meta is missing', async () => {
    const user = setupUser()
    renderWithQuery(<ChatPage />)
    expect(screen.queryByText('从哪里开始调查？')).toBeNull()
    const status = screen.getByRole('region', { name: /not found|不存在|无权/i })
    expect(status.textContent || '').toMatch(/not found|不存在|无权/i)
    await user.click(screen.getByRole('button', { name: '新建分析' }))
    expect(chat.newChat).toHaveBeenCalled()
  })
})


describe('chat archived session header', () => {
  beforeEach(() => {
    chat.sessionId = 'arch-1'
    chat.sessionMissing = false
    chat.sessionMetaLoading = false
    chat.activeSessionMeta = {
      session_id: 'arch-1',
      preview: 'old',
      title: 'Archived case',
      created_at: 1,
      updated_at: 2,
      archived: true,
    }
    chat.history.isError = false
    chat.history.isLoading = false
    chat.history.isPending = false
    chat.history.isFetching = false
    chat.state.messages = []
    chat.state.requesting = false
  })

  it('shows archived badge and unarchive action in context bar', async () => {
    const user = setupUser()
    unarchiveSessionMock.mockClear()
    renderWithQuery(<ChatPage />)
    expect(screen.getAllByText('Archived case').length).toBeGreaterThan(0)
    expect(screen.getByText('已归档')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '取消归档' }))
    expect(unarchiveSessionMock).toHaveBeenCalled()
  })
})


describe('chat session meta load failure', () => {
  beforeEach(() => {
    chat.sessionId = 'session-meta-err'
    chat.sessionMissing = false
    chat.sessionMetaLoading = false
    chat.sessionMetaFailed = true
    chat.sessionMetaError = new Error('meta boom')
    chat.sessionMetaRefetch = vi.fn<() => void>()
    chat.history.isError = false
    chat.history.isLoading = false
    chat.history.isPending = false
    chat.history.isFetching = false
    chat.state.messages = []
    chat.state.requesting = false
  })

  it('shows meta error with retry instead of welcome', async () => {
    const user = setupUser()
    renderWithQuery(<ChatPage />)
    expect(screen.queryByText('从哪里开始调查？')).toBeNull()
    const alert = screen.getByRole('alert')
    expect(alert.textContent || '').toMatch(/无法加载会话信息/)
    expect(alert.textContent || '').toMatch(/meta boom/)
    await user.click(alert.querySelector('button') as HTMLButtonElement)
    expect(chat.sessionMetaRefetch).toHaveBeenCalled()
  })
})


describe('chat session meta loading', () => {
  beforeEach(() => {
    chat.sessionId = 'session-meta-loading'
    chat.sessionMissing = false
    chat.sessionMetaLoading = true
    chat.sessionMetaFailed = false
    chat.sessionMetaError = null
    chat.history.isError = false
    chat.history.isLoading = false
    chat.history.isPending = false
    chat.history.isFetching = false
    chat.state.messages = []
    chat.state.requesting = false
    chat.state.input = 'hello'
  })

  it('disables send while session meta is resolving', () => {
    renderWithQuery(<ChatPage />)
    expect(screen.getByText('加载会话信息…')).toBeTruthy()
    expect(screen.queryByText('从哪里开始调查？')).toBeNull()
    const send = document.querySelector('.sender-actions button.ant-btn-primary') as HTMLButtonElement | null
    expect(send).toBeTruthy()
    expect(send?.disabled).toBe(true)
  })
})

describe('Team task presentation', () => {
  beforeEach(() => {
    chat.sessionId = null
    chat.activeSessionMeta = undefined
    chat.sessionMissing = false
    chat.sessionMetaLoading = false
    chat.sessionMetaFailed = false
    chat.sessionMetaError = null
    chat.history.isError = false
    chat.history.isLoading = false
    chat.history.isPending = false
    chat.history.isFetching = false
    chat.history.error = null
    chat.state.input = ''
    chat.state.requesting = false
    chat.teamSessionChecking = false
    chat.teamSessionUnavailable = false
  })

  it('renders Team task progress, assignee, dependencies, and completion state', () => {
    const message: Message = {
      id: 'team-run',
      role: 'assistant',
      content: '',
      final: false,
      status: 'streaming',
      team_tasks: {
        taskSummary: '并行收集并分析证据',
        goalComplete: true,
        completionSummary: '已准备综合结论',
        tasks: [
          {
            id: 'research',
            title: '收集漏洞情报',
            status: 'completed',
            assignee: '深度研究',
            result: '已核实三个来源',
          },
          {
            id: 'analysis',
            title: '分析资产影响',
            status: 'in_progress',
            dependencies: ['research'],
          },
        ],
      },
    }
    ;(chat.state as { messages: Message[] }).messages = [message]

    renderWithQuery(<ChatPage />)

    const panel = screen.getByRole('region', { name: '团队任务' })
    expect(panel.textContent).toContain('1 / 2 已完成')
    expect(panel.textContent).toContain('负责人：深度研究')
    expect(panel.textContent).toContain('依赖：research')
    expect(panel.textContent).toContain('团队目标已完成')
  })

  it('keeps an initial Team task summary visible before individual tasks arrive', () => {
    const message: Message = {
      id: 'team-summary',
      role: 'assistant',
      content: '',
      final: false,
      status: 'streaming',
      team_tasks: { tasks: [], taskSummary: '正在为专员拆分任务' },
    }
    ;(chat.state as { messages: Message[] }).messages = [message]

    renderWithQuery(<ChatPage />)

    const panel = screen.getByRole('region', { name: '团队任务' })
    expect(panel.textContent).toContain('正在为专员拆分任务')
    expect(panel.textContent).not.toContain('0 / 0 已完成')
  })

  it('keeps an empty final task snapshot visible with its completion summary', () => {
    const message: Message = {
      id: 'team-completion-summary',
      role: 'assistant',
      content: '',
      final: true,
      status: 'completed',
      team_tasks: {
        tasks: [],
        goalComplete: true,
        completionSummary: '无需再创建子任务',
      },
    }
    ;(chat.state as { messages: Message[] }).messages = [message]

    renderWithQuery(<ChatPage />)

    const panel = screen.getByRole('region', { name: '团队任务' })
    expect(panel.textContent).toContain('团队目标已完成')
    expect(panel.textContent).toContain('无需再创建子任务')
  })
})

describe('unavailable Team session', () => {
  beforeEach(() => {
    chat.sessionId = 'team-disabled-session'
    chat.activeSessionMeta = undefined
    chat.sessionMissing = false
    chat.sessionMetaLoading = false
    chat.sessionMetaFailed = false
    chat.sessionMetaError = null
    chat.history.isError = false
    chat.history.isLoading = false
    chat.history.isPending = false
    chat.history.isFetching = false
    chat.history.error = null
    chat.state.input = '继续该团队会话'
    chat.state.requesting = false
    ;(chat.state as { messages: Message[] }).messages = []
    chat.teamSessionChecking = false
    chat.teamSessionUnavailable = true
    chat.newChat.mockClear()
  })

  it('shows a fail-closed warning, disables sending, and offers a fresh analysis', async () => {
    const user = setupUser()
    renderWithQuery(<ChatPage />)

    const alert = screen.getByRole('alert')
    expect(alert.textContent).toContain('此 Team 当前不可用')
    expect((screen.getByRole('button', { name: '发送消息' }) as HTMLButtonElement).disabled).toBe(true)

    await user.click(screen.getByRole('button', { name: '新建普通分析' }))
    expect(chat.newChat).toHaveBeenCalledTimes(1)
  })
})
