import { useEffect, useMemo, useReducer, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRouter, useRouterState } from '@tanstack/react-router'
import { cancelRun, streamMessage } from './api'
import { chatKeys, historyQuery, modelsQuery, sessionsQuery } from './queries'
import { chatReducer, initialChatState, previousPrompt } from './utils'
import type { ChatRunEvent, Message } from './types'
import type { ReasoningEffort } from '@/shared/types/common'

export function useChat() {
  const queryClient = useQueryClient()
  const router = useRouter()
  const searchStr = useRouterState({ select: (state) => state.location.searchStr })
  const sessionId = new URLSearchParams(searchStr).get('session')
  const [state, dispatch] = useReducer(chatReducer, initialChatState)
  const abortRef = useRef<AbortController | null>(null)
  const activeRunIdRef = useRef<string | null>(null)
  const sessions = useQuery(sessionsQuery())
  const history = useQuery(historyQuery(sessionId ?? ''))
  const models = useQuery(modelsQuery())

  useEffect(() => { if (sessionId && history.data) dispatch({ type: 'history', messages: history.data }); else if (!sessionId) dispatch({ type: 'reset' }) }, [history.data, sessionId])
  useEffect(() => {
    if (!models.data?.models.length || state.selectedModelId) return
    const selected = models.data.models.find((model) => model.id === models.data.active_model_id && model.enabled) ?? models.data.models.find((model) => model.enabled) ?? models.data.models[0]
    if (selected) dispatch({ type: 'model', value: selected.id })
  }, [models.data, state.selectedModelId])

  const selectedModel = useMemo(() => models.data?.models.find((model) => model.id === state.selectedModelId) ?? null, [models.data, state.selectedModelId])
  const setSession = (value: string | null) => { void router.history.push(value ? `/chat?session=${encodeURIComponent(value)}` : '/chat') }
  const setModel = (value: string) => {
    localStorage.setItem('agno-aios-chat-model-id', value)
    dispatch({ type: 'model', value })
  }

  const submit = async (prompt: string, appendUser = true) => {
    const text = prompt.trim()
    if (!text || state.requesting || !selectedModel?.enabled || !selectedModel.configured) return
    const activeSession = sessionId ?? crypto.randomUUID()
    if (!sessionId) setSession(activeSession)
    const assistantId = crypto.randomUUID()
    const user: Message = { id: crypto.randomUUID(), role: 'user', content: text, final: true, session_id: activeSession }
    const assistant: Message = { id: assistantId, role: 'assistant', content: '', final: false, status: 'streaming', session_id: activeSession, tool_steps: [], sources: [], followups: [] }
    dispatch({ type: 'start', user: appendUser ? user : undefined, assistant, modelId: selectedModel.id })
    const controller = new AbortController(); abortRef.current = controller; activeRunIdRef.current = null
    try {
      await streamMessage({ message: text, session_id: activeSession, model_id: selectedModel.id, ...(state.reasoningEffort ? { reasoning_effort: state.reasoningEffort } : {}) }, (event: ChatRunEvent) => {
        if (event.type === 'run.started') activeRunIdRef.current = event.runId
        dispatch({ type: 'event', id: assistantId, event })
      }, controller.signal)
      await queryClient.invalidateQueries({ queryKey: chatKeys.history(activeSession) })
      await queryClient.invalidateQueries({ queryKey: chatKeys.sessionLists })
    } catch (error) {
      if ((error as Error).name !== 'AbortError') dispatch({ type: 'network-error', id: assistantId, message: error instanceof Error ? error.message : 'Chat request failed' })
    } finally { abortRef.current = null; activeRunIdRef.current = null }
  }

  const retry = (assistantId: string) => {
    const prompt = previousPrompt(state.messages, assistantId)
    const index = state.messages.findIndex((message) => message.id === assistantId)
    if (!prompt || index < 0) return
    const base = state.messages.slice(0, index); dispatch({ type: 'history', messages: base }); void submit(prompt, false)
  }
  const cancel = async () => {
    const runId = activeRunIdRef.current
    if (!runId) return
    try { await cancelRun(runId) } catch (error) { dispatch({ type: 'network-error', id: state.messages.at(-1)?.id ?? '', message: error instanceof Error ? error.message : 'Unable to cancel the active run' }) }
  }
  const setReasoningEffort = (value: ReasoningEffort | null) => dispatch({ type: 'reasoning-effort', value })
  const newChat = () => { dispatch({ type: 'reasoning-effort', value: null }); setSession(null) }
  return { state, dispatch, sessionId, sessions, history, models, selectedModel, setSession, setModel, setReasoningEffort, submit, retry, newChat, cancel }
}
