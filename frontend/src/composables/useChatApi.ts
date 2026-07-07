import { ref } from 'vue'
import { apiFetch } from '../lib/apiClient'
import { useApiMessage, messageFromUnknown } from './useApiCore'
import type {
  ChatSession,
  Message
} from '../types'

/**
 * LLM chat API.
 */
export function useChatApi() {
  const apiMessage = useApiMessage()
  const loading = ref(false)
  const error = ref<string | null>(null)

  const sendMessageStream = async (
    message: string,
    sessionId: string | null,
    modelId: string | null,
    onChunk: (chunk: string) => void
  ): Promise<void> => {
    loading.value = true
    error.value = null

    try {
      const response = await apiFetch('/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream'
        },
        body: JSON.stringify({
          message,
          session_id: sessionId,
          model_id: modelId,
        })
      })

      if (!response.ok || !response.body) {
        throw new Error(apiMessage('chatHttpFailed', { status: response.status }))
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''

        for (const part of parts) {
          const lines = part.split('\n')
          const isError = lines.some(line => line.startsWith('event: error'))
          const dataLines = lines
            .filter(line => line.startsWith('data: '))
            .map(line => line.slice(6))

          if (!dataLines.length) continue

          const data = dataLines.join('\n')
          if (data === '[DONE]') return
          if (isError) {
            throw new Error(data)
          }

          onChunk(data)
        }
      }
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, apiMessage('chatSendFailed'))
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    sendMessageStream
  }
}

/**
 * Chat session history API.
 */
export function useChatHistory() {
  const apiMessage = useApiMessage()
  const loadingSessions = ref(false)

  const listSessions = async (options: { includeRuns?: boolean } = {}): Promise<ChatSession[]> => {
    loadingSessions.value = true
    try {
      const qs = new URLSearchParams()
      if (options.includeRuns) qs.set('include_runs', 'true')
      const response = await apiFetch(`/chat/sessions${qs.size ? `?${qs.toString()}` : ''}`)
      if (!response.ok) throw new Error(apiMessage('chatSessionsLoadFailed'))
      const data: unknown = await response.json()
      return Array.isArray(data) ? data : []
    } finally {
      loadingSessions.value = false
    }
  }

  const getSessionHistory = async (sessionId: string): Promise<Message[]> => {
    const response = await apiFetch(`/chat/sessions/${sessionId}`)
    if (!response.ok) throw new Error(apiMessage('chatHistoryLoadFailed'))
    const data: unknown = await response.json()
    return Array.isArray(data) ? data : []
  }

  const archiveSession = async (sessionId: string): Promise<void> => {
    const response = await apiFetch(`/chat/sessions/${sessionId}`, {
      method: 'DELETE'
    })
    if (!response.ok) throw new Error(apiMessage('chatArchiveFailed'))
  }

  return {
    loadingSessions,
    listSessions,
    getSessionHistory,
    archiveSession
  }
}
