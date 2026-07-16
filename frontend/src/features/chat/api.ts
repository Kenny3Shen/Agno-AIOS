import { apiFetch, jsonInit, requestJson } from '@/shared/api/client'
import { normalizePaginatedList, type ListPaginationMeta } from '@/shared/lib/pagination'
import type { ModelConfigResponse, ReasoningEffort } from '@/shared/types/common'
import type { ChatRunEvent, ChatSession } from './types'
import { consumeSse, normalizeMessages } from './utils'

const normalizeSession = (value: unknown): ChatSession | null => {
  if (!value || typeof value !== 'object') return null
  const row = value as Record<string, unknown>
  const sessionId = String(row.session_id ?? '').trim()
  if (!sessionId) return null
  return {
    session_id: sessionId,
    user_id: row.user_id != null ? String(row.user_id) : null,
    preview: String(row.preview ?? '新对话'),
    title: row.title != null ? String(row.title) : null,
    created_at: Number(row.created_at ?? 0) || 0,
    updated_at: Number(row.updated_at ?? 0) || 0,
    archived: Boolean(row.archived),
    runs: Array.isArray(row.runs) ? (row.runs as ChatSession['runs']) : undefined,
  }
}

export type SessionListMeta = ListPaginationMeta

export type SessionListResult = {
  data: ChatSession[]
  meta: SessionListMeta
}

export type ListSessionsOptions = {
  includeArchived?: boolean
  /** When true, only archived sessions (server SQL filter). */
  archivedOnly?: boolean
  userId?: string
  page?: number
  limit?: number
}

/** Parse Agno-style ``{data, meta}`` chat session list. */
export const listSessions = async (options: ListSessionsOptions = {}): Promise<SessionListResult> => {
  const includeArchived = Boolean(options.includeArchived)
  const archivedOnly = Boolean(options.archivedOnly)
  const userId = options.userId
  const page = Math.max(1, Number(options.page ?? 1) || 1)
  const limit = Math.max(1, Number(options.limit ?? 40) || 40)
  const search = new URLSearchParams()
  if (archivedOnly) {
    search.set('archived_only', 'true')
  } else if (includeArchived) {
    search.set('include_archived', 'true')
  }
  if (userId) search.set('user_id', userId)
  search.set('page', String(page))
  search.set('limit', String(limit))
  const payload = await requestJson<unknown>(`/chat/sessions?${search.toString()}`)
  return normalizePaginatedList(payload, {
    page,
    limit,
    mapItem: normalizeSession,
  })
}
export const getHistory = async (sessionId: string) =>
  normalizeMessages(await requestJson<unknown>(`/chat/sessions/${encodeURIComponent(sessionId)}`))
export const archiveSession = (sessionId: string) =>
  requestJson<{ success: boolean }>(`/chat/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
export const renameSession = (sessionId: string, title: string) =>
  requestJson<ChatSession>(`/chat/sessions/${encodeURIComponent(sessionId)}`, jsonInit('PATCH', { title }))
export const getModels = () => requestJson<ModelConfigResponse>('/models')
export const cancelRun = (runId: string) =>
  requestJson<{ success?: boolean }>(`/chat/runs/${encodeURIComponent(runId)}/cancel`, jsonInit('POST'))

const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object'
const stringValue = (record: Record<string, unknown>, key: string) => (typeof record[key] === 'string' ? record[key] : undefined)
const parseEvent = (event: string, data: string): ChatRunEvent | null => {
  let value: unknown
  try {
    value = JSON.parse(data)
  } catch {
    return null
  }
  if (!isRecord(value)) return null
  const runId = stringValue(value, 'run_id')
  switch (event) {
    case 'run.started':
      return runId
        ? {
            type: event,
            runId,
            sessionId: stringValue(value, 'session_id'),
            model: stringValue(value, 'model'),
            provider: stringValue(value, 'provider'),
          }
        : null
    case 'content.delta':
      return typeof value.delta === 'string' ? { type: event, runId, delta: value.delta } : null
    case 'tool.update': {
      const tool = value.tool
      if (!isRecord(tool) || typeof tool.name !== 'string') return null
      return {
        type: event,
        runId,
        tool: {
          id: stringValue(tool, 'id') ?? tool.name,
          name: tool.name,
          status: tool.status === 'completed' || tool.status === 'success' ? 'success' : tool.status === 'error' ? 'error' : 'loading',
          summary: stringValue(tool, 'summary'),
          duration: typeof tool.duration === 'number' ? tool.duration : undefined,
          input: tool.input,
          output: tool.output,
        },
      }
    }
    case 'reasoning.delta':
      return typeof value.delta === 'string' ? { type: event, runId, delta: value.delta } : null
    case 'thought.update': {
      const thought = value.thought
      if (!isRecord(thought) || typeof thought.title !== 'string') return null
      return {
        type: event,
        runId,
        thought: {
          id: stringValue(thought, 'id') ?? thought.title,
          title: thought.title,
          status:
            thought.status === 'completed' || thought.status === 'success'
              ? 'success'
              : thought.status === 'error'
                ? 'error'
                : thought.status === 'abort'
                  ? 'abort'
                  : 'loading',
          summary: stringValue(thought, 'summary'),
          duration: typeof thought.duration === 'number' ? thought.duration : undefined,
        },
      }
    }
    case 'sources':
      return {
        type: event,
        runId,
        items: Array.isArray(value.items)
          ? value.items.flatMap((item, index) => {
              if (!isRecord(item) || typeof item.title !== 'string') return []
              return [
                {
                  id: stringValue(item, 'id') ?? String(index),
                  title: item.title,
                  url: stringValue(item, 'url'),
                  snippet: stringValue(item, 'snippet'),
                },
              ]
            })
          : [],
      }
    case 'run.paused': {
      const approvalId = stringValue(value, 'approval_id')
      const toolName = stringValue(value, 'tool_name')
      return runId && approvalId
        ? {
            type: event,
            runId,
            sessionId: stringValue(value, 'session_id'),
            approvalId,
            tool: toolName ? { id: toolName, name: toolName, status: 'loading' } : undefined,
          }
        : null
    }
    case 'run.continued':
      return runId ? { type: event, runId, sessionId: stringValue(value, 'session_id') } : null
    case 'run.completed':
      return {
        type: event,
        runId,
        sessionId: stringValue(value, 'session_id'),
        metrics: isRecord(value.metrics) ? value.metrics : null,
        followups: Array.isArray(value.followups) ? value.followups.filter((item): item is string => typeof item === 'string') : [],
      }
    case 'run.cancelled':
      return { type: event, runId, reason: stringValue(value, 'reason') }
    case 'run.failed':
      return typeof value.message === 'string'
        ? { type: event, runId, code: stringValue(value, 'code'), message: value.message, retryable: value.retryable === true }
        : null
    case 'run.retrying': {
      const attempt = typeof value.attempt === 'number' ? value.attempt : Number(value.attempt)
      const maxAttempts = typeof value.max_attempts === 'number' ? value.max_attempts : Number(value.max_attempts)
      if (!Number.isFinite(attempt) || !Number.isFinite(maxAttempts)) return null
      const delayRaw = value.delay_seconds
      const delaySeconds = typeof delayRaw === 'number' ? delayRaw : Number(delayRaw)
      return {
        type: event,
        runId,
        attempt,
        maxAttempts,
        delaySeconds: Number.isFinite(delaySeconds) ? delaySeconds : undefined,
        message: stringValue(value, 'message'),
      }
    }
    default:
      return null
  }
}

export const streamMessage = async (
  payload: { message: string; session_id: string; model_id: string | null; reasoning_effort?: ReasoningEffort; search_knowledge?: boolean; live_search?: boolean | null },
  onEvent: (event: ChatRunEvent) => void,
  signal: AbortSignal
) => {
  const response = await apiFetch('/chat', {
    ...jsonInit('POST', payload),
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    signal,
  })
  if (!response.ok || !response.body) throw new Error(`Chat request failed (${response.status})`)
  let terminal = false
  await consumeSse(response.body, ({ event, data }) => {
    const chatEvent = parseEvent(event, data)
    if (!chatEvent) return
    terminal ||=
      chatEvent.type === 'run.paused' ||
      chatEvent.type === 'run.completed' ||
      chatEvent.type === 'run.cancelled' ||
      chatEvent.type === 'run.failed'
    onEvent(chatEvent)
  })
  if (!terminal) throw new Error('Chat stream ended before a terminal event')
}

