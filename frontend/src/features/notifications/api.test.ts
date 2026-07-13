import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '@/test/server'
import { getNotifications, markNotificationRead } from './api'

describe('notifications API', () => {
  it('loads notifications and marks a notification as read', async () => {
    server.use(
      http.get('/api/notifications', () =>
        HttpResponse.json({
          notifications: [{ id: 7, title: 'Skill upload awaiting approval', body: 'Submitted by member@example.com', data: {}, read: false, created_at: 1 }],
          unread_count: 1,
        })
      ),
      http.post('/api/notifications/7/read', () => HttpResponse.json({ success: true }))
    )

    expect((await getNotifications()).unread_count).toBe(1)
    await expect(markNotificationRead(7)).resolves.toEqual({ success: true })
  })
})
