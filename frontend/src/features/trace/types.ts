import type { ListPaginationMeta } from '@/shared/lib/pagination'
import type { JsonRecord } from '@/shared/types/common'
export interface Trace {
  trace_id: string
  name: string
  status: string
  /** Agno-native human-readable duration (e.g. "1.23s", "150ms"). */
  duration: string
  /** Root span input preview when available. */
  input?: string | null
  start_time: string
  end_time: string
  total_spans?: number
  error_count?: number
  run_id?: string | null
  session_id?: string | null
  user_id?: string | null
  agent_id?: string | null
  team_id?: string | null
  workflow_id?: string | null
}
export interface Span {
  session_id?: string | null
  run_id?: string | null
  span_id: string
  parent_span_id?: string | null
  name: string
  status_code: string
  /** Agno-native human-readable duration (e.g. "1.23s", "150ms"). */
  duration: string
  start_time: string
  parsed?: JsonRecord
  attributes?: JsonRecord
  events?: unknown[]
}
/** UI-facing list meta after client normalization (Agno-style). */
export type TraceListMeta = ListPaginationMeta

/** UI-facing list shape after client normalization. */
export type TraceList = {
  data: Trace[]
  meta: TraceListMeta
}

/** Wire shape for GET /api/traces (Agno-native envelope). */
export type TraceListNative = TraceList

export interface TraceFilters {
  session_id: string
  run_id: string
  user_id: string
  status: string
  start_time: string
  end_time: string
}
export interface TraceUrlState {
  filters: TraceFilters
  selectedSession: string
  traceId: string
}
export interface TraceSessionSummary {
  session_id: string
  name: string
  latest_start_time: string
  trace_count: number
  run_count: number
  error_count: number
  status: string
  user_id?: string | null
  agent_id?: string | null
  team_id?: string | null
  workflow_id?: string | null
}
/** UI-facing session list after client normalization. */
export type TraceSessionList = {
  data: TraceSessionSummary[]
  meta: TraceListMeta
}

/** Wire shape for GET /api/traces/sessions. */
export type TraceSessionListNative = TraceSessionList

export interface SpanTreeNode {
  span: Span
  children: SpanTreeNode[]
}
export interface TraceDetail {
  trace: Trace
  spans: Span[]
  tree: SpanTreeNode[]
}
export interface TraceSession {
  sessionId: string
  name: string
  context: string
  archived: boolean
  traces: Trace[]
  runCount: number
  latestAt: string
  workflowId?: string | null
}
export interface TraceRun {
  runId: string
  traceId: string
  name: string
  status: string
  duration: string
  startTime: string
  traces: Trace[]
}
