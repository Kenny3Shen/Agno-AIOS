import { useEffect, useMemo, useReducer, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRouter, useRouterState } from '@tanstack/react-router'
import { cancelRun, streamMessage } from './api'
import { chatKeys, historyQuery, modelsQuery, SESSION_PAGE_SIZE, sessionsQuery } from './queries'
import { chatReducer, defaultReasoningEffort, initialChatState, previousPrompt } from './utils'
import type { SessionListResult } from './api'
import type { ChatRunEvent, ChatSession, Message } from './types'
import type { ReasoningEffort } from '@/shared/types/common'

export function useChat() {
  const { t } = useTranslation('chat')
  const queryClient = useQueryClient()
  const router = useRouter()
  const searchStr = useRouterState({ select: (state) => state.location.searchStr })
  const sessionId = new URLSearchParams(searchStr).get('session')
  const [state, dispatch] = useReducer(chatReducer, initialChatState)
  const abortRef = useRef<AbortController | null>(null)
  const activeRunIdRef = useRef<string | null>(null)
  const sessionsQueryResult = useInfiniteQuery(sessionsQuery())
  const sessionItems = useMemo(
    () => sessionsQueryResult.data?.pages.flatMap((page) => page.data) ?? [],
    [sessionsQueryResult.data]
  )
  const sessions = {
    ...sessionsQueryResult,
    data: sessionItems,
  }
  const history = useQuery(historyQuery(sessionId ?? ''))
  const models = useQuery(modelsQuery())

  useEffect(() => {
    if (sessionId && history.data) dispatch({ type: 'history', messages: history.data })
    else if (!sessionId) dispatch({ type: 'reset' })
  }, [history.data, sessionId])
  const hasPausedRun = state.messages.some((message) => message.role === 'assistant' && message.status === 'paused')
  useEffect(() => {
    if (!sessionId || !hasPausedRun) return
    const refreshHistory = () => void queryClient.invalidateQueries({ queryKey: chatKeys.history(sessionId) })
    const interval = window.setInterval(refreshHistory, 2_000)
    return () => window.clearInterval(interval)
  }, [hasPausedRun, queryClient, sessionId])
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
    void router.history.push(value ? `/chat?session=${encodeURIComponent(value)}` : '/chat')
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
      queryClient.setQueryData<{ pages: SessionListResult[]; pageParams: number[] }>(chatKeys.sessions(), (current) => {
        const pages = current?.pages ?? []
        if (!pages.length) {
          return {
            pages: [
              {
                data: [optimisticSession],
                meta: { page: 1, limit: SESSION_PAGE_SIZE, total_pages: 1, total_count: 1, search_time_ms: 0 },
              },
            ],
            pageParams: [1],
          }
        }
        const [first, ...rest] = pages
        const nextFirst: SessionListResult = {
          ...first,
          data: [optimisticSession, ...first.data.filter((item) => item.session_id !== activeSession)],
          meta: {
            ...first.meta,
            total_count: Math.max(first.meta.total_count, first.data.length) + (first.data.some((item) => item.session_id === activeSession) ? 0 : 1),
          },
        }
        return { pages: [nextFirst, ...rest], pageParams: current?.pageParams ?? [1] }
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
    try {
      await streamMessage(
        {
          message: text,
          session_id: activeSession,
          model_id: selectedModel.id,
          ...(state.reasoningEffort ? { reasoning_effort: state.reasoningEffort } : {}),
          search_knowledge: state.searchKnowledge,
          live_search: state.liveSearch,
        },
        (event: ChatRunEvent) => {
          if (event.type === 'run.started') activeRunIdRef.current = event.runId
          dispatch({ type: 'event', id: assistantId, event })
        },
        controller.signal
      )
      await queryClient.invalidateQueries({ queryKey: chatKeys.history(activeSession) })
      await queryClient.invalidateQueries({ queryKey: chatKeys.sessionLists })
    } catch (error) {
      if ((error as Error).name === 'AbortError') {
        dispatch({
          type: 'event',
          id: assistantId,
          event: {
            type: 'run.cancelled',
            runId: activeRunIdRef.current ?? undefined,
            reason: t('stoppedGenerating'),
          },
        })
      } else {
        dispatch({
          type: 'network-error',
          id: assistantId,
          message: error instanceof Error ? error.message : 'Chat request failed',
        })
      }
    } finally {
      abortRef.current = null
      activeRunIdRef.current = null
    }
  }

  const retry = (assistantId: string) => {
    const prompt = previousPrompt(state.messages, assistantId)
    const index = state.messages.findIndex((message) => message.id === assistantId)
    if (!prompt || index < 0) return
    const base = state.messages.slice(0, index)
    dispatch({ type: 'history', messages: base })
    void submit(prompt, false)
  }
  const cancel = async () => {
    const runId = activeRunIdRef.current
    // Always stop the client SSE first so the UI unblocks even before run.started.
    abortRef.current?.abort()
    if (!runId) return
    try {
      await cancelRun(runId)
    } catch (error) {
      // Best-effort server cancel; client stream is already aborted.
      const detail = error instanceof Error ? error.message : String(error)
      console.warn(`[chat] server cancel failed for run ${runId}: ${detail}`)
      dispatch({ type: 'soft-error', message: t('cancelServerFailed') })
    }
  }
  const setReasoningEffort = (value: ReasoningEffort | null) => dispatch({ type: 'reasoning-effort', value })
  const setSearchKnowledge = (value: boolean) => dispatch({ type: 'search-knowledge', value })
  const setLiveSearch = (value: boolean) => dispatch({ type: 'live-search', value })
  const newChat = () => {
    dispatch({ type: 'reasoning-effort', value: defaultReasoningEffort(selectedModel) })
    setSession(null)
  }
  return {
    state,
    dispatch,
    sessionId,
    sessions,
    history,
    models,
    selectedModel,
    setSession,
    setModel,
    setReasoningEffort,
    setSearchKnowledge,
    setLiveSearch,
    submit,
    retry,
    newChat,
    cancel,
  }
}
