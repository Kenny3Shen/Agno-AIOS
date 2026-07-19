export type OverviewRange = '1h' | '24h' | '7d'
type OverviewResponseRange = OverviewRange | 'custom'

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

interface OverviewDimension {
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

interface OverviewAuditEvent {
  id: string | number
  action: string
  resource_type: string
  resource_id: string
  actor_email: string
  status: string
  created_at: string
}

interface OverviewKpis {
  total_runs: number
  failed_runs: number
  failure_rate: number
  p50_duration_ms: number | null
  p95_duration_ms: number | null
  input_tokens?: number | null
  output_tokens?: number | null
  total_tokens: number | null
  /** Rows used for metrics/series (capped sample). */
  sample_size?: number | null
  /** Agno window total before sample cap. */
  window_total?: number | null
  truncated?: boolean | null
  /** Failures observed inside the loaded sample (latency series). */
  sample_failed_runs?: number | null
}

interface OverviewEvaluation {
  total: number
  passed: number
  failed: number
  pass_rate: number | null
  /** Recent sample size used for passed/failed/pass_rate (total may be larger). */
  sample_size?: number | null
}

interface OverviewApprovalCounts {
  pending: number
  approved: number
  rejected: number
}

interface OverviewAssets {
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
