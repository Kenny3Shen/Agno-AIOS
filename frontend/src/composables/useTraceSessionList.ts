import { computed, type Ref } from "vue"
import {
  filterTraceSessions,
  findTraceSession,
  pageTraceSessions,
  type TraceSessionFilters,
} from "../modules/traceWorkbench"
import type { ChatSession } from "../types"

interface UseTraceSessionListParams {
  sessions: Ref<ChatSession[]>
  sessionFilters: TraceSessionFilters
  selectedSessionId: Ref<string | null>
  sessionPage: Ref<number>
  sessionPageSize: number
}

export const useTraceSessionList = ({
  sessions,
  sessionFilters,
  selectedSessionId,
  sessionPage,
  sessionPageSize,
}: UseTraceSessionListParams) => {
  const filteredSessions = computed(() => filterTraceSessions(sessions.value, sessionFilters))

  const pagedSessions = computed(() => {
    return pageTraceSessions(filteredSessions.value, sessionPage.value, sessionPageSize)
  })

  const selectedSession = computed(() => findTraceSession(sessions.value, selectedSessionId.value))

  return {
    filteredSessions,
    pagedSessions,
    selectedSession,
  }
}
