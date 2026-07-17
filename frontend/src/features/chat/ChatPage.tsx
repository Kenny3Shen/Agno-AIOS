import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Actions, Bubble, Prompts, Sender, Sources, ThoughtChain } from '@ant-design/x'
import { Markdown } from '@/shared/ui/Markdown'
import { App, Avatar, Button, Cascader, Popover, Spin, Tag, Tooltip } from 'antd'
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  CaretDownOutlined,
  CloseOutlined,
  CaretRightOutlined,
  CodeOutlined,
  CopyOutlined,
  NumberOutlined,
  NodeIndexOutlined,
  DownOutlined,
  BookOutlined,
  ToolOutlined,
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
import { useBlocker, useRouter } from '@tanstack/react-router'
import { buildTraceSearch, emptyTraceFilters } from '@/features/trace/utils'
import { copyToClipboard } from '@/shared/lib/clipboard'
import { isOverlayEscapeTarget } from '@/shared/lib/keyboard'
import { reasoningEffortLabel } from '@/shared/lib/reasoning'
import {
  formatSkillLabels,
  formatToolLabel,
  formatRetryDetail,
  supportedReasoningEfforts,
  isLastTurnAutoLean,
  isKnowledgeToggleActive,
  isLiveSearchToggleActive,
} from './utils'
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
function toolNode(
  tool: ToolStep,
  labels: { input: string; output: string; copy: string; toolTitle: (name: string) => string },
) {
  return {
    key: `tool-${tool.id}`,
    title: labels.toolTitle(tool.name) || tool.name,
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

function MessageBody({ message, retry, sessionId, requesting = false }: { message: Message; retry: () => void; sessionId?: string | null; requesting?: boolean }) {
  const { t } = useTranslation('chat')
  const { message: toast } = App.useApp()
  const router = useRouter()
  const [thoughtOpen, setThoughtOpen] = useState(message.status === 'streaming' || message.status === 'retrying')
  const motionState = message.role === 'assistant' ? (message.status ?? 'completed') : 'sent'
  const traceSessionId = (message.session_id || sessionId || '').trim()
  const traceRunId = (message.run_id || '').trim()
  const openTrace = () => {
    if (!traceRunId && !traceSessionId) return
    const filters = {
      ...emptyTraceFilters(),
      session_id: traceSessionId,
      run_id: traceRunId,
    }
    const search = buildTraceSearch(filters, traceSessionId, traceRunId)
    void router.history.push(`/trace${search ? `?${search}` : ''}`)
  }
  const actions = [
    {
      key: 'copy',
      label: t('common:copy'),
      icon: <CopyOutlined />,
      onItemClick: () => void copyToClipboard(message.content),
    },
    ...(message.role === 'assistant'
      ? [
          // HITL pause: regenerate would re-fire tools; route through Approvals instead.
          ...(message.final && message.status !== 'paused' && !requesting
            ? [{ key: 'retry', label: t('regenerate'), icon: <ReloadOutlined />, onItemClick: retry }]
            : []),
          ...(traceRunId || traceSessionId
            ? [
                {
                  key: 'open-trace',
                  label: t('openTrace'),
                  icon: <NodeIndexOutlined />,
                  onItemClick: openTrace,
                },
              ]
            : []),
          ...(traceRunId
            ? [
                {
                  key: 'copy-run-id',
                  label: t('copyRunId'),
                  icon: <NumberOutlined />,
                  onItemClick: () => {
                    void copyToClipboard(traceRunId).then((copied) =>
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
  const chain = [...(message.thought_chain ?? []).map(thoughtNode), ...(message.tool_steps ?? []).map((tool) => toolNode(tool, { input: t('rawToolInput'), output: t('rawToolOutput'), copy: t('common:copy'), toolTitle: (name) => formatToolLabel(name, t) }))]
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
        <div
          className={
            message.status === 'retrying'
              ? 'response-pending response-pending--retrying'
              : 'response-pending'
          }
          aria-live="polite"
        >
          {message.status === 'paused'
            ? t('awaitingApproval')
            : message.status === 'cancelled'
              ? t('status.cancelled')
              : message.status === 'retrying'
                ? formatRetryDetail(message.retry, t)
                : t('establishingRun')}
        </div>
      )}
      {message.status === 'retrying' && message.content ? (
        <div className="message-run-retrying" role="status" aria-live="polite">
          {formatRetryDetail(message.retry, t)}
        </div>
      ) : null}
      {message.status === 'paused' && (
        <output className="message-run-paused" aria-live="polite">
          <span>{t('awaitingApproval')}</span>
          {message.approval_id ? (
            <Button
              type="link"
              size="small"
              style={{ paddingInline: 0, marginLeft: 8 }}
              href={`#/approvals?approval_id=${encodeURIComponent(message.approval_id)}`}
            >
              {t('openApproval')}
            </Button>
          ) : null}
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
          {message.status === 'retrying' && message.retry
            ? t('status.retryingProgress', {
                attempt: message.retry.attempt,
                max: message.retry.maxAttempts,
              })
            : ({
                streaming: t('status.streaming'),
                retrying: t('status.retrying'),
                paused: t('status.paused'),
                completed: t('status.completed'),
                cancelled: t('status.cancelled'),
                failed: t('status.failed'),
              } as const)[message.status ?? 'completed']}
        </span>
        {message.enableTools === false ? (
          <Tooltip title={t('toolsSkillsHelp')}>
            <span className="run-metric run-metric--lean">{t('toolsOffBadge')}</span>
          </Tooltip>
        ) : message.leanMode ? (
          <Tooltip title={t('autoLeanHelp')}>
            <span className="run-metric run-metric--lean">{t('autoLeanBadge')}</span>
          </Tooltip>
        ) : null}
        {message.enableTools !== false && !message.leanMode && message.skillNames === null ? (
          <Tooltip title={t('skillsAllEnabled')}>
            <span className="run-metric run-metric--skills">{t('skillsAllEnabledBadge')}</span>
          </Tooltip>
        ) : null}
        {message.enableTools !== false && Array.isArray(message.skillNames) && message.skillNames.length > 0 ? (
          <Tooltip title={t('skillsAttached', { names: formatSkillLabels(message.skillNames) })}>
            <span className="run-metric run-metric--skills">{t('skillsAttachedBadge', { count: message.skillNames.length })}</span>
          </Tooltip>
        ) : null}
        {message.enableTools !== false && !message.leanMode && message.searchKnowledge === false ? (
          <Tooltip title={t('knowledgeSearchHelp')}>
            <span className="run-metric run-metric--lean">{t('knowledgeOffBadge')}</span>
          </Tooltip>
        ) : null}
        {message.metrics?.duration != null && (
          <span className="run-metric" title={t('duration')}>
            {message.metrics.duration.toFixed(1)}s
          </span>
        )}
        {message.metrics?.total_tokens != null && (
          <span
            className="run-metric"
            title={t('tokensMetricTitle', { count: message.metrics.total_tokens.toLocaleString() })}
          >
            {t('tokensMetric', {
              value: Intl.NumberFormat(undefined, {
                notation: 'compact',
                maximumFractionDigits: 1,
              }).format(message.metrics.total_tokens),
            })}
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
  const { modal } = App.useApp()
  const router = useRouter()
  const chat = useChat()
  const scrollRef = useRef<HTMLDivElement>(null)
  const senderShellRef = useRef<HTMLDivElement>(null)
  const workspaceRef = useRef<HTMLDivElement>(null)
  const cancelRef = useRef(chat.cancel)
  cancelRef.current = chat.cancel
  const [followLatest, setFollowLatest] = useState(true)
  const activeSession = useMemo(
    () =>
      chat.activeSessionMeta ??
      (chat.sessions.data ?? []).find((session) => session.session_id === chat.sessionId),
    [chat.activeSessionMeta, chat.sessionId, chat.sessions.data]
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
      contentRender: (value: Message) => (
        <MessageBody message={value} retry={() => chat.retry(value.id)} sessionId={chat.sessionId} requesting={chat.state.requesting} />
      ),
    }))
  const activeRun = [...chat.state.messages].reverse().find((item) => item.role === 'assistant' && (item.status === 'streaming' || item.status === 'retrying'))
  const pausedRun = [...chat.state.messages].reverse().find((item) => item.role === 'assistant' && item.status === 'paused')
  const availableReasoningOptions = reasoningOptions(chat.selectedModel)
  const inputDisabled =
    !chat.selectedModel?.enabled ||
    !chat.selectedModel.configured ||
    Boolean(chat.sessionMissing)
  const liveSearchSupported = Boolean(chat.selectedModel?.capabilities?.supports_live_search)
  const latestAssistant = useMemo(
    () => [...chat.state.messages].reverse().find((item) => item.role === 'assistant'),
    [chat.state.messages],
  )
  const lastTurnAutoLean = isLastTurnAutoLean(chat.state.enableTools, latestAssistant)
  const knowledgeToggleActive = isKnowledgeToggleActive(
    chat.state.searchKnowledge,
    chat.state.enableTools,
    lastTurnAutoLean,
  )
  const liveSearchToggleActive = isLiveSearchToggleActive(
    chat.state.liveSearch,
    chat.state.enableTools,
    liveSearchSupported,
    lastTurnAutoLean,
  )
  const sendDisabled = inputDisabled || Boolean(pausedRun) || !chat.state.input.trim()
  const scrollToLatest = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const node = scrollRef.current
    if (!node) return
    node.scrollTo({ top: node.scrollHeight, behavior })
    setFollowLatest(true)
  }, [])

  // Prefer instant scroll while streaming to avoid smooth-scroll jank on every delta.
  const lastAssistant = [...chat.state.messages].reverse().find((item) => item.role === 'assistant')
  // Soft errors (e.g. server cancel) keep messages healthy — only offer Retry for failed runs.
  const bannerCanRetry = Boolean(
    lastAssistant && (lastAssistant.status === 'failed' || lastAssistant.error?.retryable)
  )
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

  const historyFlags = chat.history as {
    isError?: boolean
    isLoading?: boolean
    isPending?: boolean
    isFetching?: boolean
  }
  const historyBusy =
    Boolean(chat.sessionId) &&
    !historyFlags.isError &&
    (Boolean(historyFlags.isLoading) ||
      Boolean(historyFlags.isPending) ||
      (Boolean(historyFlags.isFetching) && chat.state.messages.length === 0))
  const sessionMetaBusy = Boolean(chat.sessionMetaLoading)
  const showHistoryLoading =
    (historyBusy || sessionMetaBusy) && !chat.state.requesting && chat.state.messages.length === 0
  const showSessionMissing =
    Boolean(chat.sessionId) &&
    Boolean(chat.sessionMissing) &&
    !chat.state.requesting &&
    chat.state.messages.length === 0
  const showHistoryError =
    Boolean(chat.sessionId) && chat.history.isError && !chat.state.requesting && !showSessionMissing

  // Soft errors (e.g. server cancel failed) auto-dismiss; keep hard run failures until dismiss/retry.

  useEffect(() => {
    if (!chat.state.error) return
    const hardFailure = chat.state.messages.some(
      (message) => message.role === 'assistant' && message.status === 'failed',
    )
    if (hardFailure) return
    const timer = window.setTimeout(() => {
      chat.dispatch({ type: 'clear-error' })
    }, 8_000)
    return () => window.clearTimeout(timer)
  }, [chat.state.error, chat.state.messages, chat.dispatch])

  // Esc stops an in-flight run (including model retry backoff).
  // Skip when a modal/drawer owns Escape (e.g. rename session).
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented) return
      if (event.metaKey || event.ctrlKey || event.altKey) return
      if (!chat.state.requesting) return
      if (isOverlayEscapeTarget(event.target)) return
      event.preventDefault()
      void cancelRef.current()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [chat.state.requesting])

  // SPA nav + tab close while a run is streaming / retrying.
  const cancelForLeaveRef = useRef(chat.cancel)
  cancelForLeaveRef.current = chat.cancel
  const requestingRef = useRef(chat.state.requesting)
  requestingRef.current = chat.state.requesting
  useBlocker({
    disabled: !chat.state.requesting,
    enableBeforeUnload: chat.state.requesting,
    shouldBlockFn: async ({ current, next }) => {
      if (!requestingRef.current) return false
      // Same-route session switches (/chat?session=…) are handled by setSession cancel
      // without a second confirm dialog.
      const curPath = String(current.pathname || '')
      const nextPath = String(next.pathname || '')
      if (curPath === nextPath) return false
      const leave = await new Promise<boolean>((resolve) => {
        modal.confirm({
          title: t('leaveWhileGeneratingTitle'),
          content: t('leaveWhileGeneratingContent'),
          okText: t('stopAndLeave'),
          cancelText: t('common:cancel'),
          okButtonProps: { danger: true },
          onOk: () => resolve(true),
          onCancel: () => resolve(false),
        })
      })
      if (!leave) return true
      void cancelForLeaveRef.current()
      return false
    },
  })


  useEffect(() => {
    const shell = senderShellRef.current
    const workspace = workspaceRef.current
    if (!shell || !workspace) return
    const apply = () => {
      const measured = shell.getBoundingClientRect().height
      const height = Number.isFinite(measured) ? Math.ceil(measured) : 72
      workspace.style.setProperty('--chat-sender-offset', `${Math.max(height, 72)}px`)
    }
    apply()
    const observer = new ResizeObserver(apply)
    observer.observe(shell)
    return () => observer.disconnect()
  }, [])

  return (
    <main className="chat-page">
      <section className="chat-workspace" ref={workspaceRef}>
        <header className="chat-context-bar">
          <div>
            <SafetyCertificateOutlined />
            <span>{activeSession?.title || t('securityAnalysis')}</span>
            <span className="context-divider" />
            <span>{chat.selectedModel?.name ?? t('noModel')}</span>
          </div>
          <div className="context-status">
            <span className={activeRun ? 'status-dot active' : pausedRun ? 'status-dot paused' : 'status-dot'} />
            {activeRun ? t('agentRunning') : pausedRun ? t('awaitingApproval') : chat.sessionId ? t('sessionReady') : t('newAnalysis')}
            {(() => {
              if (!chat.state.enableTools) {
                return (
                  <Tag className="context-mode-tag" color="default">
                    {t('toolsOffBadge')}
                  </Tag>
                )
              }
              if (latestAssistant?.enableTools === false) {
                return (
                  <Tooltip title={t('toolsSkillsHelp')}>
                    <Tag className="context-mode-tag" color="default">
                      {t('toolsOffBadge')}
                    </Tag>
                  </Tooltip>
                )
              }
              if (latestAssistant?.leanMode) {
                return (
                  <Tooltip title={t('autoLeanHelp')}>
                    <Tag className="context-mode-tag" color="processing">
                      {t('autoLeanBadge')}
                    </Tag>
                  </Tooltip>
                )
              }
              const names = latestAssistant?.skillNames
              if (names === null) {
                return (
                  <Tooltip title={t('skillsAllEnabled')}>
                    <Tag className="context-mode-tag" color="blue">
                      {t('skillsAllEnabledBadge')}
                    </Tag>
                  </Tooltip>
                )
              }
              if (Array.isArray(names) && names.length > 0) {
                return (
                  <Tooltip title={t('skillsAttached', { names: formatSkillLabels(names) })}>
                    <Tag className="context-mode-tag" color="blue">
                      {t('skillsAttachedBadge', { count: names.length })}
                    </Tag>
                  </Tooltip>
                )
              }
              if (latestAssistant?.searchKnowledge === false) {
                return (
                  <Tooltip title={t('knowledgeSearchHelp')}>
                    <Tag className="context-mode-tag" color="default">
                      {t('knowledgeOffBadge')}
                    </Tag>
                  </Tooltip>
                )
              }
              return null
            })()}
            {pausedRun?.approval_id ? (
              <Button
                type="link"
                size="small"
                className="context-approval-link"
                href={`#/approvals?approval_id=${encodeURIComponent(pausedRun.approval_id)}`}
              >
                {t('openApproval')}
              </Button>
            ) : null}
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
          {showHistoryError ? (
            <div className="chat-error chat-history-error" role="alert">
              <span className="chat-error__message">
                {chat.history.error instanceof Error
                  ? chat.history.error.message
                  : t('historyLoadFailed')}
              </span>
              <span className="chat-error__actions">
                <Button
                  size="small"
                  type="primary"
                  loading={chat.history.isFetching}
                  onClick={() => void chat.history.refetch()}
                >
                  {t('common:retry')}
                </Button>
              </span>
            </div>
          ) : null}
          {showHistoryLoading ? (
            <div className="chat-history-loading" role="status" aria-live="polite">
              <Spin size="small" />
              <span>{t('historyLoading')}</span>
            </div>
          ) : showSessionMissing ? (
            <div className="chat-history-error chat-session-missing" role="status">
              <p className="chat-error__message">{t('sessionNotFound')}</p>
              <Button type="primary" onClick={() => chat.newChat()}>
                {t('newAnalysis')}
              </Button>
            </div>
          ) : showHistoryError && !bubbles.length ? null : !bubbles.length ? (
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
          {chat.state.messages.at(-1)?.followups?.length && !chat.state.requesting && !pausedRun ? (
            <Prompts
              className="followup-prompts"
              title={t('continueAnalysis')}
              items={chat.state.messages.at(-1)?.followups?.map((label, index) => ({ key: String(index), label })) ?? []}
              onItemClick={({ data }) => {
                if (chat.state.requesting || pausedRun) return
                void chat.submit(String(data.label ?? ''))
              }}
            />
          ) : null}
          {lastAssistant?.status === 'retrying' && !chat.state.error ? (
            <div className="chat-retrying" role="status" aria-live="polite">
              <span className="chat-retrying__message">
                {formatRetryDetail(lastAssistant.retry, t)}
              </span>
              {/* Stop lives on the sender FAB (Esc) — avoid a second Stop control. */}
              <span className="chat-retrying__hint">{t('stopGeneratingHint')}</span>
            </div>
          ) : null}
          {chat.state.error && (
            <div className="chat-error" role="alert">
              <span className="chat-error__message">{chat.state.error}</span>
              <span className="chat-error__actions">
                {bannerCanRetry ? (
                  <Button type="link" size="small" onClick={() => chat.retry(lastAssistant?.id ?? '')}>
                    {t('common:retry')}
                  </Button>
                ) : null}
                {(lastAssistant?.run_id || lastAssistant?.session_id || chat.sessionId) ? (
                  <Button
                    type="link"
                    size="small"
                    onClick={() => {
                      const session = (lastAssistant?.session_id || chat.sessionId || '').trim()
                      const runId = (lastAssistant?.run_id || '').trim()
                      const filters = {
                        ...emptyTraceFilters(),
                        session_id: session,
                        run_id: runId,
                      }
                      const search = buildTraceSearch(filters, session, runId)
                      void router.history.push(`/trace${search ? `?${search}` : ''}`)
                    }}
                  >
                    {t('openTrace')}
                  </Button>
                ) : null}
                <Button
                  type="text"
                  size="small"
                  icon={<CloseOutlined />}
                  aria-label={t('common:close')}
                  onClick={() => chat.dispatch({ type: 'clear-error' })}
                />
              </span>
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
        <div className="sender-shell" ref={senderShellRef}>
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
                    className={chat.state.enableTools ? 'sender-toggle active' : 'sender-toggle'}
                    type="text"
                    size="small"
                    icon={<ToolOutlined />}
                    aria-pressed={chat.state.enableTools}
                    aria-label={t('toolsSkills')}
                    title={t('toolsSkillsHelp')}
                    disabled={chat.state.requesting || Boolean(pausedRun)}
                    onClick={() => chat.setEnableTools(!chat.state.enableTools)}
                  >
                    {t('toolsSkills')}
                  </Button>
                  <Button
                    className={liveSearchToggleActive ? 'sender-toggle active' : chat.state.liveSearch && chat.state.enableTools && lastTurnAutoLean ? 'sender-toggle muted' : 'sender-toggle'}
                    type="text"
                    size="small"
                    icon={<GlobalOutlined />}
                    aria-pressed={chat.state.liveSearch}
                    aria-label={t('liveSearch')}
                    title={
                      !chat.state.enableTools
                        ? t('liveSearchNeedsTools')
                        : lastTurnAutoLean
                          ? t('liveSearchAutoLeanHint')
                          : t('liveSearchHelp')
                    }
                    disabled={
                      chat.state.requesting ||
                      Boolean(pausedRun) ||
                      !liveSearchSupported ||
                      !chat.state.enableTools
                    }
                    onClick={() => chat.setLiveSearch(!chat.state.liveSearch)}
                  >
                    {t('liveSearch')}
                  </Button>
                  <Button
                    className={knowledgeToggleActive ? 'sender-toggle active' : chat.state.searchKnowledge && chat.state.enableTools && lastTurnAutoLean ? 'sender-toggle muted' : 'sender-toggle'}
                    type="text"
                    size="small"
                    icon={<BookOutlined />}
                    aria-pressed={chat.state.searchKnowledge}
                    aria-label={t('knowledgeSearch')}
                    title={
                      !chat.state.enableTools
                        ? t('knowledgeSearchNeedsTools')
                        : lastTurnAutoLean
                          ? t('knowledgeSearchAutoLeanHint')
                          : t('knowledgeSearchHelp')
                    }
                    disabled={chat.state.requesting || Boolean(pausedRun) || !chat.state.enableTools}
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
                    title={chat.state.requesting ? t('stopGeneratingHint') : t('sendMessage')}
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
