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
  const envelope = asRecord(payload)
  const meta = asRecord(envelope.meta)
  const rows = Array.isArray(envelope.data) ? envelope.data : []
  const data = rows.map((row) => mapItem(row)).filter((row): row is T => row != null)
  const page = Number(meta.page ?? 1) || 1
  const limit = Number(meta.limit ?? 20) || 20
  const totalCount = Number(meta.total_count ?? data.length) || 0
  return {
    data,
    meta: {
      page,
      limit,
      total_count: totalCount,
      total_pages: Number(meta.total_pages ?? (totalCount ? Math.ceil(totalCount / Math.max(limit, 1)) : 0)) || 0,
      search_time_ms: meta.search_time_ms != null ? Number(meta.search_time_ms) || 0 : undefined,
      truncated: Boolean(meta.truncated),
      scanned_count: meta.scanned_count != null ? Number(meta.scanned_count) || 0 : undefined,
    },
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

/** Single-page Agno sessions list (server-side page/limit; no client multi-page walk). */
export const listTraceSessions = async (params: TraceParams): Promise<TraceSessionList> => {
  const raw = await requestJson<TraceSessionListNative>(`/traces/sessions?${traceSearch(params)}`)
  return normalizePaginated(raw, normalizeSession)
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
