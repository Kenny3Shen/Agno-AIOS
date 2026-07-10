import type { JsonRecord } from '@/shared/types/common'
export interface Trace { trace_id: string; name: string; status: string; duration_ms: number; start_time: string; end_time: string; total_spans?: number; error_count?: number; run_id?: string | null; session_id?: string | null; user_id?: string | null; agent_id?: string | null; team_id?: string | null; workflow_id?: string | null }
export interface Span { span_id: string; parent_span_id?: string | null; name: string; status_code: string; duration_ms: number; start_time: string; parsed?: JsonRecord; attributes?: JsonRecord; events?: unknown[] }
export interface TraceList { items: Trace[]; total_count: number; page: number; limit: number }
export interface SpanTreeNode { span: Span; children: SpanTreeNode[] }
export interface TraceDetail { trace: Trace; spans: Span[]; tree: SpanTreeNode[] }
export interface TraceSession { sessionId: string; name: string; context: string; archived: boolean; traces: Trace[]; runCount: number; latestAt: string }
export interface TraceRun { runId: string; traceId: string; name: string; status: string; durationMs: number; startTime: string; traces: Trace[] }
