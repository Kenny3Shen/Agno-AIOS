import type { ModelConfig, ReasoningEffort } from '@/shared/types/common'
import { DEEPSEEK_REASONING_EFFORTS, openaiReasoningEfforts } from '@/shared/lib/reasoning'
import type { ChatAction, ChatRunEvent, ChatSource, ChatState, Message, RunMetrics, RunStatus, ThoughtStep, ToolStatus, ToolStep } from './types'

const readStoredBool = (key: string, fallback: boolean): boolean => {
  try {
    const raw = localStorage.getItem(key)
    if (raw === 'true') return true
    if (raw === 'false') return false
  } catch {
    // ignore
  }
  return fallback
}

/** Humanize skill directory ids for badges/tooltips (no catalog required). */
export const formatSkillLabel = (name: string): string => {
  const raw = (name || '').trim()
  if (!raw) return ''
  let base = raw
  if (base.toLowerCase().endsWith('-skill')) {
    base = base.slice(0, -'-skill'.length)
  }
  const parts = base.split(/[-_]+/).filter(Boolean)
  if (!parts.length) return raw
  return parts
    .map((part) => {
      const lower = part.toLowerCase()
      if (lower === 'cve' || lower === 'hitl' || lower === 'ip' || lower === 'mcp' || lower === 'ir') {
        return lower.toUpperCase()
      }
      return lower.charAt(0).toUpperCase() + lower.slice(1)
    })
    .join(' ')
}

export const formatSkillLabels = (names: string[]): string =>
  names.map(formatSkillLabel).filter(Boolean).join(', ')

/** Built-in MCP tool ids (namespace_fn) → i18n keys under chat.tools.* */
export const BUILTIN_TOOL_I18N_KEYS: Record<string, string> = {
  delegate_task_to_member: 'tools.delegateTaskToMember',
  delegate_task_to_members: 'tools.delegateTaskToMembers',
  get_member_information: 'tools.getMemberInformation',
  get_member_information_tool: 'tools.getMemberInformation',
  basic_send_feishu_notify: 'tools.basic_send_feishu_notify',
  hitl_simulate_containment: 'tools.hitl_simulate_containment',
  playbook_list_workflows: 'tools.playbook_list_workflows',
  playbook_get_method_params: 'tools.playbook_get_method_params',
  playbook_invoke_method: 'tools.playbook_invoke_method',
  playbook_get_exec_result: 'tools.playbook_get_exec_result',
  // Agno Local Skills progressive loaders (not MCP namespace)
  get_skill_instructions: 'tools.get_skill_instructions',
  get_skill_reference: 'tools.get_skill_reference',
  get_skill_script: 'tools.get_skill_script',
}

const TOOL_NS_PREFIXES = ['basic_', 'hitl_', 'playbook_'] as const

/** Title-case unknown tool ids after stripping builtin namespaces. */
export const humanizeToolId = (name: string): string => {
  const raw = (name || '').trim()
  if (!raw) return ''
  let base = raw
  for (const prefix of TOOL_NS_PREFIXES) {
    if (base.startsWith(prefix)) {
      base = base.slice(prefix.length)
      break
    }
  }
  base = base.replace(/__/g, '_').replace(/\./g, '_')
  const parts = base.split(/[-_]+/).filter(Boolean)
  if (!parts.length) return raw
  return parts
    .map((part) => {
      const lower = part.toLowerCase()
      if (
        lower === 'cve' ||
        lower === 'hitl' ||
        lower === 'ip' ||
        lower === 'mcp' ||
        lower === 'ir' ||
        lower === 'id' ||
        lower === 'url' ||
        lower === 'api'
      ) {
        return lower.toUpperCase()
      }
      return lower.charAt(0).toUpperCase() + lower.slice(1)
    })
    .join(' ')
}

/**
 * Humanize MCP / tool call ids for ThoughtChain titles.
 * Pass `t` from useTranslation('chat') for builtin product titles.
 */
export const formatToolLabel = (
  name: string,
  t?: (key: string) => string,
): string => {
  const raw = (name || '').trim()
  if (!raw) return ''
  // Team member tools are projected as "[Member Name] tool_id".
  const memberPrefix = raw.match(/^\[([^\]]+)\]\s+(.+)$/)
  if (memberPrefix) {
    const member = memberPrefix[1]
    const rest = formatToolLabel(memberPrefix[2], t)
    return `[${member}] ${rest}`
  }
  const i18nKey = BUILTIN_TOOL_I18N_KEYS[raw]
  if (i18nKey && t) {
    const translated = t(i18nKey)
    if (translated && translated !== i18nKey) return translated
  }
  return humanizeToolId(raw)
}

export const DEFAULT_CHAT_AGENT_ID = 'security-operations'

export const initialChatState: ChatState = {
  messages: [],
  input: '',
  requesting: false,
  error: null,
  selectedModelId: localStorage.getItem('agno-aios-chat-model-id'),
  selectedAgentId: localStorage.getItem('agno-aios-chat-agent-id') || DEFAULT_CHAT_AGENT_ID,
  reasoningEffort: null,
  searchKnowledge: readStoredBool('agno-aios-chat-search-knowledge', true),
  liveSearch: readStoredBool('agno-aios-chat-live-search', false),
  enableTools: readStoredBool('agno-aios-chat-enable-tools', true),
}

const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object'
const asString = (value: unknown): string | undefined => (typeof value === 'string' ? value : undefined)
const asMetrics = (value: unknown): RunMetrics | null => (isRecord(value) ? (value as RunMetrics) : null)

const updateMessage = (messages: Message[], id: string, callback: (message: Message) => Message) =>
  messages.map((message) => (message.id === id ? callback(message) : message))

export const chatReducer = (state: ChatState, action: ChatAction): ChatState => {
  switch (action.type) {
    case 'history':
      return state.requesting ? state : { ...state, messages: action.messages }
    case 'input':
      return { ...state, input: action.value }
    case 'model':
      return { ...state, selectedModelId: action.value, reasoningEffort: action.reasoningEffort }
    case 'reasoning-effort':
      return { ...state, reasoningEffort: action.value }
    case 'search-knowledge':
      return { ...state, searchKnowledge: action.value }
    case 'live-search':
      return { ...state, liveSearch: action.value }
    case 'enable-tools':
      // Tools-off is an explicit lite path: de-emphasize dependent toggles in UI state.
      return {
        ...state,
        enableTools: action.value,
        ...(action.value
          ? {}
          : {
              // Keep localStorage preference for knowledge; only clear live search which is tool-gated.
              liveSearch: false,
            }),
      }
    case 'agent':
      return { ...state, selectedAgentId: action.value || 'security-operations' }
    case 'start':
      return {
        ...state,
        input: '',
        requesting: true,
        error: null,
        selectedModelId: action.modelId,
        messages: [...state.messages, ...(action.user ? [action.user] : []), action.assistant],
      }
    case 'event': {
      const event: ChatRunEvent = action.event
      const terminal = event.type === 'run.paused' || event.type === 'run.completed' || event.type === 'run.cancelled' || event.type === 'run.failed'
      const messages = updateMessage(state.messages, action.id, (message) => {
        switch (event.type) {
          case 'run.started':
            return { ...message, run_id: event.runId, session_id: event.sessionId ?? message.session_id, status: 'streaming', retry: null, error: null, leanMode: event.leanMode, enableTools: event.enableTools, searchKnowledge: event.searchKnowledge, skillNames: event.skillNames }
          case 'content.delta': {
            if (message.final && message.status !== 'streaming' && message.status !== 'retrying') {
              return message
            }
            // After a provider retry, replace stale partials with the new stream.
            const resumeAfterRetry = message.status === 'retrying'
            const prev = resumeAfterRetry ? '' : message.content
            const delta = event.delta
            // Some providers (and Team show_result) re-send growing snapshots.
            let nextContent = prev + delta
            if (prev && delta.startsWith(prev)) nextContent = delta
            else if (prev && prev.endsWith(delta)) nextContent = prev
            return {
              ...message,
              content: nextContent,
              reasoning: resumeAfterRetry ? null : message.reasoning,
              status: 'streaming',
              retry: null,
              error: null,
            }
          }
          case 'run.retrying':
            if (message.final && message.status !== 'streaming' && message.status !== 'retrying') {
              return message
            }
            return {
              ...message,
              run_id: event.runId ?? message.run_id,
              // Keep partial answer/tools visible during backoff (user can still Esc/stop).
              final: false,
              status: 'retrying',
              error: null,
              retry: {
                attempt: event.attempt,
                maxAttempts: event.maxAttempts,
                delaySeconds: event.delaySeconds,
                message: event.message,
              },
            }
          case 'tool.update': {
            if (message.final && message.status !== 'streaming' && message.status !== 'retrying') {
              return message
            }
            const resumeAfterRetry = message.status === 'retrying'
            const toolSteps = resumeAfterRetry ? [] : (message.tool_steps ?? [])
            const index = toolSteps.findIndex((step) => step.id === event.tool.id)
            const next =
              index < 0 ? [...toolSteps, event.tool] : toolSteps.map((step, stepIndex) => (stepIndex === index ? event.tool : step))
            return {
              ...message,
              // New attempt after retry — drop previous partial answer/tools.
              content: resumeAfterRetry ? '' : message.content,
              reasoning: resumeAfterRetry ? null : message.reasoning,
              thought_chain: resumeAfterRetry ? [] : message.thought_chain,
              tool_steps: next,
              status: 'streaming',
              retry: null,
              error: null,
            }
          }
          case 'reasoning.delta': {
            if (message.final && message.status !== 'streaming' && message.status !== 'retrying') {
              return message
            }
            const resumeAfterRetry = message.status === 'retrying'
            return {
              ...message,
              content: resumeAfterRetry ? '' : message.content,
              reasoning: resumeAfterRetry ? event.delta : (message.reasoning ?? '') + event.delta,
              tool_steps: resumeAfterRetry ? [] : message.tool_steps,
              thought_chain: resumeAfterRetry ? [] : message.thought_chain,
              status: 'streaming',
              retry: null,
              error: null,
            }
          }
          case 'thought.update': {
            if (message.final && message.status !== 'streaming' && message.status !== 'retrying') {
              return message
            }
            const resumeAfterRetry = message.status === 'retrying'
            const thoughts = resumeAfterRetry ? [] : (message.thought_chain ?? [])
            const index = thoughts.findIndex((step) => step.id === event.thought.id)
            return {
              ...message,
              content: resumeAfterRetry ? '' : message.content,
              reasoning: resumeAfterRetry ? null : message.reasoning,
              tool_steps: resumeAfterRetry ? [] : message.tool_steps,
              thought_chain:
                index < 0 ? [...thoughts, event.thought] : thoughts.map((step, stepIndex) => (stepIndex === index ? event.thought : step)),
              status: 'streaming',
              retry: null,
              error: null,
            }
          }
          case 'sources': {
            if (message.final && message.status !== 'streaming' && message.status !== 'retrying') {
              return message
            }
            const resumeAfterRetry = message.status === 'retrying'
            // Team members may each emit sources; merge by id/url/title instead of replace.
            const prevSources = resumeAfterRetry ? [] : (message.sources ?? [])
            const merged = [...prevSources]
            const seen = new Set(
              prevSources.map((s) => s.id || s.url || s.title).filter(Boolean) as string[],
            )
            for (const item of event.items ?? []) {
              const key = item.id || item.url || item.title
              if (key && seen.has(key)) continue
              if (key) seen.add(key)
              merged.push(item)
            }
            return {
              ...message,
              content: resumeAfterRetry ? '' : message.content,
              reasoning: resumeAfterRetry ? null : message.reasoning,
              tool_steps: resumeAfterRetry ? [] : message.tool_steps,
              thought_chain: resumeAfterRetry ? [] : message.thought_chain,
              sources: merged,
              status: 'streaming',
              retry: null,
              error: null,
            }
          }
          case 'run.paused': {
            const toolSteps = message.tool_steps ?? []
            const tool = event.tool
            const index = tool ? toolSteps.findIndex((step) => step.id === tool.id) : -1
            return {
              ...message,
              run_id: event.runId,
              session_id: event.sessionId ?? message.session_id,
              approval_id: event.approvalId,
              status: 'paused',
              final: true,
              retry: null,
              error: null,
              tool_steps: tool ? (index < 0 ? [...toolSteps, tool] : toolSteps.map((step, stepIndex) => (stepIndex === index ? tool : step))) : toolSteps,
            }
          }
          case 'run.continued':
            return {
              ...message,
              run_id: event.runId,
              session_id: event.sessionId ?? message.session_id,
              // Leave HITL pause state fully; keep approval link off resumed stream.
              approval_id: null,
              status: 'streaming',
              final: false,
              retry: null,
              error: null,
            }
          case 'run.completed': {
            // Team/Agent streams can leave member thoughts/tools in loading if a
            // terminal event is skipped; close them when the run completes.
            const thoughts = (message.thought_chain ?? []).map((step) =>
              step.status === 'loading' ? { ...step, status: 'success' as const } : step,
            )
            const tools = (message.tool_steps ?? []).map((step) =>
              step.status === 'loading' ? { ...step, status: 'success' as const } : step,
            )
            const completedContent =
              typeof event.content === 'string' && event.content.trim()
                ? event.content
                : message.content
            return {
              ...message,
              run_id: event.runId ?? message.run_id,
              session_id: event.sessionId ?? message.session_id,
              metrics: event.metrics ?? message.metrics,
              followups: event.followups ?? [],
              content: completedContent || message.content,
              thought_chain: thoughts.length ? thoughts : message.thought_chain,
              tool_steps: tools.length ? tools : message.tool_steps,
              approval_id: null,
              status: 'completed',
              final: true,
              retry: null,
            }
          }
          case 'run.cancelled':
            return {
              ...message,
              run_id: event.runId ?? message.run_id,
              approval_id: null,
              status: 'cancelled',
              final: true,
              retry: null,
              error: event.reason ? { message: event.reason } : null,
              tool_steps: (message.tool_steps ?? []).map((step) =>
                step.status === 'loading' ? { ...step, status: 'abort' as const } : step,
              ),
              thought_chain: (message.thought_chain ?? []).map((step) =>
                step.status === 'loading' ? { ...step, status: 'abort' as const } : step,
              ),
            }
          case 'run.failed':
            return {
              ...message,
              run_id: event.runId ?? message.run_id,
              approval_id: null,
              status: 'failed',
              final: true,
              retry: null,
              error: { code: event.code, message: event.message, retryable: event.retryable },
              tool_steps: (message.tool_steps ?? []).map((step) =>
                step.status === 'loading' ? { ...step, status: 'error' as const } : step,
              ),
              thought_chain: (message.thought_chain ?? []).map((step) =>
                step.status === 'loading' ? { ...step, status: 'error' as const } : step,
              ),
            }
        }
      })
      return {
        ...state,
        requesting: terminal ? false : state.requesting,
        error: event.type === 'run.failed' ? event.message : state.error,
        messages,
      }
    }
    case 'network-error':
      return {
        ...state,
        requesting: false,
        error: action.message,
        messages: updateMessage(state.messages, action.id, (message) => ({
          ...message,
          final: true,
          status: 'failed',
          retry: null,
          error: { message: action.message, retryable: true },
        })),
      }
    case 'soft-error':
      return {
        ...state,
        error: action.message,
      }
    case 'clear-error':
      return {
        ...state,
        error: null,
      }
    case 'session-switch':
      // Drop in-flight stream UI so history can replace messages for the new session.
      return {
        ...state,
        messages: [],
        requesting: false,
        error: null,
      }
    case 'reset':
      return { ...state, messages: [], input: '', requesting: false, error: null, reasoningEffort: null }
  }
}

const normalizeToolStatus = (value: unknown): ToolStatus => {
  const status = typeof value === 'string' ? value.trim().toLowerCase() : ''
  if (status === 'completed' || status === 'success') return 'success'
  if (status === 'error' || status === 'failed') return 'error'
  if (status === 'abort' || status === 'cancelled' || status === 'canceled') return 'abort'
  return 'loading'
}
const normalizeSources = (value: unknown): ChatSource[] =>
  Array.isArray(value)
    ? value.flatMap((source, index) => {
        if (typeof source === 'string') return [{ id: String(index), title: source }]
        if (!isRecord(source)) return []
        const title = asString(source.title) ?? asString(source.name) ?? asString(source.url)
        return title
          ? [
              {
                id: asString(source.id) ?? String(index),
                title,
                url: asString(source.url),
                snippet: asString(source.snippet) ?? asString(source.description),
              },
            ]
          : []
      })
    : []
const normalizeTools = (value: unknown): ToolStep[] =>
  Array.isArray(value)
    ? value.flatMap((tool, index) => {
        if (!isRecord(tool)) return []
        const name = asString(tool.name) ?? asString(tool.title)
        return name
          ? [
              {
                id: asString(tool.id) ?? String(index),
                name,
                status: normalizeToolStatus(tool.status),
                summary: asString(tool.summary),
                duration: typeof tool.duration === 'number' ? tool.duration : null,
                input: tool.input,
                output: tool.output,
                member_id: asString(tool.member_id) ?? null,
                member_name: asString(tool.member_name) ?? null,
              },
            ]
          : []
      })
    : []
const normalizeThoughts = (value: unknown): ThoughtStep[] =>
  Array.isArray(value)
    ? value.flatMap((thought, index) => {
        if (!isRecord(thought)) return []
        const title = asString(thought.title) ?? asString(thought.name)
        return title
          ? [
              {
                id: asString(thought.id) ?? String(index),
                title,
                status: normalizeToolStatus(thought.status),
                summary: asString(thought.summary),
                duration: typeof thought.duration === 'number' ? thought.duration : null,
              },
            ]
          : []
      })
    : []

const normalizeRunStatus = (value: unknown): RunStatus => {
  const status = typeof value === 'string' ? value.trim().toLowerCase() : ''
  if (status === 'streaming' || status === 'running' || status === 'started') return 'streaming'
  if (status === 'paused' || status === 'pending') return 'paused'
  if (status === 'cancelled' || status === 'canceled') return 'cancelled'
  if (status === 'failed' || status === 'error') return 'failed'
  return 'completed'
}

export const normalizeMessages = (value: unknown): Message[] =>
  Array.isArray(value)
    ? value.map((item, index) => {
        const source = isRecord(item) ? item : {}
        const status = normalizeRunStatus(source.status)
        return {
          id: String(source.id ?? source.message_id ?? source.run_id ?? `${source.role ?? 'message'}-${index}`),
          role: source.role === 'user' || source.role === 'system' ? source.role : 'assistant',
          content: typeof source.content === 'string' ? source.content : JSON.stringify(source.content ?? ''),
          attachments: Array.isArray(source.attachments)
            ? source.attachments
                .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
                .map((item) => ({
                  name: String(item.name ?? item.filename ?? 'file'),
                  mime: item.mime != null ? String(item.mime) : item.mime_type != null ? String(item.mime_type) : undefined,
                  kind: item.kind != null ? String(item.kind) : undefined,
                }))
            : undefined,
          final: status !== 'streaming',
          status,
          run_id: asString(source.run_id),
          session_id: asString(source.session_id),
          approval_id: asString(source.approval_id),
          metrics: asMetrics(source.metrics),
          sources: normalizeSources(source.sources ?? source.citations ?? source.references),
          tool_steps: normalizeTools(source.tool_steps ?? source.tools),
          thought_chain: normalizeThoughts(source.thought_chain ?? source.timeline),
          reasoning: asString(source.reasoning),
          followups: Array.isArray(source.followups)
            ? source.followups.filter((followup): followup is string => typeof followup === 'string')
            : [],
          leanMode: typeof source.lean_mode === 'boolean' ? source.lean_mode : undefined,
          enableTools: typeof source.enable_tools === 'boolean' ? source.enable_tools : undefined,
          searchKnowledge: typeof source.search_knowledge === 'boolean' ? source.search_knowledge : undefined,
          skillNames: Array.isArray(source.skill_names)
            ? source.skill_names.filter((item): item is string => typeof item === 'string')
            : source.skill_names === null
              ? null
              : undefined,
        }
      })
    : []

export interface SseEvent {
  event: string
  data: string
}
export const consumeSse = async (
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: SseEvent) => void,
  signal?: AbortSignal,
) => {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  const flush = (block: string) => {
    const lines = block.replace(/\r/g, '').split('\n')
    const event =
      lines
        .find((line) => line.startsWith('event:'))
        ?.slice(6)
        .trim() ?? 'message'
    const data = lines
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).replace(/^ /, ''))
      .join('\n')
    if (data) onEvent({ event, data })
  }
  const onAbort = () => {
    void reader.cancel().catch(() => undefined)
  }
  if (signal) {
    if (signal.aborted) {
      onAbort()
      throw new DOMException('The operation was aborted.', 'AbortError')
    }
    signal.addEventListener('abort', onAbort, { once: true })
  }
  try {
    while (true) {
      if (signal?.aborted) {
        throw new DOMException('The operation was aborted.', 'AbortError')
      }
      const { value, done } = await reader.read()
      // reader.cancel() on abort often resolves read() with done=true; still treat as abort.
      if (signal?.aborted) {
        throw new DOMException('The operation was aborted.', 'AbortError')
      }
      buffer += decoder.decode(value, { stream: !done })
      const blocks = buffer.split(/\n\n|\r\n\r\n/)
      buffer = blocks.pop() ?? ''
      blocks.forEach(flush)
      if (done) break
    }
    if (signal?.aborted) {
      throw new DOMException('The operation was aborted.', 'AbortError')
    }
    if (buffer.trim()) flush(buffer)
  } finally {
    if (signal) signal.removeEventListener('abort', onAbort)
  }
}

export const previousPrompt = (messages: Message[], assistantId: string) => {
  const index = messages.findIndex((message) => message.id === assistantId)
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) if (messages[cursor]?.role === 'user') return messages[cursor]?.content ?? ''
  return ''
}

export const supportedReasoningEfforts = (model: ModelConfig | null): ReasoningEffort[] => {
  if (!model) return []
  if (model.capabilities) {
    return model.capabilities.supports_reasoning_effort
      ? (model.capabilities.reasoning_efforts as ReasoningEffort[])
      : []
  }
  if (model.provider === 'openai-compatible' || model.provider === 'xai') return []
  if (model.provider === 'deepseek') return DEEPSEEK_REASONING_EFFORTS
  return openaiReasoningEfforts(model.api_protocol)
}

export const defaultReasoningEffort = (model: ModelConfig | null): ReasoningEffort | null => {
  const available = supportedReasoningEfforts(model)
  if (!available.length) return null
  const configured = model?.default_reasoning_effort
  if (configured && available.includes(configured)) return configured
  const optimal = model?.capabilities?.optimal_reasoning_effort
  if (optimal && available.includes(optimal)) return optimal
  const fallback = model?.capabilities?.fallback_reasoning_effort
  if (fallback && available.includes(fallback)) return fallback
  return available.at(-1) ?? null
}

/** Tools are on and the latest assistant turn reported auto-lite (no skills). */
/** Build user-facing retry progress (attempt/max + optional delay). */
export const formatRetryDetail = (
  retry: { attempt: number; maxAttempts: number; delaySeconds?: number; message?: string } | null | undefined,
  t: (key: string, options?: Record<string, unknown>) => string,
): string => {
  if (!retry) return t('establishingRun')
  const delay = retry.delaySeconds
  const hasDelay = typeof delay === 'number' && Number.isFinite(delay) && delay > 0
  const base = hasDelay
    ? t('retryingDetailWithDelay', {
        attempt: retry.attempt,
        max: retry.maxAttempts,
        seconds: Math.max(1, Math.round(delay)),
      })
    : t('retryingDetail', { attempt: retry.attempt, max: retry.maxAttempts })
  const provider = (retry.message || '').trim()
  if (!provider) return base
  // Keep banner short; full text stays in run strip tooltip via raw message if needed.
  const short = provider.length > 120 ? `${provider.slice(0, 117)}…` : provider
  return `${base} (${short})`
}

export const isLastTurnAutoLean = (
  enableTools: boolean,
  latestAssistant?: Pick<Message, 'enableTools' | 'leanMode'> | null,
): boolean =>
  Boolean(enableTools && latestAssistant?.enableTools !== false && latestAssistant?.leanMode)

export const isKnowledgeToggleActive = (
  searchKnowledge: boolean,
  enableTools: boolean,
): boolean => Boolean(searchKnowledge && enableTools)

export const isLiveSearchToggleActive = (
  liveSearch: boolean,
  enableTools: boolean,
  liveSearchSupported: boolean,
): boolean => Boolean(liveSearch && enableTools && liveSearchSupported)

