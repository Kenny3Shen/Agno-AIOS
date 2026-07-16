export type OverviewRange = '1h' | '24h' | '7d'
export type OverviewResponseRange = OverviewRange | 'custom'

export interface OverviewQuery {
  range?: OverviewRange
  startTime?: string
  endTime?: string
}

export interface OverviewBucket {
  timestamp: string
  runs: number
  failed_runs: number
  p50_duration_ms: number | null
  p95_duration_ms: number | null
  input_tokens?: number | null
  output_tokens?: number | null
  total_tokens?: number | null
  bucket_end?: string
}

export interface OverviewDimension {
  name: string
  value: number
}

export interface OverviewTrace {
  trace_id: string
  name: string
  status: string
  duration_ms: number
  start_time: string
  session_id?: string | null
  run_id?: string | null
  agent_id?: string | null
  workflow_id?: string | null
}

export interface OverviewAuditEvent {
  id: string | number
  action: string
  resource_type: string
  resource_id: string
  actor_email: string
  status: string
  created_at: string
}

export interface OverviewKpis {
  total_runs: number
  failed_runs: number
  failure_rate: number
  p50_duration_ms: number | null
  p95_duration_ms: number | null
  input_tokens?: number | null
  output_tokens?: number | null
  total_tokens: number | null
}

export interface OverviewEvaluation {
  total: number
  passed: number
  failed: number
  pass_rate: number | null
  /** Recent sample size used for passed/failed/pass_rate (total may be larger). */
  sample_size?: number | null
}

export interface OverviewApprovalCounts {
  pending: number
  approved: number
  rejected: number
}

export interface OverviewAssets {
  approvals?: OverviewApprovalCounts | null
  knowledge_documents?: number | null
  memories?: number | null
  evaluation?: OverviewEvaluation | null
}

export interface RuntimeOverview {
  generated_at: string
  range: OverviewResponseRange
  start_time?: string
  end_time?: string
  health: { status: string; environment?: string }
  metrics: OverviewKpis
  series: OverviewBucket[]
  distributions: Record<string, OverviewDimension[]>
  recent_failures: OverviewTrace[]
  snapshots?: OverviewAssets | null
  audit?: { recent: OverviewAuditEvent[] } | null
}
