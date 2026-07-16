import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Actions, Bubble, Prompts, Sender, Sources, ThoughtChain } from '@ant-design/x'
import { Markdown } from '@/shared/ui/Markdown'
import { App, Avatar, Button, Cascader, Popover } from 'antd'
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  CaretDownOutlined,
  CaretRightOutlined,
  CodeOutlined,
  CopyOutlined,
  NumberOutlined,
  DownOutlined,
  BookOutlined,
  GlobalOutlined,
  PaperClipOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SafetyOutlined,
  SearchOutlined,
  StopOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { useChat } from './useChat'
import type { Message, ThoughtStep, ToolStep } from './types'
import type { ModelConfig, ReasoningEffort } from '@/shared/types/common'
import { useTranslation } from 'react-i18next'
import { copyToClipboard } from '@/shared/lib/clipboard'
import { reasoningEffortLabel } from '@/shared/lib/reasoning'
import { supportedReasoningEfforts } from './utils'
import './chat.css'

const promptKeys = ['cve', 'exposure', 'runbook'] as const

const reasoningOptions = (model: ModelConfig | null) => {
  return supportedReasoningEfforts(model).map((value) => ({ value, label: reasoningEffortLabel(value) }))
}

interface ModelSettingsOption {
  value: string
  label: string
  disabled?: boolean
  children?: ModelSettingsOption[]
}

const renderRaw = (value: unknown) => (typeof value === 'string' ? value : JSON.stringify(value, null, 2))
function RawDetails({ label, value, copyLabel }: { label: string; value: unknown; copyLabel: string }) {
  if (value === undefined || value === null || value === '') return null
  const content = renderRaw(value)
  return (
    <details className="raw-details">
      <summary>{label}</summary>
      <div>
        <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => void copyToClipboard(content)}>
          {copyLabel}
        </Button>
        <pre>{content}</pre>
      </div>
    </details>
  )
}
function toolNode(tool: ToolStep, labels: { input: string; output: string; copy: string }) {
  return {
    key: `tool-${tool.id}`,
    title: tool.name,
    status: tool.status,
    blink: tool.status === 'loading',
    collapsible: true,
    description: tool.summary ?? undefined,
    footer: (
      <>
        {tool.duration != null && <span>{tool.duration.toFixed(1)}s</span>}
        <RawDetails label={labels.input} value={tool.input} copyLabel={labels.copy} />
        <RawDetails label={labels.output} value={tool.output} copyLabel={labels.copy} />
      </>
    ),
  }
}
function thoughtNode(thought: ThoughtStep) {
  return {
    key: `thought-${thought.id}`,
    title: thought.title,
    status: thought.status,
    blink: thought.status === 'loading',
    collapsible: true,
    description: thought.summary ?? undefined,
    footer: thought.duration != null ? `${thought.duration.toFixed(1)}s` : undefined,
  }
}

function ModelSettings({
  models,
  selectedModel,
  reasoningEffort,
  availableReasoningOptions,
  disabled,
  onModelChange,
  onReasoningChange,
}: {
  models: ModelConfig[]
  selectedModel: ModelConfig | null
  reasoningEffort: ReasoningEffort | null
  availableReasoningOptions: { value: ReasoningEffort; label: string }[]
  disabled: boolean
  onModelChange: (value: string) => void
  onReasoningChange: (value: ReasoningEffort) => void
}) {
  const { t } = useTranslation('chat')
  const [open, setOpen] = useState(false)
  const [activeGroup, setActiveGroup] = useState<'model' | 'reasoning'>('model')
  const label = `${selectedModel?.name ?? t('noModel')}${reasoningEffort ? ` · ${reasoningEffortLabel(reasoningEffort)}` : ''}`
  const options = useMemo<ModelSettingsOption[]>(() => {
    const modelOptions = models.map((model) => ({
      value: model.id,
      label: model.name,
      disabled: !model.enabled || !model.configured,
    }))
    const effortOptions = availableReasoningOptions.map((option) => ({ value: option.value, label: option.label }))
    return [
      { value: 'model', label: t('model'), children: modelOptions },
      ...(effortOptions.length ? [{ value: 'reasoning', label: t('reasoningEffort'), children: effortOptions }] : []),
    ]
  }, [availableReasoningOptions, models, t])
  const selectedPath =
    activeGroup === 'reasoning' && reasoningEffort
      ? ['reasoning', reasoningEffort]
      : selectedModel
        ? ['model', selectedModel.id]
        : undefined
  const selectedPathKey = selectedPath?.join(':') ?? 'none'
  const handleChange = (value: (string | number)[]) => {
    const [group, leaf] = value.map(String)
    if (disabled || !leaf) return
    if (group === 'model') {
      setActiveGroup('model')
      onModelChange(leaf)
    }
    if (group === 'reasoning' && availableReasoningOptions.some((option) => option.value === leaf)) {
      setActiveGroup('reasoning')
      onReasoningChange(leaf as ReasoningEffort)
    }
  }
  const renderOption = (option: ModelSettingsOption) => {
    const current = option.value === selectedModel?.id || option.value === reasoningEffort
    return (
      <span className="model-settings-cascader-option">
        <span>{option.label}</span>
        {current && <span>{t('current')}</span>}
      </span>
    )
  }
  return (
    <Popover
      trigger="click"
      open={open}
      onOpenChange={setOpen}
      placement="topRight"
      classNames={{ root: 'model-settings-popover' }}
      content={
        <div className="model-settings-cascader-host">
          <Cascader
            key={selectedPathKey}
            className="model-settings-cascader"
            classNames={{ popup: { root: 'model-settings-cascader-popup' } }}
            options={options}
            value={selectedPath}
            open={open}
            disabled={disabled}
            allowClear={false}
            changeOnSelect={false}
            expandTrigger="hover"
            placement="bottomRight"
            variant="borderless"
            optionRender={renderOption}
            onChange={handleChange}
            getPopupContainer={(node) => node.closest('.model-settings-cascader-host') ?? document.body}
          />
        </div>
      }
    >
      <Button className="model-settings-trigger" type="text" disabled={disabled} aria-label={t('modelAndReasoning')} title={label}>
        <span className="model-select-value" title={selectedModel?.name ?? ''}>
          {label}
        </span>
        <DownOutlined />
      </Button>
    </Popover>
  )
}

function MessageBody({ message, retry }: { message: Message; retry: () => void }) {
  const { t } = useTranslation('chat')
  const { message: toast } = App.useApp()
  const [thoughtOpen, setThoughtOpen] = useState(message.status === 'streaming' || message.status === 'retrying')
  const motionState = message.role === 'assistant' ? (message.status ?? 'completed') : 'sent'
  const actions = [
    {
      key: 'copy',
      label: t('common:copy'),
      icon: <CopyOutlined />,
      onItemClick: () => void copyToClipboard(message.content),
    },
    ...(message.role === 'assistant'
      ? [
          { key: 'retry', label: t('regenerate'), icon: <ReloadOutlined />, onItemClick: retry },
          ...(message.run_id
            ? [
                {
                  key: 'copy-run-id',
                  label: t('copyRunId'),
                  icon: <NumberOutlined />,
                  onItemClick: () => {
                    void copyToClipboard(message.run_id ?? '').then((copied) =>
                      copied ? toast.success(t('runIdCopied')) : toast.error(t('runIdCopyFailed'))
                    )
                  },
                },
              ]
            : []),
        ]
      : []),
  ]
  if (message.role !== 'assistant')
    return (
      <div className={`message-body message-body--${motionState}`}>
        <p>{message.content}</p>
        <div className="message-actions-bar"><Actions className="message-actions" items={actions} /></div>
      </div>
    )
  const chain = [...(message.thought_chain ?? []).map(thoughtNode), ...(message.tool_steps ?? []).map((tool) => toolNode(tool, { input: t('rawToolInput'), output: t('rawToolOutput'), copy: t('common:copy') }))]
  const hasThoughts = chain.length > 0 || Boolean(message.reasoning)
  return (
    <div className={`message-body message-body--${motionState}`}>
      {hasThoughts && (
        <section className="thought-section">
          <Button
            className="thought-toggle"
            type="text"
            size="small"
            icon={thoughtOpen ? <CaretDownOutlined /> : <CaretRightOutlined />}
            onClick={() => setThoughtOpen((open) => !open)}
            aria-expanded={thoughtOpen}
          >
            {t('thoughtProcess')}
          </Button>
          {thoughtOpen && (
            <div className="thought-content">
              <RawDetails label={t('rawReasoning')} copyLabel={t('common:copy')} value={message.reasoning} />
              {chain.length > 0 && (
                <ThoughtChain
                  className="tool-chain"
                  items={chain}
                  defaultExpandedKeys={chain.filter((item) => item.status === 'loading').map((item) => item.key)}
                />
              )}
            </div>
          )}
        </section>
      )}
      {message.content ? (
        <Markdown
          content={message.content}
          streaming={{ hasNextChunk: !message.final, tail: !message.final }}
          openLinksInNewTab
          escapeRawHtml
        />
      ) : (
        <div className="response-pending">
          {message.status === 'paused'
            ? t('awaitingApproval')
            : message.status === 'cancelled'
              ? t('status.cancelled')
              : message.status === 'retrying' && message.retry
                ? t('retryingDetail', { attempt: message.retry.attempt, max: message.retry.maxAttempts })
                : t('establishingRun')}
        </div>
      )}
      {message.status === 'paused' && (
        <output className="message-run-paused" aria-live="polite">
          {t('awaitingApproval')}
        </output>
      )}
      {(message.sources?.length ?? 0) > 0 && (
        <Sources
          title={t('sources')}
          items={
            message.sources?.map((source) => ({
              key: source.id,
              title: source.title,
              url: source.url ?? undefined,
              description: source.snippet ?? undefined,
            })) ?? []
          }
        />
      )}
      <div className={`run-strip run-${message.status ?? 'completed'}`}>
        <span className="run-status">
          {({
            streaming: t('status.streaming'),
            retrying: t('status.retrying'),
            paused: t('status.paused'),
            completed: t('status.completed'),
            cancelled: t('status.cancelled'),
            failed: t('status.failed'),
          } as const)[message.status ?? 'completed']}
        </span>
        {message.metrics?.duration != null && (
          <span className="run-metric" title={t('duration')}>
            {message.metrics.duration.toFixed(1)}s
          </span>
        )}
        {message.metrics?.total_tokens != null && (
          <span className="run-metric" title={`${message.metrics.total_tokens.toLocaleString()} tokens`}>
            {Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(message.metrics.total_tokens)} tokens
          </span>
        )}
      </div>
      {message.error && (
        <div className="message-run-error" role="alert">
          {message.error.code ? `${message.error.code}: ` : ''}
          {message.error.message}
        </div>
      )}
      {message.final && <div className="message-actions-bar"><Actions className="message-actions" items={actions} /></div>}
    </div>
  )
}

export function ChatPage() {
  const { t } = useTranslation('chat')
  const chat = useChat()
  const scrollRef = useRef<HTMLDivElement>(null)
  const [followLatest, setFollowLatest] = useState(true)
  const activeSession = useMemo(
    () => (chat.sessions.data ?? []).find((session) => session.session_id === chat.sessionId),
    [chat.sessionId, chat.sessions.data]
  )
  const bubbles = chat.state.messages
    .filter((item) => item.content || item.role === 'assistant')
    .map((item) => ({
      key: item.id,
      role: item.role === 'user' ? 'user' : 'ai',
      content: item,
      placement: item.role === 'user' ? ('end' as const) : ('start' as const),
      variant: item.role === 'user' ? ('filled' as const) : ('outlined' as const),
      streaming: item.status === 'streaming' || item.status === 'retrying',
      avatar:
        item.role === 'user' ? (
          <Avatar icon={<UserOutlined />} />
        ) : (
          <Avatar shape="square" className="agent-avatar">
            T
          </Avatar>
        ),
      contentRender: (value: Message) => <MessageBody message={value} retry={() => chat.retry(value.id)} />,
    }))
  const activeRun = [...chat.state.messages].reverse().find((item) => item.role === 'assistant' && (item.status === 'streaming' || item.status === 'retrying'))
  const pausedRun = [...chat.state.messages].reverse().find((item) => item.role === 'assistant' && item.status === 'paused')
  const availableReasoningOptions = reasoningOptions(chat.selectedModel)
  const inputDisabled = !chat.selectedModel?.enabled || !chat.selectedModel.configured
  const liveSearchSupported = Boolean(chat.selectedModel?.capabilities?.supports_live_search)
  const sendDisabled = inputDisabled || Boolean(pausedRun) || !chat.state.input.trim()
  const scrollToLatest = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const node = scrollRef.current
    if (!node) return
    node.scrollTo({ top: node.scrollHeight, behavior })
    setFollowLatest(true)
  }, [])

  // Prefer instant scroll while streaming to avoid smooth-scroll jank on every delta.
  const lastAssistant = chat.state.messages.at(-1)
  const streamTick = useMemo(() => {
    if (!lastAssistant || lastAssistant.role !== 'assistant') {
      return `${chat.state.messages.length}:idle`
    }
    return [
      chat.state.messages.length,
      lastAssistant.status ?? 'done',
      lastAssistant.content.length,
      lastAssistant.tool_steps?.length ?? 0,
      lastAssistant.thought_chain?.length ?? 0,
    ].join(':')
  }, [chat.state.messages, lastAssistant])

  useEffect(() => {
    if (!followLatest) return
    const streaming =
      lastAssistant?.role === 'assistant' &&
      (lastAssistant.status === 'streaming' || lastAssistant.status === 'retrying')
    const behavior: ScrollBehavior = streaming ? 'auto' : 'smooth'
    const id = requestAnimationFrame(() => {
      const node = scrollRef.current
      if (!node) return
      node.scrollTo({ top: node.scrollHeight, behavior })
    })
    return () => cancelAnimationFrame(id)
  }, [chat.sessionId, followLatest, streamTick, lastAssistant?.role, lastAssistant?.status])

  useEffect(() => {
    setFollowLatest(true)
  }, [chat.sessionId])

  return (
    <main className="chat-page">
      <section className="chat-workspace">
        <header className="chat-context-bar">
          <div>
            <SafetyCertificateOutlined />
            <span>{activeSession?.title || t('securityAnalysis')}</span>
            <span className="context-divider" />
            <span>{chat.selectedModel?.name ?? t('noModel')}</span>
          </div>
          <div className="context-status">
            <span className={activeRun ? 'status-dot active' : 'status-dot'} />
            {activeRun ? t('agentRunning') : pausedRun ? t('awaitingApproval') : chat.sessionId ? t('sessionReady') : t('newAnalysis')}
          </div>
        </header>
        <div
          className="bubble-scroll"
          ref={scrollRef}
          onScroll={(event) => {
            const node = event.currentTarget
            // Larger threshold while content grows so minor layout thrash doesn't unpin.
            const threshold = chat.state.requesting ? 96 : 48
            setFollowLatest(node.scrollHeight - node.scrollTop - node.clientHeight < threshold)
          }}
        >
          {!bubbles.length ? (
            <div className="chat-welcome">
              <div className="welcome-emblem">
                <SafetyOutlined />
              </div>
              <p className="welcome-kicker">{t('welcomeKicker')}</p>
              <h1>{t('welcomeTitle')}</h1>
              <p className="welcome-description">{t('welcomeDescription')}</p>
              <div className="prompt-grid">
                {promptKeys.map((key, index) => {
                  const prompt = {
                    key,
                    label: t(`prompts.${key}.label`),
                    description: t(`prompts.${key}.description`),
                  }
                  return (
                    <button
                      key={prompt.key}
                      type="button"
                      className="prompt-card"
                      onClick={() => chat.dispatch({ type: 'input', value: prompt.label })}
                    >
                      <span className={`prompt-icon prompt-icon-${index}`}>
                        {index === 0 ? <SearchOutlined /> : index === 1 ? <SafetyCertificateOutlined /> : <CodeOutlined />}
                      </span>
                      <strong>{prompt.label}</strong>
                      <small>{prompt.description}</small>
                    </button>
                  )
                })}
              </div>
            </div>
          ) : (
            <Bubble.List items={bubbles} autoScroll={false} />
          )}
          {chat.state.messages.at(-1)?.followups?.length ? (
            <Prompts
              className="followup-prompts"
              title={t('continueAnalysis')}
              items={chat.state.messages.at(-1)?.followups?.map((label, index) => ({ key: String(index), label })) ?? []}
              onItemClick={({ data }) => void chat.submit(String(data.label ?? ''))}
            />
          ) : null}
          {chat.state.error && (
            <div className="chat-error" role="alert">
              {chat.state.error}
              <Button type="link" size="small" onClick={() => chat.retry(chat.state.messages.at(-1)?.id ?? '')}>
                {t('common:retry')}
              </Button>
            </div>
          )}
        </div>
        {!followLatest && (
          <Button
            className="latest-button"
            shape="round"
            icon={<ArrowDownOutlined />}
            onClick={() => scrollToLatest('smooth')}
          >
            {t('jumpToLatest')}
          </Button>
        )}
        <div className="sender-shell">
          <div className="sender-context">
            <SafetyCertificateOutlined />
            {activeSession?.title || t('workspace')}
          </div>
          <Sender
            value={chat.state.input}
            onChange={(value) => chat.dispatch({ type: 'input', value })}
            onSubmit={(value) => void chat.submit(value)}
            loading={chat.state.requesting}
            disabled={inputDisabled || Boolean(pausedRun)}
            suffix={false}
            placeholder={chat.selectedModel?.configured ? t('placeholderReady') : t('placeholderNoModel')}
            autoSize={{ minRows: 1, maxRows: 5 }}
            footer={
              <div className="sender-controls">
                <div className="sender-toggles">
                  <Button
                    className={chat.state.liveSearch ? 'sender-toggle active' : 'sender-toggle'}
                    type="text"
                    size="small"
                    icon={<GlobalOutlined />}
                    aria-pressed={chat.state.liveSearch}
                    aria-label={t('liveSearch')}
                    title={t('liveSearchHelp')}
                    disabled={chat.state.requesting || Boolean(pausedRun) || !liveSearchSupported}
                    onClick={() => chat.setLiveSearch(!chat.state.liveSearch)}
                  >
                    {t('liveSearch')}
                  </Button>
                  <Button
                    className={chat.state.searchKnowledge ? 'sender-toggle active' : 'sender-toggle'}
                    type="text"
                    size="small"
                    icon={<BookOutlined />}
                    aria-pressed={chat.state.searchKnowledge}
                    aria-label={t('knowledgeSearch')}
                    title={t('knowledgeSearchHelp')}
                    disabled={chat.state.requesting || Boolean(pausedRun)}
                    onClick={() => chat.setSearchKnowledge(!chat.state.searchKnowledge)}
                  >
                    {t('knowledgeSearch')}
                  </Button>
                  <Button className="sender-extension" type="text" icon={<PaperClipOutlined />} disabled aria-label={t('attachmentsComing')} />
                </div>
                <div className="sender-actions">
                  <ModelSettings
                    models={chat.models.data?.models ?? []}
                    selectedModel={chat.selectedModel}
                    reasoningEffort={chat.state.reasoningEffort}
                    availableReasoningOptions={availableReasoningOptions}
                    disabled={chat.state.requesting}
                    onModelChange={chat.setModel}
                    onReasoningChange={chat.setReasoningEffort}
                  />
                  <Button
                    aria-label={chat.state.requesting ? t('stopGenerating') : t('sendMessage')}
                    title={chat.state.requesting ? t('stopGenerating') : t('sendMessage')}
                    type={chat.state.requesting ? 'default' : 'primary'}
                    danger={chat.state.requesting}
                    shape="circle"
                    icon={chat.state.requesting ? <StopOutlined /> : <ArrowUpOutlined />}
                    disabled={chat.state.requesting ? false : sendDisabled}
                    onClick={() => {
                      if (chat.state.requesting) void chat.cancel()
                      else void chat.submit(chat.state.input)
                    }}
                  />
                </div>
              </div>
            }
          />
        </div>
      </section>
    </main>
  )
}
