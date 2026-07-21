import type { ChatSession } from '@/features/chat'
import type { Trace, TraceFilters, TraceRun, TraceSession, TraceSessionSummary, TraceUrlState } from './types'

const timestamp = (value: string) => Date.parse(value) || 0

export type SessionArchiveFilter = 'all' | 'active' | 'archived'

export const emptyTraceFilters = (): TraceFilters => ({
  session_id: '',
  run_id: '',
  user_id: '',
  status: '',
  start_time: '',
  end_time: '',
})

export function parseTraceSearch(search: string | URLSearchParams): TraceUrlState {
  const params = typeof search === 'string' ? new URLSearchParams(search) : search
  const filters = {
    session_id: params.get('session_id') ?? '',
    run_id: params.get('run_id') ?? '',
    user_id: params.get('user_id') ?? '',
    status: params.get('status') ?? '',
    start_time: params.get('start_time') ?? '',
    end_time: params.get('end_time') ?? '',
  }
  return {
    filters,
    selectedSession: params.get('selected_session') ?? filters.session_id,
    traceId: params.get('trace') ?? '',
  }
}

export function buildTraceSearch(filters: TraceFilters, selectedSession = '', traceId = '') {
  const query = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value) query.set(key, value)
  })
  if (selectedSession) query.set('selected_session', selectedSession)
  if (traceId) query.set('trace', traceId)
  return query.toString()
}

export function filterSessionsByArchive(sessions: TraceSession[], filter: SessionArchiveFilter): TraceSession[] {
  if (filter === 'all') return sessions
  return sessions.filter((session) => (filter === 'archived' ? session.archived : !session.archived))
}

/** Agno engine labels like ``安全运营助手.arun`` are not useful as session titles. */
export function isTechnicalTraceSessionName(value: string | null | undefined): boolean {
  const text = String(value || '').trim()
  if (!text) return true
  const lower = text.toLowerCase()
  if (lower.endsWith('.arun') || lower.endsWith('.run')) return true
  if (lower.includes('.arun')) return true
  if (lower.includes('.run') && !text.includes(' ')) return true
  return false
}

export function humanizeTraceSessionName(
  name: string | null | undefined,
  fallbacks: Array<string | null | undefined> = [],
): string {
  const raw = String(name || '').trim()
  if (raw && !isTechnicalTraceSessionName(raw)) return raw
  for (const candidate of fallbacks) {
    const text = String(candidate || '').trim()
    if (text && !isTechnicalTraceSessionName(text)) return text
  }
  if (raw) {
    for (const suffix of ['.arun', '.run'] as const) {
      if (raw.toLowerCase().endsWith(suffix)) {
        const base = raw.slice(0, -suffix.length).trim()
        if (base) return base
      }
    }
    return raw
  }
  return ''
}

export function mergeTraceSessions(chatSessions: ChatSession[], summaries: TraceSessionSummary[]): TraceSession[] {
  const chatSessionById = new Map(chatSessions.map((session) => [session.session_id, session]))
  return summaries
    .map((summary) => {
      const chatSession = chatSessionById.get(summary.session_id)
      const name =
        chatSession?.title ||
        chatSession?.preview ||
        humanizeTraceSessionName(summary.name, [
          summary.workflow_id,
          summary.team_id,
          summary.agent_id,
          summary.session_id,
        ]) ||
        summary.session_id
      return {
        sessionId: summary.session_id,
        name,
        context: summary.workflow_id || summary.agent_id || summary.team_id || summary.user_id || chatSession?.user_id || '',
        archived: chatSession?.archived === true,
        traces: [],
        runCount: summary.run_count,
        latestAt: summary.latest_start_time,
        workflowId: summary.workflow_id || chatSession?.workflow_id || null,
      }
    })
    .sort((left, right) => timestamp(right.latestAt) - timestamp(left.latestAt))
}

export function previewSpanValue(value: unknown, limit = 120): string {
  if (value === undefined || value === null || value === '') return ''
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const wrapped = value as Record<string, unknown>
    if (typeof wrapped.text === 'string' && wrapped.text) return previewSpanValue(wrapped.text, limit)
    if (wrapped.data !== undefined && wrapped.data !== null) return previewSpanValue(wrapped.data, limit)
    const keys = Object.keys(wrapped)
    const messages = Array.isArray(wrapped.messages) ? wrapped.messages.length : 0
    return messages > 0 ? `JSON · ${messages} messages` : `JSON · ${keys.length} fields`
  }
  if (Array.isArray(value)) return `JSON · ${value.length} items`
  const text = String(value)
  if (text.trim().startsWith('{') || text.trim().startsWith('[')) {
    try {
      return previewSpanValue(JSON.parse(text), limit)
    } catch {
      // Keep malformed structured text as a shortened preview.
    }
  }
  return text.length <= limit ? text : `${text.slice(0, limit - 1)}…`
}

export function groupRuns(traces: Trace[], sessionId: string): TraceRun[] {
  return traces
    .filter((trace) => !sessionId || trace.session_id === sessionId)
    .map((trace) => {
      return {
        runId: trace.run_id || trace.trace_id,
        traceId: trace.trace_id,
        name: trace.name,
        status: trace.status,
        duration: trace.duration,
        startTime: trace.start_time,
        traces: [trace],
      }
    })
    .sort((left, right) => timestamp(right.startTime) - timestamp(left.startTime))
}
