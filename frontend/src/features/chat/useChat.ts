import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRouter, useRouterState } from '@tanstack/react-router'
import { cancelRun, streamMessage, unarchiveSession } from './api'
import {
  abortActiveChatStream,
  clearChatStream,
  registerChatStream,
  updateChatStreamRunId,
} from './activeChatStream'
import { ApiError } from '@/shared/api/client'
import { chatKeys, historyQuery, modelsQuery, sessionMetaQuery, sessionsQuery } from './queries'
import { markSessionActiveInCaches } from './sessionCache'
import { chatReducer, defaultReasoningEffort, initialChatState, previousPrompt } from './utils'
import type { ChatRunEvent, ChatSession, Message } from './types'
import type { ReasoningEffort } from '@/shared/types/common'
import { buildTraceSearch, emptyTraceFilters } from '@/features/trace/utils'

function bestEffortCancelRun(runId: string | null | undefined) {
  if (!runId) return
  void cancelRun(runId).catch((error: unknown) => {
    // Leaving the session: soft-error would be cleared by reset and is noisy.
    if (error instanceof ApiError && error.status === 404) return
    const detail = error instanceof Error ? error.message : String(error)
    console.warn(`[chat] cancel on session switch failed for ${runId}: ${detail}`)
  })
}



export function useChat() {
  const { t } = useTranslation('chat')
  const queryClient = useQueryClient()
  const router = useRouter()
  const searchStr = useRouterState({ select: (state) => state.location.searchStr })
  const sessionId = new URLSearchParams(searchStr).get('session')
  const [state, dispatch] = useReducer(chatReducer, initialChatState)
  const abortRef = useRef<AbortController | null>(null)
  const activeRunIdRef = useRef<string | null>(null)
  // Track URL session for abort-on-change (sidebar navigates URL; this hook owns the SSE).
  const prevSessionIdRef = useRef<string | null>(sessionId)
  // Active (non-archived) list only — shares RQ cache with ChatTaskPanel recents.
  const sessionsQueryResult = useInfiniteQuery(sessionsQuery({}))
  const sessionItems = useMemo(
    () => sessionsQueryResult.data?.pages.flatMap((page) => page.data) ?? [],
    [sessionsQueryResult.data]
  )
  const sessions = {
    ...sessionsQueryResult,
    data: sessionItems,
  }
  const listSessionMeta = useMemo(
    () => (sessionId ? sessionItems.find((item) => item.session_id === sessionId) : undefined),
    [sessionId, sessionItems]
  )
  // Deep links / older sessions may sit outside the loaded recents window.
  const sessionMetaResult = useQuery(sessionMetaQuery(sessionId ?? '', Boolean(sessionId) && !listSessionMeta))
  const activeSessionMeta = listSessionMeta ?? sessionMetaResult.data ?? undefined
  const isWorkflowSession = String(activeSessionMeta?.session_type || '').toLowerCase() === 'workflow'
  // Wait for meta when missing from list so we do not load agent history for a workflow session.
  const metaResolved = !sessionId || Boolean(listSessionMeta) || sessionMetaResult.isFetched
  // Network/5xx on meta: do not treat as missing (404) or load history as agent blindly.
  const sessionMetaFailed =
    Boolean(sessionId) && !listSessionMeta && Boolean(sessionMetaResult.isError)
  // 404 meta → null data with success; treat as missing for empty-state UX.
  const sessionMissing =
    Boolean(sessionId) &&
    metaResolved &&
    !listSessionMeta &&
    sessionMetaResult.isSuccess &&
    sessionMetaResult.data == null
  const history = useQuery(
    historyQuery(
      sessionId ?? '',
      Boolean(sessionId) &&
        metaResolved &&
        !sessionMetaFailed &&
        !isWorkflowSession &&
        !sessionMissing,
    )
  )
  const models = useQuery(modelsQuery())

  // URL session changed (sidebar, deep link, browser history): abort live SSE
  // so history can load and the server run is cancelled best-effort.
  useEffect(() => {
    const prev = prevSessionIdRef.current
    prevSessionIdRef.current = sessionId
    if (prev === sessionId) return
    const { runId } = abortActiveChatStream()
    abortRef.current = null
    // Keep activeRunIdRef for submit's AbortError → run.cancelled payload; submit finally clears it.
    bestEffortCancelRun(runId)
    // null → new session is first-message submit (keep streaming UI). A→B or A→null needs clear.
    if (prev != null) {
      dispatch({ type: 'session-switch' })
    }
  }, [sessionId])

  // Unmount aborts only the stream registered by this page instance.
  useEffect(() => {
    return () => {
      const local = abortRef.current
      if (!local) return
      const runId = activeRunIdRef.current
      clearChatStream(local)
      try {
        local.abort()
      } catch {
        // ignore
      }
      abortRef.current = null
      bestEffortCancelRun(runId)
    }
  }, [])

  useEffect(() => {
    if (!sessionId) {
      dispatch({ type: 'reset' })
      return
    }
    if (!history.data) return
    // Avoid replacing an in-flight stream with a concurrent history fetch.
    if (state.requesting) return
    dispatch({ type: 'history', messages: history.data })
  }, [history.data, sessionId, state.requesting])

  // Workflow sessions are not agent transcripts — open Studio when known, else Trace.
  useEffect(() => {
    if (!sessionId || !isWorkflowSession) return
    const workflowId = String(activeSessionMeta?.workflow_id || '').trim()
    if (workflowId) {
      void router.history.replace(`/workflow?workflow_id=${encodeURIComponent(workflowId)}`)
      return
    }
    const filters = { ...emptyTraceFilters(), session_id: sessionId }
    const search = buildTraceSearch(filters, sessionId, '')
    void router.history.replace(`/trace${search ? `?${search}` : ''}`)
  }, [activeSessionMeta?.workflow_id, isWorkflowSession, router.history, sessionId])
  const hasPausedRun = state.messages.some((message) => message.role === 'assistant' && message.status === 'paused')
  useEffect(() => {
    if (!sessionId || !hasPausedRun || isWorkflowSession) return
    const refreshHistory = () => void queryClient.invalidateQueries({ queryKey: chatKeys.history(sessionId) })
    const interval = window.setInterval(refreshHistory, 2_000)
    return () => window.clearInterval(interval)
  }, [hasPausedRun, isWorkflowSession, queryClient, sessionId])
  useEffect(() => {
    if (!models.data?.models.length) return
    const selected =
      models.data.models.find((model) => model.id === state.selectedModelId) ??
      models.data.models.find((model) => model.id === models.data.active_model_id && model.enabled) ??
      models.data.models.find((model) => model.enabled) ??
      models.data.models[0]
    if (!selected) return
    const effort = defaultReasoningEffort(selected)
    if (state.selectedModelId !== selected.id) dispatch({ type: 'model', value: selected.id, reasoningEffort: effort })
    else if (state.reasoningEffort === null && effort !== null) dispatch({ type: 'reasoning-effort', value: effort })
  }, [models.data, state.reasoningEffort, state.selectedModelId])

  const selectedModel = useMemo(
    () => models.data?.models.find((model) => model.id === state.selectedModelId) ?? null,
    [models.data, state.selectedModelId]
  )
  const setSession = (value: string | null) => {
    const next = value
    const same =
      (next == null && !sessionId) || (next != null && next === sessionId)
    // Switching sessions mid-stream aborts the live SSE (sidebar may change URL first).
    if (!same) {
      const { runId } = abortActiveChatStream()
      abortRef.current = null
      // Keep activeRunIdRef for submit's AbortError → run.cancelled payload; submit finally clears it.
      bestEffortCancelRun(runId)
    }
    if (same) return
    void router.history.push(next ? `/chat?session=${encodeURIComponent(next)}` : '/chat')
  }
  const setModel = (value: string) => {
    localStorage.setItem('agno-aios-chat-model-id', value)
    const model = models.data?.models.find((item) => item.id === value) ?? null
    dispatch({ type: 'model', value, reasoningEffort: defaultReasoningEffort(model) })
  }

  const submit = async (prompt: string, appendUser = true) => {
    const text = prompt.trim()
    const hasPendingApproval = state.messages.some((message) => message.role === 'assistant' && message.status === 'paused')
    if (!text || state.requesting || hasPendingApproval || !selectedModel?.enabled || !selectedModel.configured) return
    const activeSession = sessionId ?? crypto.randomUUID()
    if (!sessionId) setSession(activeSession)
    if (!sessionId) {
      const now = Date.now() / 1_000
      const optimisticSession: ChatSession = {
        session_id: activeSession,
        preview: text,
        created_at: now,
        updated_at: now,
        archived: false,
      }
      markSessionActiveInCaches(queryClient, optimisticSession)
    } else if (activeSessionMeta?.archived) {
      // Continuing a thread should bring it back to recents.
      markSessionActiveInCaches(queryClient, {
        ...activeSessionMeta,
        preview: text || activeSessionMeta.preview,
        updated_at: Date.now() / 1_000,
      })
      void unarchiveSession(activeSession).catch((error: unknown) => {
        const detail = error instanceof Error ? error.message : String(error)
        console.warn(`[chat] auto-unarchive failed for ${activeSession}: ${detail}`)
        // Keep optimistic active caches; list invalidate will reconcile.
        void queryClient.invalidateQueries({ queryKey: chatKeys.sessionLists })
      })
    }
    const assistantId = crypto.randomUUID()
    const user: Message = { id: crypto.randomUUID(), role: 'user', content: text, final: true, session_id: activeSession }
    const assistant: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      final: false,
      status: 'streaming',
      session_id: activeSession,
      tool_steps: [],
      sources: [],
      followups: [],
    }
    dispatch({ type: 'start', user: appendUser ? user : undefined, assistant, modelId: selectedModel.id })
    const controller = new AbortController()
    abortRef.current = controller
    activeRunIdRef.current = null
    registerChatStream(controller, activeSession)
    try {
      await streamMessage(
        {
          message: text,
          session_id: activeSession,
          model_id: selectedModel.id,
          ...(state.reasoningEffort ? { reasoning_effort: state.reasoningEffort } : {}),
          // Tools-off / lean path ignores these server-side; send false for clarity.
          search_knowledge: state.enableTools ? state.searchKnowledge : false,
          live_search: state.enableTools ? state.liveSearch : false,
          enable_tools: state.enableTools,
        },
        (event: ChatRunEvent) => {
          // Drop late chunks if the user switched sessions mid-stream.
          if (prevSessionIdRef.current !== activeSession) return
          // Keep cancel targets current across retries / late run_id attachment.
          const eventRunId = 'runId' in event ? event.runId : undefined
          if (typeof eventRunId === 'string' && eventRunId) {
            activeRunIdRef.current = eventRunId
            updateChatStreamRunId(eventRunId)
          }
          dispatch({ type: 'event', id: assistantId, event })
        },
        controller.signal
      )
    } catch (error) {
      if ((error as Error).name === 'AbortError') {
        // Session switch already cleared requesting via session-switch; skip cancelled UI.
        if (prevSessionIdRef.current === activeSession) {
          dispatch({ type: 'clear-error' })
          dispatch({
            type: 'event',
            id: assistantId,
            event: {
              type: 'run.cancelled',
              runId: activeRunIdRef.current ?? undefined,
              reason: t('stoppedGenerating'),
            },
          })
        }
      } else if (prevSessionIdRef.current === activeSession) {
        dispatch({
          type: 'network-error',
          id: assistantId,
          message: error instanceof Error ? error.message : t('errorRequestFailed'),
        })
      }
    } finally {
      clearChatStream(controller)
      abortRef.current = null
      activeRunIdRef.current = null
      // Refresh after success, cancel, or failure (partial/cancelled runs may be stored).
      void queryClient.invalidateQueries({ queryKey: chatKeys.history(activeSession) })
      void queryClient.invalidateQueries({ queryKey: chatKeys.sessionLists })
    }
  }

  const retry = (assistantId: string) => {
    if (state.requesting) return
    const prompt = previousPrompt(state.messages, assistantId)
    const index = state.messages.findIndex((message) => message.id === assistantId)
    if (!prompt || index < 0) return
    const base = state.messages.slice(0, index)
    dispatch({ type: 'history', messages: base })
    void submit(prompt, false)
  }
  const cancel = useCallback(async () => {
    // Prefer process-wide stream (this instance or the sibling useChat owner).
    const global = abortActiveChatStream()
    // Local backup if registry was already cleared mid-flight.
    abortRef.current?.abort()
    abortRef.current = null
    const runId = global.runId ?? activeRunIdRef.current
    // Leave activeRunIdRef for submit's AbortError path; submit finally clears it.
    if (!runId) return
    try {
      await cancelRun(runId)
    } catch (error) {
      // Best-effort server cancel; client stream is already aborted.
      // 404 = run already finished or never registered (race with terminal event).
      if (error instanceof ApiError && error.status === 404) return
      const detail = error instanceof Error ? error.message : String(error)
      console.warn(`[chat] server cancel failed for run ${runId}: ${detail}`)
      dispatch({ type: 'soft-error', message: t('cancelServerFailed') })
    }
  }, [t])
  const setReasoningEffort = (value: ReasoningEffort | null) => dispatch({ type: 'reasoning-effort', value })
  const setSearchKnowledge = (value: boolean) => {
    try {
      localStorage.setItem('agno-aios-chat-search-knowledge', String(value))
    } catch {
      // ignore
    }
    dispatch({ type: 'search-knowledge', value })
  }
  const setEnableTools = (value: boolean) => {
    try {
      localStorage.setItem('agno-aios-chat-enable-tools', String(value))
      if (!value) {
        localStorage.setItem('agno-aios-chat-live-search', 'false')
      }
    } catch {
      // ignore
    }
    dispatch({ type: 'enable-tools', value })
  }
  const setLiveSearch = (value: boolean) => {
    try {
      localStorage.setItem('agno-aios-chat-live-search', String(value))
    } catch {
      // ignore
    }
    dispatch({ type: 'live-search', value })
  }
  const newChat = () => {
    dispatch({ type: 'reasoning-effort', value: defaultReasoningEffort(selectedModel) })
    // setSession aborts any in-flight run before clearing the URL session.
    setSession(null)
  }
  return {
    state,
    dispatch,
    sessionId,
    sessions,
    activeSessionMeta,
    sessionMetaLoading: Boolean(sessionId) && !listSessionMeta && !sessionMetaResult.isFetched,
    sessionMetaFailed,
    sessionMetaError:
      sessionMetaFailed && sessionMetaResult.error instanceof Error
        ? sessionMetaResult.error
        : sessionMetaFailed
          ? new Error('session meta failed')
          : null,
    sessionMetaRefetch: () => void sessionMetaResult.refetch(),
    sessionMissing,
    history,
    models,
    selectedModel,
    setSession,
    setModel,
    setReasoningEffort,
    setSearchKnowledge,
    setEnableTools,
    setLiveSearch,
    submit,
    retry,
    newChat,
    cancel,
  }
}
