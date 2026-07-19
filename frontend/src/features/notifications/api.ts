import { apiFetch, jsonInit, requestJson } from '@/shared/api/client'
import { normalizePaginatedList, type ListPaginationMeta } from '@/shared/lib/pagination'
import type { JsonRecord } from '@/shared/types/common'

export interface Notification {
  id: number
  title: string
  body: string
  data: JsonRecord
  read: boolean
  created_at: number
  read_at: number | null
}

const invalidNotificationPayload = (context: string): never => {
  throw new Error(`${context}: invalid notification payload`)
}

const isInteger = (value: unknown): value is number =>
  typeof value === 'number' && Number.isInteger(value)

const isNonNegativeInteger = (value: unknown): value is number => isInteger(value) && value >= 0

const isNullableInteger = (value: unknown): value is number | null => value === null || isInteger(value)

const isJsonRecord = (value: unknown): value is JsonRecord =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value)

const unreadCountFromEnvelope = (value: unknown): number => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return invalidNotificationPayload('getNotifications')
  }
  const meta = (value as Record<string, unknown>).meta
  if (!meta || typeof meta !== 'object' || Array.isArray(meta)) {
    return invalidNotificationPayload('getNotifications')
  }
  const unreadCount = (meta as Record<string, unknown>).unread_count
  if (!isNonNegativeInteger(unreadCount)) {
    return invalidNotificationPayload('getNotifications')
  }
  return unreadCount
}

const parseNotification = (value: unknown, context: string): Notification => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return invalidNotificationPayload(context)
  }
  const row = value as Record<string, unknown>
  const id = row.id
  const data = row.data
  const read = row.read
  const createdAt = row.created_at
  const readAt = row.read_at
  if (
    !isInteger(id) ||
    id < 1 ||
    typeof row.title !== 'string' ||
    typeof row.body !== 'string' ||
    !isJsonRecord(data) ||
    typeof read !== 'boolean' ||
    !isInteger(createdAt) ||
    createdAt < 0 ||
    !isNullableInteger(readAt)
  ) {
    return invalidNotificationPayload(context)
  }
  return {
    id,
    title: row.title,
    body: row.body,
    data,
    read,
    created_at: createdAt,
    read_at: readAt,
  }
}

export type NotificationsResponse = {
  data: Notification[]
  meta: ListPaginationMeta & { unread_count: number }
}

export const getNotifications = async (): Promise<NotificationsResponse> => {
  const raw = await requestJson<unknown>('/notifications')
  const unreadCount = unreadCountFromEnvelope(raw)
  const result = normalizePaginatedList(raw, {
    mapItem: (item) => parseNotification(item, 'getNotifications'),
    extras: true,
  })
  return {
    data: result.data,
    meta: {
      ...result.meta,
      unread_count: unreadCount,
    },
  }
}
export const markNotificationRead = (id: number) =>
  requestJson<{ success: boolean }>(`/notifications/${encodeURIComponent(id)}/read`, jsonInit('POST'))
export const markAllNotificationsRead = () => requestJson<{ updated_count: number }>('/notifications/read-all', jsonInit('POST'))
export const deleteNotification = (id: number) =>
  requestJson<{ success: boolean }>(`/notifications/${encodeURIComponent(id)}`, jsonInit('DELETE'))

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
      onNotification(parseNotification(JSON.parse(data), 'streamNotifications'))
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
