import { describe, expect, it } from 'vitest'
import { auditFormToQuery, auditStatusColor, cleanAuditQuery, hasAuditMetadata } from './utils'

describe('audit query helpers', () => {
  it('removes empty filters without dropping pagination', () => {
    expect(cleanAuditQuery({
      page: 2,
      limit: 25,
      actor_user_id: ' u1 ',
      actor_email: ' ',
      action: '',
      status: 'success',
    })).toEqual({ page: 2, limit: 25, actor_user_id: 'u1', status: 'success' })
  })

  it('converts selected time range into backend filter boundaries', () => {
    const createdFrom = { toISOString: () => '2026-01-01T00:00:00.000Z' }
    const createdTo = { toISOString: () => '2026-01-02T00:00:00.000Z' }

    expect(auditFormToQuery({
      actor_user_id: 'u1',
      time_range: [createdFrom, createdTo],
    }, 1, 50)).toEqual({
      page: 1,
      limit: 50,
      actor_user_id: 'u1',
      created_from: '2026-01-01T00:00:00.000Z',
      created_to: '2026-01-02T00:00:00.000Z',
    })
  })

  it('maps audit status and metadata presence for compact table display', () => {
    expect(auditStatusColor('success')).toBe('success')
    expect(auditStatusColor('denied')).toBe('error')
    expect(auditStatusColor('pending')).toBe('warning')
    expect(auditStatusColor('custom')).toBe('default')
    expect(hasAuditMetadata({ changed: true })).toBe(true)
    expect(hasAuditMetadata({})).toBe(false)
  })
})
