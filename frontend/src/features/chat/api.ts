import { apiFetch, jsonInit, requestJson } from '@/shared/api/client'
import type { ModelConfigResponse, ReasoningEffort } from '@/shared/types/common'
import type { ChatRunEvent, ChatSession, Message } from './types'
import { consumeSse, normalizeMessages } from './utils'

export const listSessions = async (includeArchived = false, userId?: string) => {
  const search = new URLSearchParams()
  if (includeArchived) search.set('include_archived', 'true')
  if (userId) search.set('user_id', userId)
  const value = await requestJson<unknown>(`/chat/sessions${search.size ? `?${search}` : ''}`)
  return Array.isArray(value) ? value as ChatSession[] : []
}
export const getHistory = async (sessionId: string) => normalizeMessages(await requestJson<unknown>(`/chat/sessions/${encodeURIComponent(sessionId)}`))
export const archiveSession = (sessionId: string) => requestJson<{ success: boolean }>(`/chat/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
export const renameSession = (sessionId: string, title: string) => requestJson<ChatSession>(`/chat/sessions/${encodeURIComponent(sessionId)}`, jsonInit('PATCH', { title }))
export const getModels = () => requestJson<ModelConfigResponse>('/models')
export const cancelRun = (runId: string) => requestJson<{ success?: boolean }>(`/chat/runs/${encodeURIComponent(runId)}/cancel`, jsonInit('POST'))

const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object'
const stringValue = (record: Record<string, unknown>, key: string) => typeof record[key] === 'string' ? record[key] : undefined
const parseEvent = (event: string, data: string): ChatRunEvent | null => {
  let value: unknown
  try { value = JSON.parse(data) } catch { return null }
  if (!isRecord(value)) return null
  const runId = stringValue(value, 'run_id')
  switch (event) {
    case 'run.started': return runId ? { type: event, runId, sessionId: stringValue(value, 'session_id'), model: stringValue(value, 'model'), provider: stringValue(value, 'provider') } : null
    case 'content.delta': return typeof value.delta === 'string' ? { type: event, runId, delta: value.delta } : null
    case 'tool.update': {
      const tool = value.tool
      if (!isRecord(tool) || typeof tool.name !== 'string') return null
      return { type: event, runId, tool: { id: stringValue(tool, 'id') ?? tool.name, name: tool.name, status: tool.status === 'completed' || tool.status === 'success' ? 'success' : tool.status === 'error' ? 'error' : 'loading', summary: stringValue(tool, 'summary'), duration: typeof tool.duration === 'number' ? tool.duration : undefined, input: tool.input, output: tool.output } }
    }
    case 'reasoning.delta': return typeof value.delta === 'string' ? { type: event, runId, delta: value.delta } : null
    case 'thought.update': {
      const thought = value.thought
      if (!isRecord(thought) || typeof thought.title !== 'string') return null
      return { type: event, runId, thought: { id: stringValue(thought, 'id') ?? thought.title, title: thought.title, status: thought.status === 'completed' || thought.status === 'success' ? 'success' : thought.status === 'error' ? 'error' : thought.status === 'abort' ? 'abort' : 'loading', summary: stringValue(thought, 'summary'), duration: typeof thought.duration === 'number' ? thought.duration : undefined } }
    }
    case 'sources': return { type: event, runId, items: Array.isArray(value.items) ? value.items.flatMap((item, index) => {
      if (!isRecord(item) || typeof item.title !== 'string') return []
      return [{ id: stringValue(item, 'id') ?? String(index), title: item.title, url: stringValue(item, 'url'), snippet: stringValue(item, 'snippet') }]
    }) : [] }
    case 'run.completed': return { type: event, runId, sessionId: stringValue(value, 'session_id'), metrics: isRecord(value.metrics) ? value.metrics : null, followups: Array.isArray(value.followups) ? value.followups.filter((item): item is string => typeof item === 'string') : [] }
    case 'run.cancelled': return { type: event, runId, reason: stringValue(value, 'reason') }
    case 'run.failed': return typeof value.message === 'string' ? { type: event, runId, code: stringValue(value, 'code'), message: value.message, retryable: value.retryable === true } : null
    default: return null
  }
}

export const streamMessage = async (
  payload: { message: string; session_id: string; model_id: string | null; reasoning_effort?: ReasoningEffort },
  onEvent: (event: ChatRunEvent) => void,
  signal: AbortSignal,
) => {
  const response = await apiFetch('/chat', { ...jsonInit('POST', payload), headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' }, signal })
  if (!response.ok || !response.body) throw new Error(`Chat request failed (${response.status})`)
  let terminal = false
  await consumeSse(response.body, ({ event, data }) => {
    const chatEvent = parseEvent(event, data)
    if (!chatEvent) return
    terminal ||= chatEvent.type === 'run.completed' || chatEvent.type === 'run.cancelled' || chatEvent.type === 'run.failed'
    onEvent(chatEvent)
  })
  if (!terminal) throw new Error('Chat stream ended before a terminal event')
}

export const mergeRunMetadata = (messages: Message[], history: Message[]) => messages.map((message) => {
  if (message.role !== 'assistant' || !message.content.trim()) return message
  const persisted = [...history].reverse().find((item) => item.role === 'assistant' && item.content.trim() === message.content.trim())
  return persisted ? { ...message, ...persisted, content: message.content, final: true } : message
})
