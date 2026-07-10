import { apiFetch, jsonInit, requestJson } from '@/shared/api/client'
import type { ModelConfigResponse } from '@/shared/types/common'
import type { ChatSession, Message } from './types'
import { consumeSse, normalizeMessages } from './utils'

export const listSessions = async (includeArchived = false) => {
  const value = await requestJson<unknown>(`/chat/sessions${includeArchived ? '?include_archived=true' : ''}`)
  return Array.isArray(value) ? value as ChatSession[] : []
}
export const getHistory = async (sessionId: string) => normalizeMessages(await requestJson<unknown>(`/chat/sessions/${encodeURIComponent(sessionId)}`))
export const archiveSession = (sessionId: string) => requestJson<{ success: boolean }>(`/chat/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
export const getModels = () => requestJson<ModelConfigResponse>('/models')

export const streamMessage = async (payload: { message: string; session_id: string; model_id: string | null }, onChunk: (chunk: string) => void, signal: AbortSignal) => {
  const response = await apiFetch('/chat', { ...jsonInit('POST', payload), headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' }, signal })
  if (!response.ok || !response.body) throw new Error(`Chat request failed (${response.status})`)
  let receivedContent = false
  await consumeSse(response.body, ({ event, data }) => {
    if (event === 'error') throw new Error(data)
    if (data !== '[DONE]') {
      receivedContent = true
      onChunk(data)
    }
  })
  if (!receivedContent) throw new Error('Chat stream ended without content')
}

export const mergeRunMetadata = (messages: Message[], history: Message[]) => messages.map((message) => {
  if (message.role !== 'assistant' || !message.content.trim()) return message
  const persisted = [...history].reverse().find((item) => item.role === 'assistant' && item.content.trim() === message.content.trim())
  return persisted ? { ...message, ...persisted, content: message.content, final: true } : message
})
