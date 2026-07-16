import { requestJson } from '@/shared/api/client'
import { normalizePaginatedList } from '@/shared/lib/pagination'
import { cleanAuditQuery } from './utils'
import type { AuditLog, AuditLogQuery, AuditLogResponse } from './types'

export const auditKeys = {
  all: ['audit-logs'] as const,
  list: (query: AuditLogQuery) => [...auditKeys.all, cleanAuditQuery(query)] as const,
}

const normalizeAuditLog = (value: unknown): AuditLog | null => {
  if (!value || typeof value !== 'object') return null
  const row = value as Record<string, unknown>
  if (row.id == null) return null
  return {
    id: row.id as number | string,
    actor_user_id: String(row.actor_user_id ?? ''),
    actor_email: String(row.actor_email ?? ''),
    actor_role: String(row.actor_role ?? ''),
    action: String(row.action ?? ''),
    resource_type: String(row.resource_type ?? ''),
    resource_id: String(row.resource_id ?? ''),
    status: String(row.status ?? ''),
    ip_address: String(row.ip_address ?? ''),
    user_agent: String(row.user_agent ?? ''),
    metadata:
      row.metadata && typeof row.metadata === 'object' && !Array.isArray(row.metadata)
        ? (row.metadata as AuditLog['metadata'])
        : {},
    created_at: String(row.created_at ?? ''),
  }
}

export async function getAuditLogs(query: AuditLogQuery = {}): Promise<AuditLogResponse> {
  const search = new URLSearchParams()
  Object.entries(cleanAuditQuery(query)).forEach(([key, value]) => {
    if (value !== undefined) search.set(key, String(value))
  })
  const queryString = search.toString()
  const raw = await requestJson<unknown>(`/audit/logs${queryString ? `?${queryString}` : ''}`)
  return normalizePaginatedList(raw, {
    page: query.page ?? 1,
    limit: query.limit ?? 20,
    mapItem: normalizeAuditLog,
  })
}
