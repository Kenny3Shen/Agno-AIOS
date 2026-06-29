import type {
  TraceDetailResponse,
  TraceStatus,
  WorkspaceMessage,
} from '#/lib/workspace.ts'

export type TraceTimelineEntry = {
  id: string
  name: string
  kind: string
  status: TraceStatus
  offsetPercent: number
  widthPercent: number
  durationMs: number
  startedAt: string
}

export type ConversationSummary = {
  id: string
  label: '用户' | '助手'
  content: string
}

export type TraceDatePreset = '24h' | '7d' | '30d' | 'custom'

export type TraceDateRange = {
  startTime?: string
  endTime?: string
  label: string
}

function toMillis(value: string) {
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function clampPercent(value: number) {
  return Math.min(100, Math.max(0, Math.round(value)))
}

function dateInputToLocalDate(value: string, endOfDay: boolean) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const date = new Date(
    `${value}T${endOfDay ? '23:59:59.999' : '00:00:00.000'}`,
  )
  return Number.isNaN(date.getTime()) ? null : date
}

function formatDateRangeLabel(startDate?: string, endDate?: string) {
  if (!startDate && !endDate) return '未限定时间'
  const start = startDate || '最早'
  const end = endDate || '现在'
  return `${start} 至 ${end}`
}

export function buildTraceDateRange({
  preset,
  customStartDate,
  customEndDate,
  now = new Date(),
}: {
  preset: TraceDatePreset
  customStartDate?: string
  customEndDate?: string
  now?: Date
}): TraceDateRange {
  if (preset === 'custom') {
    const startDate = customStartDate
      ? dateInputToLocalDate(customStartDate, false)
      : null
    const endDate = customEndDate
      ? dateInputToLocalDate(customEndDate, true)
      : null
    const startTime = startDate?.toISOString()
    const endTime = endDate?.toISOString()

    if (startDate && endDate && startDate.getTime() > endDate.getTime()) {
      return {
        startTime: endTime,
        endTime: startTime,
        label: formatDateRangeLabel(customEndDate, customStartDate),
      }
    }

    return {
      startTime,
      endTime,
      label: formatDateRangeLabel(customStartDate, customEndDate),
    }
  }

  const hoursByPreset: Record<Exclude<TraceDatePreset, 'custom'>, number> = {
    '24h': 24,
    '7d': 24 * 7,
    '30d': 24 * 30,
  }
  const endDate = new Date(now)
  const startDate = new Date(endDate)
  startDate.setHours(startDate.getHours() - hoursByPreset[preset])

  return {
    startTime: startDate.toISOString(),
    endTime: endDate.toISOString(),
    label:
      preset === '24h'
        ? '最近 24 小时'
        : preset === '7d'
          ? '最近 7 天'
          : '最近 30 天',
  }
}

export function buildTraceTimeline(
  detail: TraceDetailResponse | null,
): TraceTimelineEntry[] {
  if (!detail) return []

  const traceStart = toMillis(detail.trace.start_time)
  const traceEnd = Math.max(toMillis(detail.trace.end_time), traceStart + 1)
  const traceDuration = Math.max(traceEnd - traceStart, 1)

  return [...detail.spans]
    .sort(
      (left, right) => toMillis(left.start_time) - toMillis(right.start_time),
    )
    .map((span) => {
      const spanStart = toMillis(span.start_time)
      const spanEnd = Math.max(toMillis(span.end_time), spanStart)
      const durationMs = Math.max(span.duration_ms, spanEnd - spanStart, 0)

      return {
        id: span.span_id,
        name: span.name,
        kind: span.kind || 'span',
        status: span.status_code,
        offsetPercent: clampPercent(
          ((spanStart - traceStart) / traceDuration) * 100,
        ),
        widthPercent: Math.max(
          4,
          clampPercent((durationMs / traceDuration) * 100),
        ),
        durationMs,
        startedAt: span.start_time,
      }
    })
}

export function summarizeConversationMessages(
  messages: WorkspaceMessage[],
): ConversationSummary[] {
  return messages.map((message, index) => ({
    id: `message-${index}`,
    label: message.role === 'user' ? '用户' : '助手',
    content: message.content.trim() || '空消息',
  }))
}
