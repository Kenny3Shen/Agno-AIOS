import type { SpanTreeNode, Trace, TraceRun, TraceSession } from './types'

const timestamp = (value: string) => Date.parse(value) || 0

export type SessionArchiveFilter = 'all' | 'active' | 'archived'

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
  const groups = new Map<string, Trace[]>()
  traces.forEach((trace) => {
    if (trace.session_id !== sessionId) return
    const runId = trace.run_id || trace.trace_id
    groups.set(runId, [...(groups.get(runId) ?? []), trace])
  })
  return [...groups.entries()].map(([runId, items]) => {
    const representative = [...items].sort((left, right) => (right.total_spans ?? 0) - (left.total_spans ?? 0) || right.duration_ms - left.duration_ms)[0]!
    return {
      runId,
      traceId: representative.trace_id,
      name: representative.name,
      status: items.some((trace) => trace.status === 'ERROR') ? 'ERROR' : representative.status,
      durationMs: Math.max(...items.map((trace) => trace.duration_ms)),
      startTime: representative.start_time,
      traces: items,
    }
  }).sort((left, right) => timestamp(right.startTime) - timestamp(left.startTime))
}
