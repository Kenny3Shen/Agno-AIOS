import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRouter, useRouterState } from '@tanstack/react-router'
import { cancelRun, streamMessage } from './api'
import {
  abortActiveChatStream,
  clearChatStream,
  registerChatStream,
  updateChatStreamRunId,
} from './activeChatStream'
import { ApiError } from '@/shared/api/client'
import { chatKeys, historyQuery, modelsQuery, SESSION_PAGE_SIZE, sessionsQuery } from './queries'
import { chatReducer, defaultReasoningEffort, initialChatState, previousPrompt } from './utils'
import type { SessionListResult } from './api'
import type { ChatRunEvent, ChatSession, Message } from './types'
import type { ReasoningEffort } from '@/shared/types/common'
import { useDebouncedValue } from '@/shared/lib/useDebouncedValue'
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
  const [sessionSearch, setSessionSearch] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const debouncedSessionSearch = useDebouncedValue(sessionSearch, 300)
  const abortRef = useRef<AbortController | null>(null)
  const activeRunIdRef = useRef<string | null>(null)
  // Track URL session so any dual useChat instance aborts the live stream on change
  // (sidebar may call setSession while only the page instance owns the SSE).
  const prevSessionIdRef = useRef<string | null>(sessionId)
  const sessionsQueryResult = useInfiniteQuery(
    sessionsQuery({
      archivedOnly: showArchived,
      q: debouncedSessionSearch.trim(),
    }),
  )
  const sessionItems = useMemo(
    () => sessionsQueryResult.data?.pages.flatMap((page) => page.data) ?? [],
    [sessionsQueryResult.data]
  )
  const sessions = {
    ...sessionsQueryResult,
    data: sessionItems,
  }
  const activeSessionMeta = useMemo(
    () => (sessionId ? sessionItems.find((item) => item.session_id === sessionId) : undefined),
    [sessionId, sessionItems]
  )
  const isWorkflowSession = String(activeSessionMeta?.session_type || '').toLowerCase() === 'workflow'
  const history = useQuery(historyQuery(sessionId ?? '', !isWorkflowSession))
  const models = useQuery(modelsQuery())

  // URL session changed (sidebar, deep link, or another useChat instance): abort live SSE
  // so this instance can load history and the server run is cancelled best-effort.
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

  // Unmount only aborts the stream this instance registered (sidebar unmount must not kill page stream).
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
    // Switching sessions mid-stream aborts the live SSE even if this instance is idle
    // (ChatTaskPanel vs ChatPage dual useChat).
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
      }
      if (!showArchived) {
        queryClient.setQueryData<{ pages: SessionListResult[]; pageParams: number[] }>(
          chatKeys.sessions({ archivedOnly: false, q: debouncedSessionSearch.trim() }),
          (current) => {
            const pages = current?.pages ?? []
            if (!pages.length) {
              return {
                pages: [
                  {
                    data: [optimisticSession],
                    meta: {
                      page: 1,
                      limit: SESSION_PAGE_SIZE,
                      total_pages: 1,
                      total_count: 1,
                      search_time_ms: 0,
                    },
                  },
                ],
                pageParams: [1],
              }
            }
            const [first, ...rest] = pages
            const nextFirst: SessionListResult = {
              ...first,
              data: [
                optimisticSession,
                ...first.data.filter((item) => item.session_id !== activeSession),
              ],
              meta: {
                ...first.meta,
                total_count:
                  Math.max(first.meta.total_count, first.data.length) +
                  (first.data.some((item) => item.session_id === activeSession) ? 0 : 1),
              },
            }
            return { pages: [nextFirst, ...rest], pageParams: current?.pageParams ?? [1] }
          },
        )
      }
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
    setSessionSearch('')
    // setSession aborts any in-flight run before clearing the URL session.
    setSession(null)
  }
  return {
    state,
    dispatch,
    sessionId,
    sessions,
    sessionSearch,
    setSessionSearch,
    debouncedSessionSearch,
    showArchived,
    setShowArchived,
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
