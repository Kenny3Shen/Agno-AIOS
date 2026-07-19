import { requestJson } from '@/shared/api/client'
import { asRecord } from '@/shared/lib/format'
import { normalizePaginatedList } from '@/shared/lib/pagination'
import type {
  Span,
  SpanTreeNode,
  Trace,
  TraceDetail,
  TraceList,
  TraceSessionList,
  TraceSessionSummary,
} from './types'

type TraceParams = Record<string, string | number | undefined>

const traceSearch = (params: TraceParams) => {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') search.set(key, String(value))
  })
  return search
}

const canonicalDuration = (value: unknown): string | null => {
  if (typeof value !== 'string') return null
  const duration = value.trim()
  return duration || null
}

const isNonNegativeInteger = (value: unknown): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= 0

const nullableTraceSessionString = (value: unknown, context: string): string | null => {
  if (value == null) return null
  if (typeof value !== 'string') throw new Error(`${context}: invalid trace session payload`)
  return value
}

/** Parse a canonical list/detail trace row for UI. */
const parseTrace = (value: unknown, context: string): Trace => {
  const row = asRecord(value)
  const traceId = String(row.trace_id ?? '').trim()
  const duration = canonicalDuration(row.duration)
  if (!traceId || !duration) throw new Error(`${context}: invalid trace payload`)
  return {
    trace_id: traceId,
    name: String(row.name ?? ''),
    status: String(row.status ?? 'UNSET'),
    duration,
    input: row.input == null ? null : String(row.input),
    start_time: String(row.start_time ?? ''),
    end_time: String(row.end_time ?? ''),
    total_spans: row.total_spans != null ? Number(row.total_spans) : undefined,
    error_count: row.error_count != null ? Number(row.error_count) : undefined,
    run_id: row.run_id != null ? String(row.run_id) : null,
    session_id: row.session_id != null ? String(row.session_id) : null,
    user_id: row.user_id != null ? String(row.user_id) : null,
    agent_id: row.agent_id != null ? String(row.agent_id) : null,
    team_id: row.team_id != null ? String(row.team_id) : null,
    workflow_id: row.workflow_id != null ? String(row.workflow_id) : null,
  }
}

const parseSpan = (value: unknown, context: string): Span => {
  const row = asRecord(value)
  const spanId = String(row.span_id ?? '').trim()
  const duration = canonicalDuration(row.duration)
  if (!spanId || !duration) throw new Error(`${context}: invalid span payload`)
  return {
    session_id: row.session_id != null ? String(row.session_id) : null,
    run_id: row.run_id != null ? String(row.run_id) : null,
    span_id: spanId,
    parent_span_id: row.parent_span_id != null ? String(row.parent_span_id) : null,
    name: String(row.name ?? ''),
    status_code: String(row.status_code ?? 'UNSET'),
    duration,
    start_time: String(row.start_time ?? ''),
    parsed: row.parsed && typeof row.parsed === 'object' ? (row.parsed as Span['parsed']) : undefined,
    attributes: row.attributes && typeof row.attributes === 'object' ? (row.attributes as Span['attributes']) : undefined,
    events: Array.isArray(row.events) ? row.events : undefined,
  }
}

const normalizeTree = (nodes: unknown, context: string): SpanTreeNode[] => {
  if (!Array.isArray(nodes)) throw new Error(`${context}: invalid span tree payload`)
  return nodes.map((node) => {
    const row = asRecord(node)
    if (!Array.isArray(row.children)) throw new Error(`${context}: invalid span tree payload`)
    return {
      span: parseSpan(row.span, context),
      children: normalizeTree(row.children, context),
    }
  })
}

const parseTraceSession = (value: unknown, context: string): TraceSessionSummary => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${context}: invalid trace session payload`)
  }
  const row = value as Record<string, unknown>
  const sessionId = row.session_id
  const name = row.name
  const latestStartTime = row.latest_start_time
  const traceCount = row.trace_count
  const runCount = row.run_count
  const errorCount = row.error_count
  const status = row.status
  if (
    typeof sessionId !== 'string' ||
    !sessionId.trim() ||
    typeof name !== 'string' ||
    !name.trim() ||
    typeof latestStartTime !== 'string' ||
    !latestStartTime.trim() ||
    !isNonNegativeInteger(traceCount) ||
    traceCount < 1 ||
    !isNonNegativeInteger(runCount) ||
    !isNonNegativeInteger(errorCount) ||
    typeof status !== 'string' ||
    !status.trim()
  ) {
    throw new Error(`${context}: invalid trace session payload`)
  }
  return {
    session_id: sessionId,
    name,
    latest_start_time: latestStartTime,
    trace_count: traceCount,
    run_count: runCount,
    error_count: errorCount,
    status,
    user_id: nullableTraceSessionString(row.user_id, context),
    agent_id: nullableTraceSessionString(row.agent_id, context),
    team_id: nullableTraceSessionString(row.team_id, context),
    workflow_id: nullableTraceSessionString(row.workflow_id, context),
  }
}

export const listTraces = async (params: TraceParams): Promise<TraceList> => {
  const raw = await requestJson<unknown>(`/traces?${traceSearch(params)}`)
  return normalizePaginatedList(raw, { mapItem: (item) => parseTrace(item, 'listTraces'), extras: true })
}

/** Single-page Agno sessions list (server-side page/limit; no client multi-page walk). */
export const listTraceSessions = async (params: TraceParams): Promise<TraceSessionList> => {
  const raw = await requestJson<unknown>(`/traces/sessions?${traceSearch(params)}`)
  return normalizePaginatedList(raw, {
    mapItem: (item) => parseTraceSession(item, 'listTraceSessions'),
  })
}

export const getTrace = async (id: string): Promise<TraceDetail> => {
  const raw = asRecord(await requestJson<unknown>(`/traces/${encodeURIComponent(id)}`))
  const trace = parseTrace(raw.trace, 'getTrace')
  if (!Array.isArray(raw.spans)) throw new Error('getTrace: invalid spans payload')
  const spans = raw.spans.map((span) => parseSpan(span, 'getTrace'))
  return {
    trace,
    spans,
    tree: normalizeTree(raw.tree, 'getTrace'),
  }
}
