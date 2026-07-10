import { useEffect, useMemo, useReducer, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRouter, useRouterState } from '@tanstack/react-router'
import { mergeRunMetadata, streamMessage } from './api'
import { chatKeys, historyQuery, modelsQuery, sessionsQuery } from './queries'
import { chatReducer, initialChatState, previousPrompt } from './utils'
import type { Message } from './types'

export function useChat() {
  const queryClient = useQueryClient()
  const router = useRouter()
  const searchStr = useRouterState({ select: (state) => state.location.searchStr })
  const sessionId = new URLSearchParams(searchStr).get('session')
  const [state, dispatch] = useReducer(chatReducer, initialChatState)
  const abortRef = useRef<AbortController | null>(null)
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
  const setModel = (value: string) => { localStorage.setItem('agno-aios-chat-model-id', value); dispatch({ type: 'model', value }) }

  const submit = async (prompt: string, appendUser = true, baseMessages = state.messages) => {
    const text = prompt.trim()
    if (!text || state.requesting || !selectedModel?.enabled || !selectedModel.configured) return
    const activeSession = sessionId ?? crypto.randomUUID()
    if (!sessionId) setSession(activeSession)
    const assistantId = crypto.randomUUID()
    const user: Message = { id: crypto.randomUUID(), role: 'user', content: text, final: true, session_id: activeSession }
    const assistant: Message = { id: assistantId, role: 'assistant', content: '', final: false, session_id: activeSession }
    dispatch({ type: 'start', user: appendUser ? user : undefined, assistant, modelId: selectedModel.id })
    const controller = new AbortController()
    abortRef.current = controller
    let accumulated = ''
    try {
      await streamMessage({ message: text, session_id: activeSession, model_id: selectedModel.id }, (chunk) => { accumulated += chunk; dispatch({ type: 'chunk', id: assistantId, chunk }) }, controller.signal)
      dispatch({ type: 'finish', id: assistantId })
      const persisted = await queryClient.fetchQuery({ ...historyQuery(activeSession), staleTime: 0 })
      dispatch({ type: 'history', messages: mergeRunMetadata([...baseMessages, ...(appendUser ? [user] : []), { ...assistant, content: accumulated, final: true }], persisted) })
      await queryClient.invalidateQueries({ queryKey: chatKeys.sessionLists })
    } catch (error) {
      if ((error as Error).name !== 'AbortError') dispatch({ type: 'error', id: assistantId, message: error instanceof Error ? error.message : 'Chat request failed' })
      else dispatch({ type: 'finish', id: assistantId })
    } finally { abortRef.current = null }
  }

  const retry = (assistantId: string) => {
    const prompt = previousPrompt(state.messages, assistantId)
    const index = state.messages.findIndex((message) => message.id === assistantId)
    if (!prompt || index < 0) return
    const base = state.messages.slice(0, index)
    dispatch({ type: 'history', messages: base })
    void submit(prompt, false, base)
  }
  const newChat = () => setSession(null)
  return { state, dispatch, sessionId, sessions, history, models, selectedModel, setSession, setModel, submit, retry, newChat, cancel: () => abortRef.current?.abort() }
}
