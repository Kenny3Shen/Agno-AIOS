import type { ChatSession } from '@/features/chat'
import type { SpanTreeNode, Trace, TraceFilters, TraceRun, TraceSession, TraceSessionSummary, TraceUrlState } from './types'

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
    session_id: params.get('session_id') ?? params.get('session') ?? '',
    run_id: params.get('run_id') ?? params.get('run') ?? '',
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
  Object.entries(filters).forEach(([key, value]) => { if (value) query.set(key, value) })
  if (selectedSession) query.set('selected_session', selectedSession)
  if (traceId) query.set('trace', traceId)
  return query.toString()
}

export function groupSessions(
  traces: Trace[],
  previews: Record<string, string> = {},
  archived: Record<string, boolean> = {},
  inferMissingArchived = false,
): TraceSession[] {
  const groups = new Map<string, Trace[]>()
  traces.forEach((trace) => {
    if (!trace.session_id) return
    groups.set(trace.session_id, [...(groups.get(trace.session_id) ?? []), trace])
  })
  return [...groups.entries()].map(([sessionId, items]) => {
    const latest = [...items].sort((left, right) => timestamp(right.start_time) - timestamp(left.start_time))[0]!
    return {
      sessionId,
      name: previews[sessionId] || latest.name || 'Session',
      context: latest.workflow_id || latest.agent_id || latest.team_id || latest.user_id || '',
      archived: archived[sessionId] === true || (inferMissingArchived && !(sessionId in archived)),
      traces: items,
      runCount: new Set(items.map((trace) => trace.run_id || trace.trace_id)).size,
      latestAt: latest.start_time,
    }
  }).sort((left, right) => timestamp(right.latestAt) - timestamp(left.latestAt))
}

export function filterSessionsByArchive(sessions: TraceSession[], filter: SessionArchiveFilter): TraceSession[] {
  if (filter === 'all') return sessions
  return sessions.filter((session) => filter === 'archived' ? session.archived : !session.archived)
}

export function mergeTraceSessions(chatSessions: ChatSession[], summaries: TraceSessionSummary[]): TraceSession[] {
  const chatSessionById = new Map(chatSessions.map((session) => [session.session_id, session]))
  return summaries.map((summary) => {
    const chatSession = chatSessionById.get(summary.session_id)
    return {
      sessionId: summary.session_id,
      name: chatSession?.title || chatSession?.preview || summary.name || 'Session',
      context: summary.workflow_id || summary.agent_id || summary.team_id || summary.user_id || chatSession?.user_id || '',
      archived: chatSession?.archived === true,
      traces: [],
      runCount: summary.run_count,
      latestAt: summary.latest_start_time,
    }
  }).sort((left, right) => timestamp(right.latestAt) - timestamp(left.latestAt))
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

export function firstSpanId(nodes: SpanTreeNode[]): string {
  return nodes[0]?.span.span_id ?? ''
}

export function groupRuns(traces: Trace[], sessionId: string): TraceRun[] {
  return traces.filter((trace) => !sessionId || trace.session_id === sessionId).map((trace) => {
    return {
      runId: trace.run_id || trace.trace_id,
      traceId: trace.trace_id,
      name: trace.name,
      status: trace.status,
      durationMs: trace.duration_ms,
      startTime: trace.start_time,
      traces: [trace],
    }
  }).sort((left, right) => timestamp(right.startTime) - timestamp(left.startTime))
}
