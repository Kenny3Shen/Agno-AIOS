import { apiFetch, jsonInit, requestJson } from '@/shared/api/client'
import type { JsonRecord } from '@/shared/types/common'

export interface Notification {
  id: number
  title: string
  body: string
  data: JsonRecord
  read: boolean
  created_at: number
  read_at?: number | null
}

export interface NotificationsResponse {
  notifications: Notification[]
  unread_count: number
}

export const getNotifications = () => requestJson<NotificationsResponse>('/notifications')
export const markNotificationRead = (id: number) =>
  requestJson<{ success: boolean }>(`/notifications/${encodeURIComponent(id)}/read`, jsonInit('POST'))
export const markAllNotificationsRead = () => requestJson<{ updated_count: number }>('/notifications/read-all', jsonInit('POST'))
export const deleteNotification = (id: number) =>
  requestJson<{ success: boolean }>(`/notifications/${encodeURIComponent(id)}`, jsonInit('DELETE'))

const parseNotification = (value: unknown): Notification | null => {
  if (!value || typeof value !== 'object') return null
  const row = value as Record<string, unknown>
  if (typeof row.id !== 'number' || typeof row.title !== 'string' || typeof row.body !== 'string') return null
  return {
    id: row.id,
    title: row.title,
    body: row.body,
    data: row.data && typeof row.data === 'object' ? (row.data as JsonRecord) : {},
    read: row.read === true,
    created_at: typeof row.created_at === 'number' ? row.created_at : 0,
    read_at: typeof row.read_at === 'number' ? row.read_at : null,
  }
}

export const streamNotifications = async (
  afterId: number,
  onNotification: (notification: Notification) => void,
  signal: AbortSignal
) => {
  const response = await apiFetch(`/notifications/stream?after_id=${Math.max(0, afterId)}`, {
    headers: { Accept: 'text/event-stream' },
    signal,
  })
  if (!response.ok || !response.body) throw new Error(`Notification stream failed (${response.status})`)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  const flush = (block: string) => {
    const lines = block.replace(/\r/g, '').split('\n')
    const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim() ?? 'message'
    if (event !== 'notification.created') return
    const data = lines
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).replace(/^ /, ''))
      .join('\n')
    if (!data) return
    try {
      const notification = parseNotification(JSON.parse(data))
      if (notification) onNotification(notification)
    } catch {
      // Ignore malformed events; the REST query remains the durable fallback.
    }
  }
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const blocks = buffer.split(/\n\n|\r\n\r\n/)
    buffer = blocks.pop() ?? ''
    blocks.forEach(flush)
    if (done) break
  }
  if (buffer.trim()) flush(buffer)
}
