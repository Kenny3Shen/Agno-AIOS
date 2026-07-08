import type { ComputedRef } from "vue"

interface UseTraceFilterRefreshSchedulerParams {
  selectedSession: ComputedRef<unknown | null>
  refresh: () => Promise<void>
  refreshRuns: () => Promise<void>
}

export const useTraceFilterRefreshScheduler = ({
  selectedSession,
  refresh,
  refreshRuns,
}: UseTraceFilterRefreshSchedulerParams) => {
  let filterRefreshTimer: ReturnType<typeof window.setTimeout> | null = null

  const clearPendingFilterRefresh = () => {
    if (filterRefreshTimer !== null) {
      window.clearTimeout(filterRefreshTimer)
      filterRefreshTimer = null
    }
  }

  const scheduleRefresh = (callback: () => Promise<void>) => {
    clearPendingFilterRefresh()
    filterRefreshTimer = window.setTimeout(() => {
      filterRefreshTimer = null
      void callback()
    }, 250)
  }

  const scheduleSessionFilterRefresh = () => {
    scheduleRefresh(refresh)
  }

  const scheduleRunFilterRefresh = () => {
    scheduleRefresh(refreshRuns)
  }

  const scheduleFilterRefresh = () => {
    if (selectedSession.value) {
      scheduleRunFilterRefresh()
    } else {
      scheduleSessionFilterRefresh()
    }
  }

  return {
    clearPendingFilterRefresh,
    scheduleSessionFilterRefresh,
    scheduleRunFilterRefresh,
    scheduleFilterRefresh,
  }
}
