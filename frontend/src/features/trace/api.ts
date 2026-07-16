import { requestJson } from '@/shared/api/client'
import { asRecord } from '@/shared/lib/format'
import type {
  Span,
  SpanTreeNode,
  Trace,
  TraceDetail,
  TraceList,
  TraceListNative,
  TraceSessionList,
  TraceSessionListNative,
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

const asDuration = (value: unknown): string =>
  typeof value === 'string' && value.trim() ? value.trim() : '0ms'

/** Normalize a list/detail trace row for UI. */
export const normalizeTrace = (value: unknown): Trace | null => {
  const row = asRecord(value)
  const traceId = String(row.trace_id ?? '').trim()
  if (!traceId) return null
  return {
    trace_id: traceId,
    name: String(row.name ?? ''),
    status: String(row.status ?? 'UNSET'),
    duration: asDuration(row.duration),
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

export const normalizeSpan = (value: unknown): Span | null => {
  const row = asRecord(value)
  const spanId = String(row.span_id ?? '').trim()
  if (!spanId) return null
  return {
    session_id: row.session_id != null ? String(row.session_id) : null,
    run_id: row.run_id != null ? String(row.run_id) : null,
    span_id: spanId,
    parent_span_id: row.parent_span_id != null ? String(row.parent_span_id) : null,
    name: String(row.name ?? ''),
    status_code: String(row.status_code ?? row.status ?? 'UNSET'),
    duration: asDuration(row.duration),
    start_time: String(row.start_time ?? ''),
    parsed: row.parsed && typeof row.parsed === 'object' ? (row.parsed as Span['parsed']) : undefined,
    attributes: row.attributes && typeof row.attributes === 'object' ? (row.attributes as Span['attributes']) : undefined,
    events: Array.isArray(row.events) ? row.events : undefined,
  }
}

const normalizeTree = (nodes: unknown): SpanTreeNode[] => {
  if (!Array.isArray(nodes)) return []
  return nodes
    .map((node) => {
      const row = asRecord(node)
      const span = normalizeSpan(row.span ?? row)
      if (!span) return null
      return {
        span,
        children: normalizeTree(row.children ?? row.spans),
      }
    })
    .filter((node): node is SpanTreeNode => node != null)
}

const normalizePaginated = <T>(payload: unknown, mapItem: (row: unknown) => T | null) => {
  const data = asRecord(payload)
  const meta = asRecord(data.meta)
  const rows = Array.isArray(data.data) ? data.data : []
  const items = rows.map((row) => mapItem(row)).filter((row): row is T => row != null)
  return {
    items,
    total_count: Number(meta.total_count ?? items.length) || 0,
    page: Number(meta.page ?? 1) || 1,
    limit: Number(meta.limit ?? 20) || 20,
    total_pages: Number(meta.total_pages ?? 0) || 0,
    truncated: Boolean(meta.truncated),
    scanned_count: meta.scanned_count != null ? Number(meta.scanned_count) || 0 : undefined,
  }
}

const normalizeSession = (value: unknown): TraceSessionSummary | null => {
  const row = asRecord(value)
  const sessionId = String(row.session_id ?? '').trim()
  if (!sessionId) return null
  return {
    session_id: sessionId,
    name: String(row.name ?? sessionId),
    latest_start_time: String(row.latest_start_time ?? ''),
    trace_count: Number(row.trace_count ?? 0) || 0,
    run_count: Number(row.run_count ?? 0) || 0,
    error_count: Number(row.error_count ?? 0) || 0,
    status: String(row.status ?? 'UNSET'),
    user_id: row.user_id != null ? String(row.user_id) : null,
    agent_id: row.agent_id != null ? String(row.agent_id) : null,
    team_id: row.team_id != null ? String(row.team_id) : null,
    workflow_id: row.workflow_id != null ? String(row.workflow_id) : null,
  }
}

export const listTraces = async (params: TraceParams): Promise<TraceList> => {
  const raw = await requestJson<TraceListNative>(`/traces?${traceSearch(params)}`)
  return normalizePaginated(raw, normalizeTrace)
}

const listTraceSessionsPage = async (params: TraceParams): Promise<TraceSessionList> => {
  const raw = await requestJson<TraceSessionListNative>(`/traces/sessions?${traceSearch(params)}`)
  return normalizePaginated(raw, normalizeSession)
}

/** Hard cap client walk of /traces/sessions (200 × 5 = 1000 sessions). */
const MAX_TRACE_SESSION_PAGES = 5

export const listTraceSessions = async (params: TraceParams) => {
  const limit = 200
  let page = 1
  let totalCount = 0
  let truncated = false
  let scannedCount: number | undefined
  const items: TraceSessionSummary[] = []

  while (page <= MAX_TRACE_SESSION_PAGES) {
    const response = await listTraceSessionsPage({ ...params, page, limit })
    totalCount = response.total_count
    truncated = truncated || Boolean(response.truncated)
    if (response.scanned_count != null) scannedCount = response.scanned_count
    items.push(...response.items)
    if (items.length >= totalCount || response.items.length === 0) {
      break
    }
    if (page >= MAX_TRACE_SESSION_PAGES) {
      truncated = true
      break
    }
    page += 1
  }

  return {
    items,
    total_count: totalCount,
    page: 1,
    limit,
    total_pages: Math.ceil(totalCount / limit) || 0,
    truncated,
    scanned_count: scannedCount,
  }
}

export const getTrace = async (id: string): Promise<TraceDetail> => {
  const raw = asRecord(await requestJson<unknown>(`/traces/${encodeURIComponent(id)}`))
  const trace = normalizeTrace(raw.trace) ?? {
    trace_id: id,
    name: '',
    status: 'UNSET',
    duration: '0ms',
    start_time: '',
    end_time: '',
  }
  const spans = Array.isArray(raw.spans)
    ? raw.spans.map((span) => normalizeSpan(span)).filter((span): span is Span => span != null)
    : []
  return {
    trace,
    spans,
    tree: normalizeTree(raw.tree),
  }
}
