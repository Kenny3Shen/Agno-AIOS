import type { OverviewBucket } from './types'

export const runtimeRanges = [
  { label: '1h', value: '1h' },
  { label: '24h', value: '24h' },
  { label: '7d', value: '7d' },
] as const

export interface TimelineChartPoint {
  time: string
  runs: number
  errors: number
  errorRate: number
  p50: number | null
  p95: number | null
  inputTokens: number
  outputTokens: number
  totalTokens: number
  bucketEnd?: string
}

function failureRate(errors: number, runs: number) {
  return runs > 0 ? Number(((errors / runs) * 100).toFixed(2)) : 0
}

export function timelineChartData(items: OverviewBucket[]): TimelineChartPoint[] {
  return items.map((item) => ({
    time: item.timestamp,
    runs: item.runs,
    errors: item.failed_runs,
    errorRate: failureRate(item.failed_runs, item.runs),
    p50: item.p50_duration_ms,
    p95: item.p95_duration_ms,
    inputTokens: item.input_tokens ?? 0,
    outputTokens: item.output_tokens ?? 0,
    totalTokens: item.total_tokens ?? 0,
    bucketEnd: item.bucket_end,
  }))
}
