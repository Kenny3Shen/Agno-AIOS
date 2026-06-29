import { describe, expect, it } from 'vitest'

import {
  buildTraceDateRange,
  buildTraceTimeline,
  summarizeConversationMessages,
} from './tracing-view.ts'
import type { TraceDetailResponse, WorkspaceMessage } from '#/lib/workspace.ts'

describe('tracing view helpers', () => {
  it('builds stable trace date ranges for presets', () => {
    expect(
      buildTraceDateRange({
        preset: '24h',
        now: new Date('2026-06-29T12:00:00.000Z'),
      }),
    ).toEqual({
      startTime: '2026-06-28T12:00:00.000Z',
      endTime: '2026-06-29T12:00:00.000Z',
      label: '最近 24 小时',
    })
  })

  it('normalizes custom trace date ranges to whole days', () => {
    const range = buildTraceDateRange({
      preset: 'custom',
      customStartDate: '2026-06-29',
      customEndDate: '2026-06-27',
    })

    expect(range.startTime).toBeDefined()
    expect(range.endTime).toBeDefined()
    expect(Date.parse(range.startTime ?? '')).toBeLessThan(
      Date.parse(range.endTime ?? ''),
    )
  })

  it('sorts spans by start time and maps them onto a relative timeline', () => {
    const detail: TraceDetailResponse = {
      trace: {
        trace_id: 'trace-1',
        name: 'Security run',
        status: 'OK',
        duration_ms: 1000,
        start_time: '2026-06-29T00:00:00.000Z',
        end_time: '2026-06-29T00:00:01.000Z',
      },
      spans: [
        {
          span_id: 'span-b',
          trace_id: 'trace-1',
          name: 'Draft answer',
          status_code: 'OK',
          duration_ms: 300,
          start_time: '2026-06-29T00:00:00.600Z',
          end_time: '2026-06-29T00:00:00.900Z',
        },
        {
          span_id: 'span-a',
          trace_id: 'trace-1',
          name: 'Retrieve context',
          status_code: 'OK',
          duration_ms: 200,
          start_time: '2026-06-29T00:00:00.100Z',
          end_time: '2026-06-29T00:00:00.300Z',
        },
      ],
      tree: [],
    }

    const timeline = buildTraceTimeline(detail)

    expect(timeline.map((item) => item.name)).toEqual([
      'Retrieve context',
      'Draft answer',
    ])
    expect(timeline[0]).toMatchObject({
      offsetPercent: 10,
      widthPercent: 20,
    })
    expect(timeline[1]).toMatchObject({
      offsetPercent: 60,
      widthPercent: 30,
    })
  })

  it('formats past conversation messages for trace context', () => {
    const messages: WorkspaceMessage[] = [
      {
        role: 'user',
        content: '帮我分析公网入口风险',
      },
      {
        role: 'assistant',
        content: '已结合资产画像和 CVE 情报生成排查建议。',
        final: true,
      },
    ]

    expect(summarizeConversationMessages(messages)).toEqual([
      {
        id: 'message-0',
        label: '用户',
        content: '帮我分析公网入口风险',
      },
      {
        id: 'message-1',
        label: '助手',
        content: '已结合资产画像和 CVE 情报生成排查建议。',
      },
    ])
  })
})
