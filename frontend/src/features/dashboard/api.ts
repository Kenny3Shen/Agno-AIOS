import { requestJson } from '@/shared/api/client'
import type { OverviewRange, RuntimeOverview } from './types'

export const dashboardKeys = {
  all: ['runtime-overview'] as const,
  detail: (range: OverviewRange) => [...dashboardKeys.all, range] as const,
}

export const getRuntimeOverview = (range: OverviewRange) => {
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone
  const search = new URLSearchParams({ range })
  if (timezone) search.set('timezone', timezone)
  return requestJson<RuntimeOverview>(`/overview?${search}`)
}
