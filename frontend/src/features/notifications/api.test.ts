import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { setToken } from '@/shared/auth/storage'
import { server } from '@/test/server'
import { deleteNotification, getNotifications, markAllNotificationsRead, markNotificationRead, streamNotifications } from './api'

describe('notifications API', () => {
  it('loads notifications and marks a notification as read', async () => {
    server.use(
      http.get('/api/notifications', () =>
        HttpResponse.json({
          data: [{ id: 7, title: 'Skill upload awaiting approval', body: 'Submitted by member@example.com', data: {}, read: false, created_at: 1, read_at: null }],
          meta: { page: 1, limit: 100, total_pages: 1, total_count: 1, unread_count: 1, search_time_ms: 0 },
        })
      ),
      http.post('/api/notifications/7/read', () => HttpResponse.json({ success: true })),
      http.post('/api/notifications/read-all', () => HttpResponse.json({ updated_count: 1 }))
    )

    expect((await getNotifications()).meta.unread_count).toBe(1)
    await expect(markNotificationRead(7)).resolves.toEqual({ success: true })
    await expect(markAllNotificationsRead()).resolves.toEqual({ updated_count: 1 })
  })
  it('deletes a notification', async () => {
    server.use(http.delete('/api/notifications/7', () => HttpResponse.json({ success: true })))
    await expect(deleteNotification(7)).resolves.toEqual({ success: true })
  })

  it('rejects malformed REST notification rows instead of silently dropping them', async () => {
    server.use(
      http.get('/api/notifications', () =>
        HttpResponse.json({
          data: [{ id: 7, title: 'Missing body', data: {}, read: false, created_at: 1 }],
          meta: { page: 1, limit: 100, total_pages: 1, total_count: 1, unread_count: 1, search_time_ms: 0 },
        })
      )
    )

    await expect(getNotifications()).rejects.toThrow('getNotifications: invalid notification payload')
  })

  it('rejects malformed REST notification metadata', async () => {
    server.use(
      http.get('/api/notifications', () =>
        HttpResponse.json({
          data: [{ id: 7, title: 'Valid row', body: 'Completed', data: {}, read: false, created_at: 1, read_at: null }],
          meta: { page: 1, limit: 100, total_pages: 1, total_count: 1, unread_count: '1', search_time_ms: 0 },
        })
      )
    )

    await expect(getNotifications()).rejects.toThrow('getNotifications: invalid notification payload')
  })

  it('streams authenticated notification events after the supplied cursor', async () => {
    setToken('stream-token')
    let authorization = ''
    let cursor = ''
    server.use(
      http.get('/api/notifications/stream', ({ request }) => {
        authorization = request.headers.get('authorization') ?? ''
        cursor = new URL(request.url).searchParams.get('after_id') ?? ''
        return new HttpResponse(
          'event: notification.created\nid: 8\ndata: {"id":8,"title":"HITL resolved","body":"Completed","data":{"session_id":"session-1"},"read":false,"created_at":2,"read_at":null}\n\n',
          { headers: { 'Content-Type': 'text/event-stream' } }
        )
      })
    )
    const received: number[] = []

    await streamNotifications(7, (notification) => received.push(notification.id), new AbortController().signal)

    expect(authorization).toBe('Bearer stream-token')
    expect(cursor).toBe('7')
    expect(received).toEqual([8])
  })

  it('ignores malformed notification stream events', async () => {
    server.use(
      http.get('/api/notifications/stream', () =>
        new HttpResponse(
          'event: notification.created\nid: 8\ndata: {"id":8,"title":"Missing body","data":{},"read":false,"created_at":2,"read_at":null}\n\n',
          { headers: { 'Content-Type': 'text/event-stream' } }
        )
      )
    )
    const received: number[] = []

    await streamNotifications(7, (notification) => received.push(notification.id), new AbortController().signal)

    expect(received).toEqual([])
  })
})
