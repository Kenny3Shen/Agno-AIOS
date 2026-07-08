import { onMounted, onUnmounted } from "vue"

const TRACE_SELECT_EVENT = "agno-aios-trace-select"
const TRACE_SESSION_OPEN_EVENT = "agno-aios-trace-session-open"
const TRACE_SESSION_SELECT_EVENT = "agno-aios-trace-session-select"

interface UseTraceExternalSelectionEventsParams {
  openTraceDetail: (traceId: string | null | undefined) => Promise<void>
  selectSessionById: (
    sessionId: string,
    userId?: string | null,
    runId?: string | null,
  ) => Promise<void>
}

export const useTraceExternalSelectionEvents = ({
  openTraceDetail,
  selectSessionById,
}: UseTraceExternalSelectionEventsParams) => {
  const handleExternalTraceSelect = (event: Event) => {
    const detail = (event as CustomEvent<{ traceId?: string }>).detail
    void openTraceDetail(detail?.traceId)
  }

  const handleExternalSessionSelect = (event: Event) => {
    const detail = (event as CustomEvent<{ sessionId?: string; userId?: string | null; runId?: string | null }>).detail
    if (detail?.sessionId) void selectSessionById(detail.sessionId, detail.userId, detail.runId)
  }

  onMounted(() => {
    window.addEventListener(TRACE_SELECT_EVENT, handleExternalTraceSelect)
    window.addEventListener(TRACE_SESSION_OPEN_EVENT, handleExternalSessionSelect)
    window.addEventListener(TRACE_SESSION_SELECT_EVENT, handleExternalSessionSelect)
  })

  onUnmounted(() => {
    window.removeEventListener(TRACE_SELECT_EVENT, handleExternalTraceSelect)
    window.removeEventListener(TRACE_SESSION_OPEN_EVENT, handleExternalSessionSelect)
    window.removeEventListener(TRACE_SESSION_SELECT_EVENT, handleExternalSessionSelect)
  })
}
