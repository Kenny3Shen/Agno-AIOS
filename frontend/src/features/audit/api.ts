import { requestJson } from '@/shared/api/client'
import { cleanAuditQuery } from './utils'
import type { AuditLogQuery, AuditLogResponse } from './types'

export const auditKeys = {
  all: ['audit-logs'] as const,
  list: (query: AuditLogQuery) => [...auditKeys.all, cleanAuditQuery(query)] as const,
}

export function getAuditLogs(query: AuditLogQuery = {}) {
  const search = new URLSearchParams()
  Object.entries(cleanAuditQuery(query)).forEach(([key, value]) => {
    if (value !== undefined) search.set(key, String(value))
  })
  const queryString = search.toString()
  return requestJson<AuditLogResponse>(`/audit/logs${queryString ? `?${queryString}` : ''}`)
}
