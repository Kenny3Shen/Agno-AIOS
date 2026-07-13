import { jsonInit, requestJson } from '@/shared/api/client'
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
