import { watch, type ComputedRef, type Ref } from "vue"
import {
  clampTraceSessionPage,
  type TraceRunFilters,
  type TraceSessionFilters,
} from "../modules/traceWorkbench"
import type { ChatSession } from "../types"

interface UseTraceFilterWatchesParams {
  filteredSessions: ComputedRef<ChatSession[]>
  sessionPage: Ref<number>
  sessionFilters: TraceSessionFilters
  runFilters: TraceRunFilters
  sessionPageSize: number
  scheduleSessionFilterRefresh: () => void
  scheduleFilterRefresh: () => void
}

export const useTraceFilterWatches = ({
  filteredSessions,
  sessionPage,
  sessionFilters,
  runFilters,
  sessionPageSize,
  scheduleSessionFilterRefresh,
  scheduleFilterRefresh,
}: UseTraceFilterWatchesParams) => {
  watch(
    () => filteredSessions.value.length,
    (count) => {
      sessionPage.value = clampTraceSessionPage(sessionPage.value, count, sessionPageSize)
    },
  )

  watch(
    () => [sessionFilters.sessionId, sessionFilters.userId, sessionFilters.keyword, sessionFilters.status],
    () => {
      sessionPage.value = 1
      scheduleSessionFilterRefresh()
    },
  )

  watch(
    () => [runFilters.runId, runFilters.agentId, runFilters.teamId, runFilters.workflowId, runFilters.status],
    () => {
      scheduleFilterRefresh()
    },
  )
}
