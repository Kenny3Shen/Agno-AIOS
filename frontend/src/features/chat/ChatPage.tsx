import { useCallback, useEffect, useMemo, useRef, useState, type ComponentRef, type DragEvent } from 'react'
import type { ReactNode } from 'react'
import { Actions, Attachments, Bubble, FileCard, Prompts, Sender, Sources, ThoughtChain } from '@ant-design/x'
import { Markdown } from '@/shared/ui/Markdown'
import { Alert, App, Avatar, Button, Cascader, Popover, Select, Spin, Tag, Tooltip } from 'antd'
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
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useChat } from './useChat'
import { ChatTaskPanel } from './ChatTaskPanel'
import { formatAttachmentLimitError, MAX_CHAT_FILES, validateChatAttachments } from './attachmentLimits'
import { unarchiveSession } from './api'
import { chatKeys } from './queries'
import { markSessionActiveInCaches } from './sessionCache'
import type { Message, TeamTaskState, ThoughtStep, ToolStep } from './types'
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
  isKnowledgeToggleActive,
  isLiveSearchToggleActive,
} from './utils'
import './chat.css'

const promptKeys = ['cve', 'exposure', 'runbook'] as const

const attachmentUid = (file: File, index: number) =>
  `${file.name}-${file.size}-${file.lastModified}-${index}`


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
  const title = labels.toolTitle(tool.name) || tool.name
  const memberHint =
    tool.member_name && !title.includes(tool.member_name)
      ? tool.member_name
      : undefined
  return {
    key: `tool-${tool.id}`,
    title,
    status: tool.status,
    blink: tool.status === 'loading',
    collapsible: true,
    description: tool.summary ?? memberHint,
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
    content: undefined as ReactNode | undefined,
  }
}

function TeamTaskBoard({ state }: { state: TeamTaskState }) {
  const { t } = useTranslation('chat')
  if (!state.tasks.length && !state.taskSummary && !state.goalComplete) return null
  const completed = state.tasks.filter((task) => task.status === 'completed').length
  const statusLabel = (status: TeamTaskState['tasks'][number]['status']) =>
    t(`teamTasks.status.${status}`, { defaultValue: status })
  return (
    <section className="team-task-board" aria-label={t('teamTasks.title')} aria-live="polite">
      <header className="team-task-board__header">
        <span className="team-task-board__title">
          <NodeIndexOutlined />
          {t('teamTasks.title')}
        </span>
        {state.tasks.length ? (
          <span className="team-task-board__progress">
            {t('teamTasks.progress', { completed, total: state.tasks.length })}
          </span>
        ) : null}
      </header>
      {state.taskSummary ? <p className="team-task-board__summary">{state.taskSummary}</p> : null}
      {state.tasks.length ? (
        <ol className="team-task-board__list">
          {state.tasks.map((task) => (
            <li key={task.id} className={`team-task-board__item is-${task.status}`}>
              <span className="team-task-board__marker" aria-label={statusLabel(task.status)} />
              <div className="team-task-board__body">
                <div className="team-task-board__row">
                  <strong>{task.title}</strong>
                  <span className="team-task-board__status">{statusLabel(task.status)}</span>
                </div>
                {task.assignee ? (
                  <span className="team-task-board__assignee">
                    {t('teamTasks.assignee', { name: task.assignee })}
                  </span>
                ) : null}
                {task.description ? <p>{task.description}</p> : null}
                {task.dependencies?.length ? (
                  <span className="team-task-board__dependencies">
                    {t('teamTasks.dependencies', { items: task.dependencies.join(' · ') })}
                  </span>
                ) : null}
                {task.result ? (
                  <details className="team-task-board__result">
                    <summary>{t('teamTasks.result')}</summary>
                    <p>{task.result}</p>
                  </details>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      ) : null}
      {state.goalComplete ? (
        <footer className="team-task-board__complete">
          <strong>{t('teamTasks.goalComplete')}</strong>
          {state.completionSummary ? <span>{state.completionSummary}</span> : null}
        </footer>
      ) : null}
    </section>
  )
}

function AgentSettings({
  agents,
  selectedAgentId,
  disabled,
  onChange,
}: {
  agents: {
    id: string
    name: string
    description?: string
    kind?: string
    category?: string
    mode?: string
    members?: { id: string; name: string; role?: string }[]
  }[]
  selectedAgentId: string
  disabled: boolean
  onChange: (value: string) => void
}) {
  const { t } = useTranslation('chat')
  const options = (agents.length
    ? agents
    : [
        { id: 'security-operations', name: t('agents.securityOperations'), description: t('agents.securityOperationsHint') },
        { id: 'data-analysis', name: t('agents.dataAnalysis'), description: t('agents.dataAnalysisHint') },
        { id: 'deep-research', name: t('agents.deepResearch'), description: t('agents.deepResearchHint') },
      ]
  ).map((agent) => {
    const isTeam = agent.kind === 'team' || agent.category === 'team'
    const modeRaw =
      isTeam && 'mode' in agent && agent.mode
        ? String(agent.mode)
        : ''
    const modeLabel = modeRaw
      ? t(`agents.teamMode.${modeRaw}`, { defaultValue: modeRaw })
      : ''
    const modeTag = modeLabel ? ` · ${modeLabel}` : ''
    const members = isTeam
      ? (agent.members ?? [])
          .map((member) => member.name.trim())
          .filter(Boolean)
          .join(' · ')
      : ''
    return {
      value: agent.id,
      label: isTeam ? `${agent.name} · ${t('agents.teamBeta')}${modeTag}` : agent.name,
      title: agent.description || agent.name,
      roster: members ? t('agents.teamMembers', { members }) : undefined,
    }
  })
  const current = options.find((item) => item.value === selectedAgentId) ?? options[0]
  return (
    <Select
      className="agent-settings-select"
      size="small"
      variant="borderless"
      disabled={disabled}
      value={current?.value}
      options={options}
      optionLabelProp="label"
      popupMatchSelectWidth={false}
      aria-label={t('agent')}
      title={current?.title || t('agent')}
      onChange={onChange}
      optionRender={(option) => (
        <div className="agent-settings-option">
          <strong>{option.label}</strong>
          {option.data.title && option.data.title !== option.label ? (
            <small>{option.data.title}</small>
          ) : null}
          {option.data.roster ? <small className="agent-settings-option__roster">{option.data.roster}</small> : null}
        </div>
      )}
    />
  )
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
            ? [{ key: 'retry', label: t('regenerate'), title: t('regenerateAttachmentsHint'), icon: <ReloadOutlined />, onItemClick: retry }]
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
        {message.attachments?.length ? (
          <div className="message-attachments">
            <FileCard.List
              size="small"
              items={message.attachments.map((item) => ({
                name: item.name,
                description: item.mime || item.kind,
                type: item.kind === 'image' ? 'image' : item.kind === 'audio' ? 'audio' : item.kind === 'video' ? 'video' : 'file',
              }))}
            />
          </div>
        ) : null}
        {message.content ? <p>{message.content}</p> : null}
        <div className="message-actions-bar"><Actions className="message-actions" items={actions} /></div>
      </div>
    )
  const toolLabels = {
    input: t('rawToolInput'),
    output: t('rawToolOutput'),
    copy: t('common:copy'),
    toolTitle: (name: string) => formatToolLabel(name, t),
  }
  // Team beta: nest member tools + member:reasoning under primary member thought;
  // keep leader tools / unmatched items as sibling chain entries.
  const thoughts = message.thought_chain ?? []
  const tools = message.tool_steps ?? []
  const usedToolIds = new Set<string>()
  const usedThoughtIds = new Set<string>()
  const chain: Array<ReturnType<typeof thoughtNode> | ReturnType<typeof toolNode>> = []
  for (const thought of thoughts) {
    const thoughtId = String(thought.id || '')
    if (usedThoughtIds.has(thoughtId)) continue
    // Nested under member:{id} when parent exists; otherwise keep top-level.
    const nestedReasonMatch = /^member:([^:]+):reasoning$/.exec(thoughtId)
    if (nestedReasonMatch) {
      const parentId = `member:${nestedReasonMatch[1]}`
      if (thoughts.some((item) => item.id === parentId)) continue
    }
    const node = thoughtNode(thought)
    const memberMatch = /^member:([^:]+)$/.exec(thoughtId)
    if (memberMatch) {
      const memberId = memberMatch[1]
      const nested: ReactNode[] = []
      const reasonThought = thoughts.find((item) => item.id === `member:${memberId}:reasoning`)
      if (reasonThought) {
        usedThoughtIds.add(String(reasonThought.id))
        const reasonNode = thoughtNode(reasonThought)
        nested.push(
          <div key={reasonNode.key} className={`member-tool-item status-${reasonNode.status || 'default'}`}>
            <div className="member-tool-title">{reasonNode.title}</div>
            {reasonNode.description ? <div className="member-tool-desc">{reasonNode.description}</div> : null}
          </div>,
        )
      }
      const memberTools = tools.filter((tool) => {
        if (tool.member_id !== memberId || usedToolIds.has(tool.id)) return false
        usedToolIds.add(tool.id)
        return true
      })
      for (const tool of memberTools) {
        const item = toolNode(tool, toolLabels)
        nested.push(
          <div key={item.key} className={`member-tool-item status-${item.status || 'default'}`}>
            <div className="member-tool-title">{item.title}</div>
            {item.description ? <div className="member-tool-desc">{item.description}</div> : null}
            {item.footer ? <div className="member-tool-body">{item.footer}</div> : null}
          </div>,
        )
      }
      if (nested.length) {
        node.content = <div className="member-tool-stack">{nested}</div>
      }
    }
    usedThoughtIds.add(thoughtId)
    chain.push(node)
  }
  for (const tool of tools) {
    if (!usedToolIds.has(tool.id)) chain.push(toolNode(tool, toolLabels))
  }
  const hasThoughts = chain.length > 0 || Boolean(message.reasoning)
  return (
    <div className={`message-body message-body--${motionState}`}>
      {message.team_tasks ? <TeamTaskBoard state={message.team_tasks} /> : null}
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
        <output className="message-run-retrying" aria-live="polite">
          {formatRetryDetail(message.retry, t)}
        </output>
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
  const { modal, message: toastMessage } = App.useApp()
  const router = useRouter()
  const chat = useChat()
  const queryClient = useQueryClient()
  const unarchiveMutation = useMutation({
    mutationFn: async () => {
      const id = chat.sessionId
      if (!id) throw new Error('missing session')
      await unarchiveSession(id)
      return id
    },
    onSuccess: async (id) => {
      const base =
        chat.activeSessionMeta?.session_id === id
          ? chat.activeSessionMeta
          : {
              session_id: id,
              preview: chat.activeSessionMeta?.preview || '',
              created_at: chat.activeSessionMeta?.created_at || Date.now() / 1_000,
              updated_at: Date.now() / 1_000,
            }
      markSessionActiveInCaches(queryClient, { ...base, archived: false })
      await queryClient.invalidateQueries({ queryKey: chatKeys.sessionLists })
      toastMessage.success(t('shell:conversations.unarchived'))
    },
    onError: (error: unknown) => {
      toastMessage.error(
        error instanceof Error ? error.message : t('shell:conversations.unarchiveFailed'),
      )
    },
  })
  const scrollRef = useRef<HTMLDivElement>(null)
  const senderShellRef = useRef<HTMLDivElement>(null)
  const workspaceRef = useRef<HTMLDivElement>(null)
  const attachmentsRef = useRef<ComponentRef<typeof Attachments> | null>(null)
  const [openAttachments, setOpenAttachments] = useState(false)
  const [workspaceDragOver, setWorkspaceDragOver] = useState(false)
  const dragDepthRef = useRef(0)
  const attachmentFilesByUid = useMemo(
    () =>
      new Map(
        (chat.attachments ?? []).map((file, index) => [attachmentUid(file, index), file]),
      ),
    [chat.attachments],
  )
  const cancelRef = useRef(chat.cancel)
  cancelRef.current = chat.cancel
  const dispatchRef = useRef(chat.dispatch)
  dispatchRef.current = chat.dispatch
  const requestingRef = useRef(chat.state.requesting)
  requestingRef.current = chat.state.requesting
  const [followLatest, setFollowLatest] = useState(true)
  const activeSession = useMemo(
    () =>
      chat.activeSessionMeta ??
      (chat.sessions.data ?? []).find((session) => session.session_id === chat.sessionId),
    [chat.activeSessionMeta, chat.sessionId, chat.sessions.data]
  )
  const bubbles = chat.state.messages
    .filter((item) => item.content || item.attachments?.length || item.role === 'assistant')
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
  const isWorkflowSession =
    String(chat.activeSessionMeta?.session_type || '').toLowerCase() === 'workflow'
  const inputDisabled =
    !chat.selectedModel?.enabled ||
    !chat.selectedModel.configured ||
    Boolean(chat.sessionMissing) ||
    Boolean(chat.sessionMetaFailed) ||
    Boolean(chat.sessionMetaLoading) ||
    Boolean(chat.teamSessionChecking) ||
    Boolean(chat.teamSessionUnavailable) ||
    isWorkflowSession
  const liveSearchSupported = Boolean(chat.selectedModel?.capabilities?.supports_live_search)
  const latestAssistant = useMemo(
    () => [...chat.state.messages].reverse().find((item) => item.role === 'assistant'),
    [chat.state.messages],
  )
  const knowledgeToggleActive = isKnowledgeToggleActive(
    chat.state.searchKnowledge,
    chat.state.enableTools,
  )
  const liveSearchToggleActive = isLiveSearchToggleActive(
    chat.state.liveSearch,
    chat.state.enableTools,
    liveSearchSupported,
  )
  const hasAttachments = (chat.attachments?.length ?? 0) > 0
  const sendDisabled =
    inputDisabled || Boolean(pausedRun) || (!chat.state.input.trim() && !hasAttachments)
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
      lastAssistant.team_tasks?.tasks.map((task) => `${task.id}:${task.status}`).join(',') ?? '',
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
  const showSessionMetaLoading =
    sessionMetaBusy && !chat.state.requesting && chat.state.messages.length === 0
  const showHistoryLoading =
    historyBusy && !sessionMetaBusy && !chat.state.requesting && chat.state.messages.length === 0
  // Workflow deep-links redirect away; avoid a welcome flash while effect runs.
  const showWorkflowRedirecting =
    Boolean(chat.sessionId) &&
    isWorkflowSession &&
    !chat.state.requesting &&
    chat.state.messages.length === 0
  const showSessionMissing =
    Boolean(chat.sessionId) &&
    Boolean(chat.sessionMissing) &&
    !chat.state.requesting &&
    chat.state.messages.length === 0
  const showSessionMetaError =
    Boolean(chat.sessionId) &&
    Boolean(chat.sessionMetaFailed) &&
    !chat.state.requesting &&
    chat.state.messages.length === 0
  const showTeamUnavailable =
    Boolean(chat.sessionId) &&
    Boolean(chat.teamSessionUnavailable) &&
    !chat.state.requesting
  const showHistoryError =
    Boolean(chat.sessionId) &&
    chat.history.isError &&
    !chat.state.requesting &&
    !showSessionMissing &&
    !showSessionMetaError

  // Soft errors (e.g. server cancel failed) auto-dismiss; keep hard run failures until dismiss/retry.

  useEffect(() => {
    if (!chat.state.error) return
    const hardFailure = chat.state.messages.some(
      (message) => message.role === 'assistant' && message.status === 'failed',
    )
    if (hardFailure) return
    const timer = window.setTimeout(() => {
      dispatchRef.current({ type: 'clear-error' })
    }, 8_000)
    return () => window.clearTimeout(timer)
  }, [chat.state.error, chat.state.messages])

  // Esc stops an in-flight run (including model retry backoff).
  // Skip when a modal/drawer owns Escape (e.g. rename session).
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented) return
      if (event.metaKey || event.ctrlKey || event.altKey) return
      if (!requestingRef.current) return
      if (isOverlayEscapeTarget(event.target)) return
      event.preventDefault()
      void cancelRef.current()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  // SPA nav + tab close while a run is streaming / retrying.
  const cancelForLeaveRef = useRef(chat.cancel)
  cancelForLeaveRef.current = chat.cancel
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


  const mergeDroppedFiles = useCallback(
    (incoming: File[]) => {
      if (!incoming.length || chat.state.requesting || Boolean(pausedRun) || inputDisabled) return
      const next = [...(chat.attachments ?? []), ...incoming]
      const limitError = validateChatAttachments(next)
      if (limitError) {
        toastMessage.error(formatAttachmentLimitError(limitError, t))
        return
      }
      chat.setAttachments(next)
      setOpenAttachments(true)
    },
    [chat, inputDisabled, pausedRun, t, toastMessage],
  )

  const onWorkspaceDragEnter = useCallback((event: DragEvent) => {
    if (!event.dataTransfer?.types?.includes('Files')) return
    event.preventDefault()
    dragDepthRef.current += 1
    setWorkspaceDragOver(true)
  }, [])

  const onWorkspaceDragLeave = useCallback((event: DragEvent) => {
    if (!event.dataTransfer?.types?.includes('Files')) return
    event.preventDefault()
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1)
    if (dragDepthRef.current === 0) setWorkspaceDragOver(false)
  }, [])

  const onWorkspaceDragOver = useCallback((event: DragEvent) => {
    if (!event.dataTransfer?.types?.includes('Files')) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
  }, [])

  const onWorkspaceDrop = useCallback(
    (event: DragEvent) => {
      if (!event.dataTransfer?.files?.length) return
      event.preventDefault()
      dragDepthRef.current = 0
      setWorkspaceDragOver(false)
      const files = Array.from(event.dataTransfer.files)
      mergeDroppedFiles(files)
    },
    [mergeDroppedFiles],
  )

  return (
    <main className={`chat-page${workspaceDragOver ? ' chat-page--drop-active' : ''}`}>
      <aside className="chat-conversations-rail" aria-label={t('shell:conversations.title')}>
        <ChatTaskPanel variant="page" onNewChat={() => chat.newChat()} />
      </aside>
      <section
        className="chat-workspace"
        ref={workspaceRef}
        onDragEnter={onWorkspaceDragEnter}
        onDragLeave={onWorkspaceDragLeave}
        onDragOver={onWorkspaceDragOver}
        onDrop={onWorkspaceDrop}
      >
        {workspaceDragOver ? (
          <div className="chat-drop-overlay" aria-hidden>
            <PaperClipOutlined />
            <span>{t('attachmentsDropTitle')}</span>
            <small>{t('attachmentsDropHint')}</small>
          </div>
        ) : null}
        <header className="chat-context-bar">
          <div>
            <SafetyCertificateOutlined />
            <span>{activeSession?.title || t('securityAnalysis')}</span>
            {activeSession?.archived ? (
              <>
                <Tag className="context-mode-tag" color="default">
                  {t('shell:conversations.archivedInbox')}
                </Tag>
                <Button
                  size="small"
                  type="link"
                  className="chat-unarchive-link"
                  loading={unarchiveMutation.isPending}
                  onClick={() => unarchiveMutation.mutate()}
                >
                  {t('shell:conversations.unarchive')}
                </Button>
              </>
            ) : null}
            <span className="context-divider" />
            <span>
              {(chat.agents.data ?? []).find((a) => a.id === chat.selectedAgentId)?.name
                || t('agents.securityOperations')}
            </span>
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
          {showSessionMetaError ? (
            <div className="chat-error chat-history-error" role="alert">
              <span className="chat-error__message">
                {t('sessionMetaLoadFailed')}
                {chat.sessionMetaError instanceof Error && chat.sessionMetaError.message.trim() ? (
                  <small className="chat-error__detail"> {chat.sessionMetaError.message}</small>
                ) : null}
              </span>
              <span className="chat-error__actions">
                <Button size="small" type="primary" onClick={() => chat.sessionMetaRefetch()}>
                  {t('common:retry')}
                </Button>
              </span>
            </div>
          ) : null}
          {showHistoryError ? (
            <div className="chat-error chat-history-error" role="alert">
              <span className="chat-error__message">
                {t('historyLoadFailed')}
                {chat.history.error instanceof Error && chat.history.error.message.trim() ? (
                  <small className="chat-error__detail"> {chat.history.error.message}</small>
                ) : null}
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
          {showTeamUnavailable ? (
            <Alert
              className="chat-team-unavailable"
              type="warning"
              showIcon
              title={t('teamSessionUnavailableTitle')}
              description={t('teamSessionUnavailable')}
              action={
                <Button size="small" type="primary" onClick={() => chat.newChat()}>
                  {t('startNewAnalysis')}
                </Button>
              }
            />
          ) : null}
          {showSessionMetaLoading || showWorkflowRedirecting ? (
            <output className="chat-history-loading" aria-live="polite">
              <Spin size="small" />
              <span>{t('sessionMetaLoading')}</span>
            </output>
          ) : showHistoryLoading ? (
            <output className="chat-history-loading" aria-live="polite">
              <Spin size="small" />
              <span>{t('historyLoading')}</span>
            </output>
          ) : showSessionMetaError ? null : showSessionMissing ? (
            <section className="chat-history-error chat-session-missing" aria-label={t('sessionNotFound')}>
              <p className="chat-error__message">{t('sessionNotFound')}</p>
              <Button type="primary" onClick={() => chat.newChat()}>
                {t('newAnalysis')}
              </Button>
            </section>
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
            <output className="chat-retrying" aria-live="polite">
              <span className="chat-retrying__message">
                {formatRetryDetail(lastAssistant.retry, t)}
              </span>
              {/* Stop lives on the sender FAB (Esc) — avoid a second Stop control. */}
              <span className="chat-retrying__hint">{t('stopGeneratingHint')}</span>
            </output>
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
            header={
              <Sender.Header
                title={
                  hasAttachments
                    ? `${t('attachments')} · ${chat.attachments?.length ?? 0}`
                    : t('attachments')
                }
                open={openAttachments || hasAttachments}
                onOpenChange={(open) => {
                  if (!open && !hasAttachments) setOpenAttachments(false)
                  else setOpenAttachments(open)
                }}
                styles={{ content: { padding: 0 } }}
                classNames={{ header: 'chat-attachments-header' }}
              >
                <Attachments
                  ref={attachmentsRef}
                  className="chat-attachments"
                  beforeUpload={() => false}
                  items={(chat.attachments ?? []).map((file, index) => ({
                    uid: attachmentUid(file, index),
                    name: file.name,
                    size: file.size,
                    type: file.type,
                    status: 'done' as const,
                    description: `${Math.max(1, Math.round(file.size / 1024))} KB`,
                  }))}
                  onChange={({ fileList }) => {
                    const next = fileList
                      .map((item) => item.originFileObj ?? attachmentFilesByUid.get(item.uid))
                      .filter((file): file is File => file instanceof File)
                    const limitError = validateChatAttachments(next)
                    if (limitError) {
                      toastMessage.error(formatAttachmentLimitError(limitError, t))
                      return
                    }
                    chat.setAttachments(next)
                    if (next.length > 0) setOpenAttachments(true)
                    else setOpenAttachments(false)
                  }}
                  overflow="scrollX"
                  maxCount={MAX_CHAT_FILES}
                  accept="image/*,.pdf,.txt,.md,.csv,.json,.html,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.py,.js,.xml,.rtf,audio/*,video/*"
                  placeholder={(type) =>
                    type === 'drop'
                      ? {
                          icon: <PaperClipOutlined />,
                          title: t('attachmentsDropTitle'),
                          description: t('attachmentsDropHint'),
                        }
                      : {
                          icon: <PaperClipOutlined />,
                          title: t('attachmentsBrowseTitle'),
                          description: t('attachmentsBrowseHint'),
                        }
                  }
                  getDropContainer={() => workspaceRef.current}
                  styles={{
                    placeholder: { paddingBlock: 14, minHeight: 96 },
                    list: { paddingInline: 10, paddingBlock: 8 },
                  }}
                />
              </Sender.Header>
            }
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
                    className={liveSearchToggleActive ? 'sender-toggle active' : 'sender-toggle'}
                    type="text"
                    size="small"
                    icon={<GlobalOutlined />}
                    aria-pressed={chat.state.liveSearch}
                    aria-label={t('liveSearch')}
                    title={!chat.state.enableTools ? t('liveSearchNeedsTools') : t('liveSearchHelp')}
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
                    className={knowledgeToggleActive ? 'sender-toggle active' : 'sender-toggle'}
                    type="text"
                    size="small"
                    icon={<BookOutlined />}
                    aria-pressed={chat.state.searchKnowledge}
                    aria-label={t('knowledgeSearch')}
                    title={
                      !chat.state.enableTools ? t('knowledgeSearchNeedsTools') : t('knowledgeSearchHelp')
                    }
                    disabled={chat.state.requesting || Boolean(pausedRun) || !chat.state.enableTools}
                    onClick={() => chat.setSearchKnowledge(!chat.state.searchKnowledge)}
                  >
                    {t('knowledgeSearch')}
                  </Button>
                  <Button
                    className={hasAttachments || openAttachments ? 'sender-extension active' : 'sender-extension'}
                    type="text"
                    icon={<PaperClipOutlined />}
                    aria-label={t('attachments')}
                    title={t('attachmentsHelp')}
                    disabled={chat.state.requesting || Boolean(pausedRun) || inputDisabled}
                    onClick={() => {
                      if (hasAttachments || openAttachments) {
                        setOpenAttachments((value) => !value)
                        return
                      }
                      setOpenAttachments(true)
                      // Open native picker after header mounts.
                      window.setTimeout(() => attachmentsRef.current?.select({ multiple: true }), 0)
                    }}
                  />
                </div>
                <div className="sender-actions">
                  <AgentSettings
                    agents={chat.agents.data ?? []}
                    selectedAgentId={chat.selectedAgentId || 'security-operations'}
                    disabled={
                      chat.state.requesting ||
                      Boolean(pausedRun) ||
                      Boolean(chat.teamSessionChecking) ||
                      Boolean(chat.teamSessionUnavailable)
                    }
                    onChange={chat.setSelectedAgent}
                  />
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
