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

export const initialChatState: ChatState = {
  messages: [],
  input: '',
  requesting: false,
  error: null,
  selectedModelId: localStorage.getItem('agno-aios-chat-model-id'),
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
      return { ...state, enableTools: action.value }
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
            return { ...message, run_id: event.runId, session_id: event.sessionId ?? message.session_id, status: 'streaming', retry: null, error: null, leanMode: event.leanMode, enableTools: event.enableTools, skillNames: event.skillNames }
          case 'content.delta':
            return {
              ...message,
              content: message.content + event.delta,
              status: 'streaming',
              retry: null,
              error: null,
            }
          case 'run.retrying':
            return {
              ...message,
              run_id: event.runId ?? message.run_id,
              content: '',
              reasoning: null,
              tool_steps: [],
              thought_chain: [],
              sources: null,
              metrics: null,
              followups: null,
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
            const toolSteps = message.tool_steps ?? []
            const index = toolSteps.findIndex((step) => step.id === event.tool.id)
            const next =
              index < 0 ? [...toolSteps, event.tool] : toolSteps.map((step, stepIndex) => (stepIndex === index ? event.tool : step))
            return { ...message, tool_steps: next, status: 'streaming' }
          }
          case 'reasoning.delta':
            return { ...message, reasoning: (message.reasoning ?? '') + event.delta, status: 'streaming' }
          case 'thought.update': {
            const thoughts = message.thought_chain ?? []
            const index = thoughts.findIndex((step) => step.id === event.thought.id)
            return {
              ...message,
              thought_chain:
                index < 0 ? [...thoughts, event.thought] : thoughts.map((step, stepIndex) => (stepIndex === index ? event.thought : step)),
              status: 'streaming',
            }
          }
          case 'sources':
            return { ...message, sources: event.items }
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
              tool_steps: tool ? (index < 0 ? [...toolSteps, tool] : toolSteps.map((step, stepIndex) => (stepIndex === index ? tool : step))) : toolSteps,
            }
          }
          case 'run.continued':
            return {
              ...message,
              run_id: event.runId,
              session_id: event.sessionId ?? message.session_id,
              status: 'streaming',
              final: false,
            }
          case 'run.completed':
            return {
              ...message,
              run_id: event.runId ?? message.run_id,
              session_id: event.sessionId ?? message.session_id,
              metrics: event.metrics ?? message.metrics,
              followups: event.followups ?? [],
              status: 'completed',
              final: true,
            }
          case 'run.cancelled':
            return {
              ...message,
              run_id: event.runId ?? message.run_id,
              status: 'cancelled',
              final: true,
              error: event.reason ? { message: event.reason } : null,
              tool_steps: (message.tool_steps ?? []).map((step) => (step.status === 'loading' ? { ...step, status: 'abort' } : step)),
            }
          case 'run.failed':
            return {
              ...message,
              run_id: event.runId ?? message.run_id,
              status: 'failed',
              final: true,
              error: { code: event.code, message: event.message, retryable: event.retryable },
              tool_steps: (message.tool_steps ?? []).map((step) => (step.status === 'loading' ? { ...step, status: 'error' } : step)),
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
    case 'reset':
      return { ...state, messages: [], input: '', requesting: false, error: null, reasoningEffort: null }
  }
}

const normalizeToolStatus = (value: unknown): ToolStatus =>
  value === 'completed' || value === 'success' ? 'success' : value === 'error' ? 'error' : value === 'abort' ? 'abort' : 'loading'
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
export const consumeSse = async (stream: ReadableStream<Uint8Array>, onEvent: (event: SseEvent) => void) => {
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
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const blocks = buffer.split(/\n\n|\r\n\r\n/)
    buffer = blocks.pop() ?? ''
    blocks.forEach(flush)
    if (done) break
  }
  if (buffer.trim()) flush(buffer)
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
