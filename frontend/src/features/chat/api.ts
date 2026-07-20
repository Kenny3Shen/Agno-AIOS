import { ApiError, apiFetch, jsonInit, requestJson } from '@/shared/api/client'
import { normalizePaginatedList, type ListPaginationMeta } from '@/shared/lib/pagination'
import type { ModelConfigResponse, ReasoningEffort } from '@/shared/types/common'
import type { ChatRunEvent, ChatSession, TeamTaskState, TeamTaskStatus } from './types'
import { consumeSse, normalizeMessages } from './utils'

const SESSION_TYPES = new Set(['agent', 'team', 'workflow'])

const optionalId = (rawValue: unknown) => {
  const text = rawValue != null ? String(rawValue).trim() : ''
  return text || null
}

const parseSession = (value: unknown, context: string): ChatSession => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${context}: invalid session payload`)
  }
  const row = value as Record<string, unknown>
  const sessionId = String(row.session_id ?? '').trim()
  if (!sessionId) throw new Error(`${context}: invalid session payload`)
  const sessionType = row.session_type != null ? String(row.session_type).trim().toLowerCase() : ''
  if (!SESSION_TYPES.has(sessionType)) throw new Error(`${context}: invalid session payload`)
  const preview = typeof row.preview === 'string' ? row.preview.trim() : ''
  if (!preview) throw new Error(`${context}: invalid session payload`)
  const createdAt = Number(row.created_at)
  const updatedAt = Number(row.updated_at)
  if (!Number.isFinite(createdAt) || !Number.isFinite(updatedAt)) {
    throw new Error(`${context}: invalid session payload`)
  }
  return {
    session_id: sessionId,
    user_id: row.user_id != null ? String(row.user_id) : null,
    session_type: sessionType,
    workflow_id: optionalId(row.workflow_id),
    agent_id: optionalId(row.agent_id),
    team_id: optionalId(row.team_id),
    preview,
    title: row.title != null ? String(row.title) : null,
    created_at: createdAt,
    updated_at: updatedAt,
    archived: Boolean(row.archived),
    runs: Array.isArray(row.runs) ? (row.runs as ChatSession['runs']) : undefined,
  }
}

type SessionListMeta = ListPaginationMeta

export type SessionListResult = {
  data: ChatSession[]
  meta: SessionListMeta
}

type ListSessionsOptions = {
  includeArchived?: boolean
  /** When true, only archived sessions (server SQL filter). */
  archivedOnly?: boolean
  userId?: string
  page?: number
  limit?: number
  /** Match session_id or custom title (server-side). */
  q?: string
}

/** Parse Agno-style ``{data, meta}`` chat session list. */
export const listSessions = async (options: ListSessionsOptions = {}): Promise<SessionListResult> => {
  const includeArchived = Boolean(options.includeArchived)
  const archivedOnly = Boolean(options.archivedOnly)
  const userId = options.userId
  const page = Math.max(1, Number(options.page ?? 1) || 1)
  const limit = Math.max(1, Number(options.limit ?? 40) || 40)
  const q = (options.q ?? '').trim()
  const search = new URLSearchParams()
  if (archivedOnly) {
    search.set('archived_only', 'true')
  } else if (includeArchived) {
    search.set('include_archived', 'true')
  }
  if (userId) search.set('user_id', userId)
  if (q) search.set('q', q)
  search.set('page', String(page))
  search.set('limit', String(limit))
  const payload = await requestJson<unknown>(`/chat/sessions?${search.toString()}`)
  return normalizePaginatedList(payload, {
    mapItem: (item) => parseSession(item, 'listSessions'),
  })
}
export const getHistory = async (sessionId: string) =>
  normalizeMessages(await requestJson<unknown>(`/chat/sessions/${encodeURIComponent(sessionId)}`))
/** List-style projection for one session (deep links outside loaded recents). */
export const getSessionMeta = async (sessionId: string): Promise<ChatSession | null> => {
  try {
    const payload = await requestJson<unknown>(`/chat/sessions/${encodeURIComponent(sessionId)}/meta`)
    return parseSession(payload, 'getSessionMeta')
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}
export const archiveSession = (sessionId: string) =>
  requestJson<{ success: boolean }>(`/chat/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
export const unarchiveSession = (sessionId: string) =>
  requestJson<{ success: boolean; archived?: boolean }>(
    `/chat/sessions/${encodeURIComponent(sessionId)}/unarchive`,
    jsonInit('POST'),
  )
export const renameSession = (sessionId: string, title: string) =>
  requestJson<ChatSession>(`/chat/sessions/${encodeURIComponent(sessionId)}`, jsonInit('PATCH', { title }))
export const getModels = () => requestJson<ModelConfigResponse>('/models')

type ChatAgentCatalogItem = {
  id: string
  name: string
  role?: string
  description?: string
  category?: string
  capabilities?: string
  recommended_for?: string
  kind?: string
  /** Server hint: enable Live Search by default for this profile. */
  prefer_live_search?: boolean
  /** Team orchestration mode when kind=team. */
  mode?: string
  /** Team roster supplied by the server for a more informative selector. */
  members?: { id: string; name: string; role?: string }[]
}

type ChatAgentCatalogResponse = { data: ChatAgentCatalogItem[] }

export const getChatAgents = async (): Promise<ChatAgentCatalogItem[]> =>
  (await requestJson<ChatAgentCatalogResponse>('/chat/agents')).data

export const cancelRun = (runId: string) =>
  requestJson<{ success?: boolean }>(`/chat/runs/${encodeURIComponent(runId)}/cancel`, jsonInit('POST'))

const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object'
const stringValue = (record: Record<string, unknown>, key: string) => (typeof record[key] === 'string' ? record[key] : undefined)
const TEAM_TASK_STATUSES = new Set<TeamTaskStatus>([
  'pending',
  'in_progress',
  'completed',
  'failed',
  'blocked',
  'cancelled',
])

const isTeamTaskStatus = (value: string): value is TeamTaskStatus =>
  TEAM_TASK_STATUSES.has(value as TeamTaskStatus)

const taskText = (record: Record<string, unknown>, key: string, max: number) => {
  const value = stringValue(record, key)?.trim() ?? ''
  return value.slice(0, max)
}

const parseTeamTaskState = (value: Record<string, unknown>): TeamTaskState => {
  const rawTasks = Array.isArray(value.tasks) ? value.tasks : []
  const tasks: TeamTaskState['tasks'] = []
  for (const [index, raw] of rawTasks.entries()) {
    if (!isRecord(raw)) continue
    const rawStatus = taskText(raw, 'status', 32).toLowerCase().replaceAll('-', '_')
    const status = rawStatus === 'running' ? 'in_progress' : rawStatus
    const dependencies = Array.isArray(raw.dependencies)
      ? raw.dependencies
          .filter((item): item is string => typeof item === 'string')
          .map((item) => item.trim().slice(0, 120))
          .filter(Boolean)
          .slice(0, 12)
      : []
    tasks.push({
      id: taskText(raw, 'id', 120) || `task-${index + 1}`,
      title: taskText(raw, 'title', 240) || `Task ${index + 1}`,
      description: taskText(raw, 'description', 600) || undefined,
      status: isTeamTaskStatus(status) ? status : 'pending',
      assignee: taskText(raw, 'assignee', 120) || undefined,
      dependencies,
      result: taskText(raw, 'result', 1_000) || undefined,
    })
    if (tasks.length === 24) break
  }
  return {
    tasks,
    taskSummary: taskText(value, 'task_summary', 600) || undefined,
    goalComplete: value.goal_complete === true,
    completionSummary: taskText(value, 'completion_summary', 1_000) || undefined,
  }
}

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
            agentId: stringValue(value, 'agent_id'),
            enableTools: typeof value.enable_tools === 'boolean' ? value.enable_tools : undefined,
            leanMode: typeof value.lean_mode === 'boolean' ? value.lean_mode : undefined,
            searchKnowledge: typeof value.search_knowledge === 'boolean' ? value.search_knowledge : undefined,
            skillNames: Array.isArray(value.skill_names)
              ? value.skill_names.filter((item): item is string => typeof item === 'string')
              : value.skill_names === null
                ? null
                : undefined,
            mcpServerNames: Array.isArray(value.mcp_server_names)
              ? value.mcp_server_names.filter((item): item is string => typeof item === 'string')
              : undefined,
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
          status:
            tool.status === 'completed' || tool.status === 'success'
              ? 'success'
              : tool.status === 'error' || tool.status === 'failed'
                ? 'error'
                : tool.status === 'abort' || tool.status === 'cancelled' || tool.status === 'canceled'
                  ? 'abort'
                  : 'loading',
          summary: stringValue(tool, 'summary'),
          duration: typeof tool.duration === 'number' ? tool.duration : undefined,
          input: tool.input,
          output: tool.output,
          member_id: stringValue(tool, 'member_id'),
          member_name: stringValue(tool, 'member_name'),
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
              : thought.status === 'error' || thought.status === 'failed'
                ? 'error'
                : thought.status === 'abort' ||
                    thought.status === 'cancelled' ||
                    thought.status === 'canceled'
                  ? 'abort'
                  : 'loading',
          summary: stringValue(thought, 'summary'),
          duration: typeof thought.duration === 'number' ? thought.duration : undefined,
        },
      }
    }
    case 'team.tasks':
      return { type: event, runId, state: parseTeamTaskState(value) }
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
        content: stringValue(value, 'content'),
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

type StreamMessagePayload = {
  message: string
  session_id: string
  model_id: string | null
  agent_id?: string | null
  reasoning_effort?: ReasoningEffort
  search_knowledge?: boolean
  live_search?: boolean | null
  enable_tools?: boolean
  /** Browser File objects for Agno multipart upload (field name ``files``). */
  files?: File[]
}

export const streamMessage = async (
  payload: StreamMessagePayload,
  onEvent: (event: ChatRunEvent) => void,
  signal: AbortSignal
) => {
  const files = (payload.files ?? []).filter((file) => file instanceof File)
  let response: Response
  if (files.length > 0) {
    const form = new FormData()
    form.set('message', payload.message)
    form.set('session_id', payload.session_id)
    if (payload.model_id) form.set('model_id', payload.model_id)
    if (payload.reasoning_effort) form.set('reasoning_effort', payload.reasoning_effort)
    if (payload.search_knowledge != null) form.set('search_knowledge', String(payload.search_knowledge))
    if (payload.live_search != null) form.set('live_search', String(payload.live_search))
    if (payload.enable_tools != null) form.set('enable_tools', String(payload.enable_tools))
    if (payload.agent_id) form.set('agent_id', payload.agent_id)
    for (const file of files) form.append('files', file, file.name)
    response = await apiFetch('/chat', {
      method: 'POST',
      body: form,
      headers: { Accept: 'text/event-stream' },
      signal,
    })
  } else {
    const { files: _ignored, ...jsonPayload } = payload
    response = await apiFetch('/chat', {
      ...jsonInit('POST', jsonPayload),
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      signal,
    })
  }
  if (!response.ok || !response.body) {
    let detail = `Chat request failed (${response.status})`
    try {
      const errorPayload: unknown = await response.json()
      if (errorPayload && typeof errorPayload === 'object') {
        const record = errorPayload as Record<string, unknown>
        if (typeof record.detail === 'string' && record.detail.trim()) detail = record.detail
        else if (typeof record.message === 'string' && record.message.trim()) detail = record.message
      }
    } catch {
      // non-JSON error body
    }
    throw new Error(detail)
  }
  let terminal = false
  await consumeSse(
    response.body,
    ({ event, data }) => {
      const chatEvent = parseEvent(event, data)
      if (!chatEvent) return
      terminal ||=
        chatEvent.type === 'run.paused' ||
        chatEvent.type === 'run.completed' ||
        chatEvent.type === 'run.cancelled' ||
        chatEvent.type === 'run.failed'
      onEvent(chatEvent)
    },
    signal,
  )
  if (!terminal) throw new Error('Chat stream ended before a terminal event')
}
