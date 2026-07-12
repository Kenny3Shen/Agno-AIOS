import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Actions, Bubble, Conversations, Prompts, Sender, Sources, ThoughtChain, Welcome } from '@ant-design/x'
import XMarkdown from '@ant-design/x-markdown'
import { Avatar, Button, Form, Input, Modal, Select, Tag, Tooltip, message as toast } from 'antd'
import { ArrowDownOutlined, ArrowUpOutlined, CaretDownOutlined, CaretRightOutlined, CopyOutlined, DeleteOutlined, EditOutlined, PaperClipOutlined, PlusOutlined, ReloadOutlined, SafetyCertificateOutlined, StopOutlined, UserOutlined } from '@ant-design/icons'
import { archiveSession, renameSession } from './api'
import { chatKeys } from './queries'
import { useChat } from './useChat'
import type { ChatSession, Message, ThoughtStep, ToolStep } from './types'
import type { ModelConfig } from '@/shared/types/common'
import { copyToClipboard } from '@/shared/lib/clipboard'
import { reasoningEffortLabel } from '@/shared/lib/reasoning'
import { supportedReasoningEfforts } from './utils'
import './chat.css'

const prompts = [
  { key: 'cve', label: '分析最新 CVE 对现有资产的影响', description: '关联漏洞情报和资产上下文' },
  { key: 'exposure', label: '生成外部暴露面排查计划', description: '建立优先级明确的调查步骤' },
  { key: 'runbook', label: '为当前告警编写处置 Runbook', description: '输出可执行的响应流程' },
]

const statusText: Record<NonNullable<Message['status']>, string> = { streaming: '分析中', completed: '已完成', cancelled: '已停止', failed: '运行失败' }

const reasoningOptions = (model: ModelConfig | null) => {
  return supportedReasoningEfforts(model).map((value) => ({ value, label: reasoningEffortLabel(value) }))
}

function renderModelLabel({ label, value }: { label?: unknown; value?: string | number }) {
  const name = typeof label === 'string' ? label : String(value ?? '')
  return <Tooltip title={name}><span className="model-select-value" title={name}>{name}</span></Tooltip>
}

const renderRaw = (value: unknown) => typeof value === 'string' ? value : JSON.stringify(value, null, 2)
function RawDetails({ label, value }: { label: string; value: unknown }) {
  if (value === undefined || value === null || value === '') return null
  const content = renderRaw(value)
  return <details className="raw-details"><summary>{label}</summary><div><Button type="link" size="small" icon={<CopyOutlined />} onClick={() => void copyToClipboard(content)}>复制</Button><pre>{content}</pre></div></details>
}
function toolNode(tool: ToolStep) {
  return {
    key: `tool-${tool.id}`, title: tool.name, status: tool.status, blink: tool.status === 'loading', collapsible: true,
    description: tool.summary ?? undefined,
    footer: <>{tool.duration != null && <span>{tool.duration.toFixed(1)}s</span>}<RawDetails label="原始工具输入" value={tool.input} /><RawDetails label="原始工具输出" value={tool.output} /></>,
  }
}
function thoughtNode(thought: ThoughtStep) {
  return { key: `thought-${thought.id}`, title: thought.title, status: thought.status, blink: thought.status === 'loading', collapsible: true, description: thought.summary ?? undefined, footer: thought.duration != null ? `${thought.duration.toFixed(1)}s` : undefined }
}

function MessageBody({ message, retry }: { message: Message; retry: () => void }) {
  const [thoughtOpen, setThoughtOpen] = useState(message.status === 'streaming')
  const motionState = message.role === 'assistant' ? message.status ?? 'completed' : 'sent'
  const actions = [
    { key: 'copy', label: '复制', icon: <CopyOutlined />, onItemClick: () => void copyToClipboard(message.content) },
    ...(message.role === 'assistant' ? [{ key: 'retry', label: '重新生成', icon: <ReloadOutlined />, onItemClick: retry }, ...(message.run_id ? [{ key: 'copy-run-id', label: '复制 Run ID', icon: <CopyOutlined />, onItemClick: () => { void copyToClipboard(message.run_id ?? '').then((copied) => copied ? toast.success('Run ID 已复制') : toast.error('Run ID 复制失败')) } }] : [])] : []),
  ]
  if (message.role !== 'assistant') return <div className={`message-body message-body--${motionState}`}><p>{message.content}</p><Actions items={actions} /></div>
  const chain = [...(message.thought_chain ?? []).map(thoughtNode), ...(message.tool_steps ?? []).map(toolNode)]
  const hasThoughts = chain.length > 0 || Boolean(message.reasoning)
  return <div className={`message-body message-body--${motionState}`}>
    {hasThoughts && <section className="thought-section">
      <Button className="thought-toggle" type="text" size="small" icon={thoughtOpen ? <CaretDownOutlined /> : <CaretRightOutlined />} onClick={() => setThoughtOpen((open) => !open)} aria-expanded={thoughtOpen}>
        思考与执行过程
      </Button>
      {thoughtOpen && <div className="thought-content">
        <RawDetails label="原始 reasoning" value={message.reasoning} />
        {chain.length > 0 && <ThoughtChain className="tool-chain" items={chain} defaultExpandedKeys={chain.filter((item) => item.status === 'loading').map((item) => item.key)} />}
      </div>}
    </section>}
    {message.content ? <XMarkdown content={message.content} streaming={{ hasNextChunk: !message.final, tail: !message.final }} openLinksInNewTab escapeRawHtml /> : <div className="response-pending">正在建立分析运行…</div>}
    {(message.sources?.length ?? 0) > 0 && <Sources title="参考来源" items={message.sources?.map((source) => ({ key: source.id, title: source.title, url: source.url ?? undefined, description: source.snippet ?? undefined })) ?? []} />}
    <div className={`run-strip run-${message.status ?? 'completed'}`}><span className="run-status">{statusText[message.status ?? 'completed']}</span>{message.metrics?.duration != null && <span className="run-metric" title="运行耗时">{message.metrics.duration.toFixed(1)}s</span>}{message.metrics?.total_tokens != null && <span className="run-metric" title={`${message.metrics.total_tokens.toLocaleString()} tokens`}>{Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(message.metrics.total_tokens)} tokens</span>}</div>
    {message.error && <div className="message-run-error" role="alert">{message.error.code ? `${message.error.code}: ` : ''}{message.error.message}</div>}
    {message.final && <Actions items={actions} />}
  </div>
}

export function ChatPage() {
  const chat = useChat()
  const queryClient = useQueryClient()
  const [renameTarget, setRenameTarget] = useState<ChatSession | null>(null)
  const [renameForm] = Form.useForm<{ title: string }>()
  const [renaming, setRenaming] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const [followLatest, setFollowLatest] = useState(true)
  const conversations = useMemo(() => (chat.sessions.data ?? []).map((session) => ({ key: session.session_id, label: session.title || session.preview || '未命名会话', group: new Date(session.updated_at * 1000).toDateString() })), [chat.sessions.data])
  const activeSession = useMemo(() => (chat.sessions.data ?? []).find((session) => session.session_id === chat.sessionId), [chat.sessionId, chat.sessions.data])
  const bubbles = chat.state.messages.filter((item) => item.content || item.role === 'assistant').map((item) => ({
    key: item.id, role: item.role === 'user' ? 'user' : 'ai', content: item, placement: item.role === 'user' ? 'end' as const : 'start' as const,
    variant: item.role === 'user' ? 'filled' as const : 'outlined' as const, streaming: item.status === 'streaming',
    avatar: item.role === 'user' ? <Avatar icon={<UserOutlined />} /> : <Avatar shape="square" className="agent-avatar">T</Avatar>,
    contentRender: (value: Message) => <MessageBody message={value} retry={() => chat.retry(value.id)} />,
  }))
  const activeRun = [...chat.state.messages].reverse().find((item) => item.role === 'assistant' && item.status === 'streaming')
  const availableReasoningOptions = reasoningOptions(chat.selectedModel)
  const inputDisabled = !chat.selectedModel?.enabled || !chat.selectedModel.configured
  const sendDisabled = inputDisabled || !chat.state.input.trim()
  const scrollToLatest = useCallback(() => { const node = scrollRef.current; if (node) node.scrollTo({ top: node.scrollHeight, behavior: 'smooth' }); setFollowLatest(true) }, [])
  useEffect(() => { if (followLatest) requestAnimationFrame(scrollToLatest) }, [chat.sessionId, chat.state.messages, followLatest, scrollToLatest])
  useEffect(() => { setFollowLatest(true) }, [chat.sessionId])

  const archive = async (sessionId: string) => { await archiveSession(sessionId); if (chat.sessionId === sessionId) chat.newChat(); await queryClient.invalidateQueries({ queryKey: chatKeys.sessionLists }); toast.success('会话已归档') }
  const copySessionId = (sessionId: string) => { void copyToClipboard(sessionId).then((copied) => copied ? toast.success('Session ID 已复制') : toast.error('Session ID 复制失败')) }
  const startRename = (session: ChatSession) => { renameForm.setFieldsValue({ title: session.title || session.preview || '' }); setRenameTarget(session) }
  const confirmRename = async () => {
    const { title } = await renameForm.validateFields(); if (!renameTarget) return
    setRenaming(true)
    try {
      const updated = await renameSession(renameTarget.session_id, title.trim())
      queryClient.setQueryData<ChatSession[]>(chatKeys.sessions(), (items) => (items ?? []).map((item) => item.session_id === renameTarget.session_id ? { ...item, ...updated, title: updated.title ?? title.trim() } : item))
      toast.success('会话已重命名'); setRenameTarget(null)
    } catch (error) { toast.error(error instanceof Error ? error.message : '重命名失败') } finally { setRenaming(false) }
  }

  return <main className="chat-page">
    <aside className="conversation-panel"><div className="conversation-title"><div><strong>安全会话</strong><span>调查工作区</span></div><Tag>{conversations.length}</Tag></div><Conversations items={conversations} activeKey={chat.sessionId ?? undefined} onActiveChange={(key) => chat.setSession(key)} creation={{ icon: <PlusOutlined />, label: '新建分析', onClick: chat.newChat }} menu={(item) => ({ items: [{ key: 'rename', icon: <EditOutlined />, label: '重命名', onClick: () => { const session = (chat.sessions.data ?? []).find((value) => value.session_id === item.key); if (session) startRename(session) } }, { key: 'copy-session-id', icon: <CopyOutlined />, label: '复制 Session ID', onClick: () => copySessionId(item.key) }, { key: 'archive', danger: true, icon: <DeleteOutlined />, label: '归档', onClick: () => void archive(item.key) }] })} /></aside>
    <section className="chat-workspace">
      <header className="chat-context-bar"><div><SafetyCertificateOutlined /><span>{activeSession?.title || '安全分析'}</span><span className="context-divider" /><span>{chat.selectedModel?.name ?? '未选择模型'}</span></div><div className="context-status"><span className={activeRun ? 'status-dot active' : 'status-dot'} />{activeRun ? 'Agent 正在运行' : chat.sessionId ? '会话已就绪' : '新建分析'}</div></header>
      <div className="bubble-scroll" ref={scrollRef} onScroll={(event) => { const node = event.currentTarget; setFollowLatest(node.scrollHeight - node.scrollTop - node.clientHeight < 48) }}>
        {!bubbles.length ? <div className="chat-welcome"><Welcome variant="borderless" icon={<Avatar shape="square" className="agent-avatar">T</Avatar>} title="T.A.I.S 安全分析 Agent" description="基于漏洞、资产、知识和运行上下文发起一项可追溯的安全分析。" /><Prompts items={prompts} wrap onItemClick={({ data }) => chat.dispatch({ type: 'input', value: String(data.label ?? '') })} /></div> : <Bubble.List items={bubbles} autoScroll={false} />}
        {chat.state.messages.at(-1)?.followups?.length ? <Prompts className="followup-prompts" title="继续分析" items={chat.state.messages.at(-1)?.followups?.map((label, index) => ({ key: String(index), label })) ?? []} onItemClick={({ data }) => void chat.submit(String(data.label ?? ''))} /> : null}
        {chat.state.error && <div className="chat-error" role="alert">{chat.state.error}<Button type="link" size="small" onClick={() => chat.retry(chat.state.messages.at(-1)?.id ?? '')}>重试</Button></div>}
      </div>
      {!followLatest && <Button className="latest-button" shape="round" icon={<ArrowDownOutlined />} onClick={scrollToLatest}>返回最新消息</Button>}
      <div className="sender-shell"><Sender value={chat.state.input} onChange={(value) => chat.dispatch({ type: 'input', value })} onSubmit={(value) => void chat.submit(value)} loading={chat.state.requesting} disabled={inputDisabled} suffix={false} placeholder={chat.selectedModel?.configured ? '输入安全分析任务，例如：分析 CVE-2026-xxxx 对资产的影响…' : '请先在设置中配置可用模型'} autoSize={{ minRows: 1, maxRows: 5 }} footer={<div className="sender-controls"><Button className="sender-extension" type="text" icon={<PaperClipOutlined />} disabled aria-label="附件功能即将推出" /><div className="sender-actions"><Select aria-label="模型" className="model-select" value={chat.state.selectedModelId ?? undefined} loading={chat.models.isLoading} disabled={chat.state.requesting} onChange={chat.setModel} labelRender={renderModelLabel} options={(chat.models.data?.models ?? []).map((model) => ({ value: model.id, label: model.name, disabled: !model.enabled || !model.configured }))} />{availableReasoningOptions.length > 0 && <Select aria-label="推理强度" className="reasoning-select" value={chat.state.reasoningEffort ?? undefined} disabled={chat.state.requesting} onChange={chat.setReasoningEffort} options={availableReasoningOptions} />}<Button aria-label={chat.state.requesting ? '停止生成' : '发送消息'} title={chat.state.requesting ? '停止生成' : '发送消息'} type={chat.state.requesting ? 'default' : 'primary'} danger={chat.state.requesting} shape="circle" icon={chat.state.requesting ? <StopOutlined /> : <ArrowUpOutlined />} disabled={chat.state.requesting ? !activeRun : sendDisabled} onClick={() => { if (chat.state.requesting) void chat.cancel(); else void chat.submit(chat.state.input) }} /></div></div>} /></div>
    </section>
    <Modal title="重命名会话" open={Boolean(renameTarget)} confirmLoading={renaming} okText="保存" onOk={() => void confirmRename()} onCancel={() => setRenameTarget(null)}><Form form={renameForm} layout="vertical"><Form.Item name="title" label="会话标题" rules={[{ required: true, whitespace: true, message: '请输入会话标题' }, { max: 120, message: '标题不能超过 120 个字符' }]}><Input autoFocus maxLength={120} onPressEnter={() => void confirmRename()} /></Form.Item></Form></Modal>
  </main>
}
