import type { ComputedRef, Ref } from "vue"
import {
  buildTraceListParams,
  buildTraceStoreFilters,
  buildChatRunFallbackDetail,
  createTraceRunFilters,
  createTraceSessionFilters,
  ensureTraceSession,
  findFirstTraceSpan,
  isChatRunFallbackTrace,
  mergeChatRunFallbackTraces,
  mergePreferredTraceItem,
  normalizeTraceSessionOpenRequest,
  resolveTraceSessionSelection,
  summarizeTraceItems,
  type TraceRunFilters,
  type TraceSessionFilters,
  type TraceSummaryState,
} from "../modules/traceWorkbench"
import type {
  ChatSession,
  ChatSessionRun,
  SpanItem,
  SpanTreeNode,
  TraceDetailResponse,
  TraceItem,
  TraceListResponse,
  TraceStatus,
} from "../types"

interface TraceListQuery {
  page?: number
  limit?: number
  status?: TraceStatus | ""
  session_id?: string
  run_id?: string
  agent_id?: string
  team_id?: string
  workflow_id?: string
  user_id?: string
  start_time?: string
  end_time?: string
}

interface TraceControllerStore {
  setCurrentTraceId: (traceId: string | null) => void
  setTraceFilters: (filters: ReturnType<typeof buildTraceStoreFilters>) => void
  setTraceItems: (items: TraceItem[]) => void
  resetTraceFilters: () => void
}

interface UseTraceSessionControllerParams {
  sessions: Ref<ChatSession[]>
  filteredSessions: ComputedRef<ChatSession[]>
  selectedSession: ComputedRef<ChatSession | null>
  selectedSessionId: Ref<string | null>
  sessionFilters: TraceSessionFilters
  runFilters: TraceRunFilters
  sessionTraceItems: Ref<TraceItem[]>
  traceSummary: Ref<TraceSummaryState>
  selectedTrace: Ref<TraceItem | null>
  spans: Ref<SpanItem[]>
  tree: Ref<SpanTreeNode[]>
  selectedSpan: Ref<SpanItem | null>
  loadingDetail: Ref<boolean>
  traceStore: TraceControllerStore
  listSessions: (options: { includeRuns?: boolean }) => Promise<ChatSession[]>
  listTraces: (params: TraceListQuery) => Promise<TraceListResponse>
  getTrace: (traceId: string) => Promise<TraceDetailResponse>
  clearPendingFilterRefresh: () => void
  scrollDetailIntoView: () => void
}

export const useTraceSessionController = ({
  sessions,
  filteredSessions,
  selectedSession,
  selectedSessionId,
  sessionFilters,
  runFilters,
  sessionTraceItems,
  traceSummary,
  selectedTrace,
  spans,
  tree,
  selectedSpan,
  loadingDetail,
  traceStore,
  listSessions,
  listTraces,
  getTrace,
  clearPendingFilterRefresh,
  scrollDetailIntoView,
}: UseTraceSessionControllerParams) => {
  const clearTraceSelection = () => {
    selectedTrace.value = null
    selectedSpan.value = null
    spans.value = []
    tree.value = []
    sessionTraceItems.value = []
  }

  const loadTraceSummary = async () => {
    try {
      const resp = await listTraces({ page: 1, limit: 100, status: "" })
      const items = resp.items || []
      traceSummary.value = summarizeTraceItems(items, resp.total_count)
    } catch {
      traceSummary.value = {
        ...summarizeTraceItems(sessionTraceItems.value),
        avgLatencyMs: 0,
      }
    }
  }

  const selectTraceById = async (traceId: string | null | undefined) => {
    const id = (traceId || "").trim()
    if (!id || selectedTrace.value?.trace_id === id) return
    const localTrace = sessionTraceItems.value.find((trace) => trace.trace_id === id)
    if (isChatRunFallbackTrace(localTrace)) {
      const run = selectedSession.value?.runs?.find((item: ChatSessionRun) => item.run_id === localTrace.run_id)
      const resp = buildChatRunFallbackDetail(localTrace, run)
      selectedTrace.value = resp.trace
      spans.value = resp.spans || []
      tree.value = resp.tree || []
      selectedSpan.value = findFirstTraceSpan(tree.value, spans.value)
      traceStore.setCurrentTraceId(resp.trace.trace_id)
      scrollDetailIntoView()
      return
    }
    loadingDetail.value = true
    try {
      const resp = await getTrace(id)
      selectedTrace.value = resp.trace
      spans.value = resp.spans || []
      tree.value = resp.tree || []
      selectedSpan.value = findFirstTraceSpan(tree.value, spans.value)
      traceStore.setCurrentTraceId(resp.trace.trace_id)
      scrollDetailIntoView()
    } finally {
      loadingDetail.value = false
    }
  }

  const openTraceDetail = async (traceId: string | null | undefined) => {
    await selectTraceById(traceId)
  }

  const loadSessionTraces = async (session: ChatSession, preferredRunId?: string | null) => {
    const runId = (preferredRunId || "").trim()
    clearTraceSelection()
    traceStore.setTraceFilters(buildTraceStoreFilters({ session, runId, filters: runFilters }))
    const baseParams = buildTraceListParams({ session, filters: runFilters })
    const resp = await listTraces(baseParams)
    let realItems = resp.items || []
    let items = mergeChatRunFallbackTraces(realItems, session)
    let traceToSelect = runId ? items.find((trace) => trace.run_id === runId) : null
    if (runId && !traceToSelect) {
      const exactResp = await listTraces({
        ...baseParams,
        limit: 1,
        run_id: runId,
      })
      traceToSelect = exactResp.items?.[0] || null
      if (traceToSelect) {
        realItems = mergePreferredTraceItem(realItems, traceToSelect)
        items = mergeChatRunFallbackTraces(realItems, session)
        traceToSelect = items.find((trace) => trace.run_id === runId) || traceToSelect
      }
    }
    sessionTraceItems.value = items
    traceStore.setTraceItems(items)
    if (traceToSelect) await openTraceDetail(traceToSelect.trace_id)
  }

  const reconcileSessionSelection = async () => {
    const selection = resolveTraceSessionSelection({
      visibleSessions: filteredSessions.value,
      selectedSessionId: selectedSessionId.value,
      selectedSession: selectedSession.value,
      requestedSessionId: sessionFilters.sessionId,
    })
    if (selection.keepCurrent) return

    if (selection.shouldClearSelection) clearTraceSelection()
    selectedSessionId.value = selection.nextSessionId
    if (selection.nextSession) await loadSessionTraces(selection.nextSession)
  }

  const refresh = async () => {
    sessions.value = await listSessions({ includeRuns: true })
    await loadTraceSummary()
    const currentSession = sessions.value.find((session) => session.session_id === selectedSessionId.value)
    if (currentSession) {
      await loadSessionTraces(currentSession, runFilters.runId)
      return
    }
    await reconcileSessionSelection()
  }

  const selectSession = async (session: ChatSession) => {
    if (selectedSessionId.value === session.session_id && sessionTraceItems.value.length) return
    selectedSessionId.value = session.session_id
    await loadSessionTraces(session)
    scrollDetailIntoView()
  }

  const selectSessionById = async (sessionId: string, userId?: string | null, runId?: string | null) => {
    const request = normalizeTraceSessionOpenRequest(sessionId, userId, runId)
    if (!request) return

    clearPendingFilterRefresh()
    sessionFilters.sessionId = request.sessionId
    if (request.userFilter !== undefined) sessionFilters.userId = request.userFilter
    sessionFilters.status = "all"
    runFilters.runId = request.runId

    sessions.value = await listSessions({ includeRuns: true })
    const target = ensureTraceSession(sessions.value, request)
    sessions.value = target.sessions

    selectedSessionId.value = target.session.session_id
    await loadSessionTraces(target.session, runFilters.runId)
    scrollDetailIntoView()
  }

  const resetAllFilters = async () => {
    Object.assign(sessionFilters, createTraceSessionFilters())
    Object.assign(runFilters, createTraceRunFilters())
    selectedSessionId.value = null
    traceStore.resetTraceFilters()
    await refresh()
  }

  const refreshRuns = async () => {
    const session = selectedSession.value
    if (!session) {
      await refresh()
      return
    }
    await loadSessionTraces(session, runFilters.runId)
  }

  const refreshAll = async () => {
    if (selectedSession.value) {
      await refreshRuns()
    } else {
      await refresh()
    }
  }

  return {
    clearTraceSelection,
    loadTraceSummary,
    reconcileSessionSelection,
    refresh,
    selectSession,
    selectSessionById,
    loadSessionTraces,
    selectTraceById,
    openTraceDetail,
    resetAllFilters,
    refreshAll,
    refreshRuns,
  }
}
