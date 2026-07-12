import { describe, expect, it } from 'vitest'
import { failureRate, timelineChartData } from './utils'

describe('runtime overview chart helpers', () => {
  it('calculates error rate without dividing by zero', () => {
    expect(failureRate(2, 8)).toBe(25)
    expect(failureRate(1, 0)).toBe(0)
  })

  it('maps aggregate buckets into chart records', () => {
    expect(timelineChartData([{ timestamp: '2026-07-12T10:00:00Z', runs: 4, failed_runs: 1, p50_duration_ms: 8, p95_duration_ms: 20, input_tokens: 12, output_tokens: 8, total_tokens: 20 }])).toEqual([
      expect.objectContaining({ runs: 4, errorRate: 25, p95: 20, inputTokens: 12, outputTokens: 8, totalTokens: 20 }),
    ])
  })

  it('uses zero for token usage missing from an older overview response', () => {
    expect(timelineChartData([{ timestamp: '2026-07-12T10:00:00Z', runs: 1, failed_runs: 0, p50_duration_ms: 8, p95_duration_ms: 20 }])[0]).toMatchObject({ inputTokens: 0, outputTokens: 0, totalTokens: 0 })
  })
})
