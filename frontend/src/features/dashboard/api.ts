import { requestJson } from '@/shared/api/client'
import type { OverviewQuery, RuntimeOverview } from './types'

export const dashboardKeys = {
  all: ['runtime-overview'] as const,
  detail: (query: OverviewQuery) => [...dashboardKeys.all, query] as const,
}

export const getRuntimeOverview = (query: OverviewQuery) => {
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone
  const search = new URLSearchParams()
  if (query.startTime && query.endTime) {
    search.set('range', 'custom')
    search.set('start_time', query.startTime)
    search.set('end_time', query.endTime)
  } else if (query.range) {
    search.set('range', query.range)
  }
  if (timezone) search.set('timezone', timezone)
  return requestJson<RuntimeOverview>(`/overview?${search}`)
}
