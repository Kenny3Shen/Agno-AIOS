import { useMemo } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useRouter } from '@tanstack/react-router'
import { Actions, Bubble, Conversations, Prompts, Sender, Sources, Think, ThoughtChain, Welcome } from '@ant-design/x'
import XMarkdown from '@ant-design/x-markdown'
import { Avatar, Select, Tag, message as toast } from 'antd'
import { CopyOutlined, DeleteOutlined, ExperimentOutlined, PlusOutlined, ReloadOutlined, UserOutlined } from '@ant-design/icons'
import { archiveSession } from './api'
import { chatKeys } from './queries'
import { parseMessage } from './utils'
import { useChat } from './useChat'
import type { Message } from './types'
import { copyToClipboard } from '@/shared/lib/clipboard'
import { compactId } from '@/shared/lib/format'
import './chat.css'

const prompts = [
  { key: 'cve', label: '分析最新 CVE 对现有资产的影响' },
  { key: 'exposure', label: '生成外部暴露面排查计划' },
  { key: 'runbook', label: '为当前告警编写处置 Runbook' },
]

function MessageBody({ message, retry, openTrace }: { message: Message; retry: () => void; openTrace: () => void }) {
  const parsed = parseMessage(message.content)
  const actions = [
    { key: 'copy', label: '复制', icon: <CopyOutlined />, onItemClick: () => void copyToClipboard(message.content) },
    ...(message.role === 'assistant' ? [
      { key: 'retry', label: '重试', icon: <ReloadOutlined />, onItemClick: retry },
      ...(message.session_id ? [{ key: 'trace', label: '查看 Trace', icon: <ExperimentOutlined />, onItemClick: openTrace }] : []),
    ] : []),
  ]
  return (
    <div className="message-body">
      {message.role === 'assistant' ? <XMarkdown content={parsed.body} streaming={{ hasNextChunk: !message.final, tail: !message.final }} openLinksInNewTab escapeRawHtml /> : <p>{message.content}</p>}
      {parsed.thinking && <Think title="模型推理输出" loading={!message.final} defaultExpanded={false}><XMarkdown content={parsed.thinking} escapeRawHtml /></Think>}
      {parsed.sources.length > 0 && <Sources title="来源" items={parsed.sources.map((source, index) => ({ key: index, title: source }))} />}
      {parsed.tools.length > 0 && <ThoughtChain items={parsed.tools.map((tool, index) => ({ key: String(index), title: tool }))} />}
      {message.role === 'assistant' && message.final && <div className="run-strip"><span>{message.metrics?.duration != null ? `${message.metrics.duration}s` : 'completed'}</span><span>{message.metrics?.total_tokens != null ? `${message.metrics.total_tokens} tokens` : compactId(message.run_id)}</span></div>}
      {message.final && <Actions items={actions} />}
    </div>
  )
}

export function ChatPage() {
  const chat = useChat()
  const queryClient = useQueryClient()
  const router = useRouter()
  const conversations = useMemo(() => (chat.sessions.data ?? []).map((session) => ({ key: session.session_id, label: session.preview || compactId(session.session_id) })), [chat.sessions.data])
  const bubbles = chat.state.messages.filter((item) => item.content || item.role === 'assistant').map((item) => ({
    key: item.id,
    role: item.role === 'user' ? 'user' : 'ai',
    content: item,
    placement: item.role === 'user' ? 'end' as const : 'start' as const,
    variant: item.role === 'user' ? 'filled' as const : 'outlined' as const,
    streaming: !item.final,
    avatar: item.role === 'user' ? <Avatar icon={<UserOutlined />} /> : <Avatar shape="square" className="agent-avatar">T</Avatar>,
    contentRender: (value: Message) => <MessageBody message={value} retry={() => chat.retry(value.id)} openTrace={() => void router.history.push(`/trace?session=${encodeURIComponent(value.session_id ?? '')}&run=${encodeURIComponent(value.run_id ?? '')}`)} />,
  }))

  const archive = async (sessionId: string) => {
    await archiveSession(sessionId)
    if (chat.sessionId === sessionId) chat.newChat()
    await queryClient.invalidateQueries({ queryKey: chatKeys.sessionLists })
    toast.success('会话已归档')
  }

  return (
    <main className="chat-page">
      <aside className="conversation-panel">
        <div className="conversation-title"><strong>安全会话</strong><Tag>{conversations.length}</Tag></div>
        <Conversations
          items={conversations}
          activeKey={chat.sessionId ?? undefined}
          onActiveChange={(key) => chat.setSession(key)}
          creation={{ icon: <PlusOutlined />, label: '新建会话', onClick: chat.newChat }}
          menu={(item) => ({ items: [
            { key: 'copy', icon: <CopyOutlined />, label: '复制 ID', onClick: () => void copyToClipboard(item.key) },
            { key: 'archive', danger: true, icon: <DeleteOutlined />, label: '归档', onClick: () => void archive(item.key) },
          ] })}
        />
      </aside>
      <section className="chat-workspace">
        <div className="bubble-scroll">
          {!bubbles.length ? <div className="chat-welcome"><Welcome variant="borderless" icon={<Avatar shape="square" className="agent-avatar">T</Avatar>} title="T.A.I.S 安全分析 Agent" description="从漏洞、资产、知识和运行上下文开始一项分析。" /><Prompts items={prompts} wrap onItemClick={({ data }) => chat.dispatch({ type: 'input', value: String(data.label ?? '') })} /></div> : <Bubble.List items={bubbles} autoScroll />}
          {chat.state.error && <div className="chat-error" role="alert">{chat.state.error}</div>}
        </div>
        <div className="sender-shell">
          <Sender
            value={chat.state.input}
            onChange={(value) => chat.dispatch({ type: 'input', value })}
            onSubmit={(value) => void chat.submit(value)}
            onCancel={chat.cancel}
            loading={chat.state.requesting}
            disabled={!chat.selectedModel?.enabled || !chat.selectedModel.configured}
            placeholder={chat.selectedModel?.configured ? '输入安全分析任务' : '请先在设置中配置可用模型'}
            autoSize={{ minRows: 1, maxRows: 6 }}
            prefix={<Select className="model-select" value={chat.state.selectedModelId} loading={chat.models.isLoading} onChange={chat.setModel} options={(chat.models.data?.models ?? []).map((model) => ({ value: model.id, label: model.name, disabled: !model.enabled }))} />}
          />
        </div>
      </section>
    </main>
  )
}
