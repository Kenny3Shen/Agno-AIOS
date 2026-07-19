import { requestJson } from '@/shared/api/client'
import { normalizePaginatedList } from '@/shared/lib/pagination'
import { cleanAuditQuery } from './utils'
import type { AuditLog, AuditLogQuery, AuditLogResponse } from './types'

export const auditKeys = {
  all: ['audit-logs'] as const,
  list: (query: AuditLogQuery) => [...auditKeys.all, cleanAuditQuery(query)] as const,
}

const isAuditId = (value: unknown): value is number | string =>
  (typeof value === 'number' && Number.isFinite(value)) ||
  (typeof value === 'string' && Boolean(value.trim()))

const isJsonRecord = (value: unknown): value is AuditLog['metadata'] =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value)

const parseAuditLog = (value: unknown, context: string): AuditLog => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${context}: invalid audit log payload`)
  }
  const row = value as Record<string, unknown>
  const id = row.id
  const metadata = row.metadata
  if (
    !isAuditId(id) ||
    typeof row.actor_user_id !== 'string' ||
    typeof row.actor_email !== 'string' ||
    typeof row.actor_role !== 'string' ||
    typeof row.action !== 'string' ||
    typeof row.resource_type !== 'string' ||
    typeof row.resource_id !== 'string' ||
    typeof row.status !== 'string' ||
    typeof row.ip_address !== 'string' ||
    typeof row.user_agent !== 'string' ||
    !isJsonRecord(metadata) ||
    typeof row.created_at !== 'string' ||
    !row.created_at.trim()
  ) {
    throw new Error(`${context}: invalid audit log payload`)
  }
  return {
    id,
    actor_user_id: row.actor_user_id,
    actor_email: row.actor_email,
    actor_role: row.actor_role,
    action: row.action,
    resource_type: row.resource_type,
    resource_id: row.resource_id,
    status: row.status,
    ip_address: row.ip_address,
    user_agent: row.user_agent,
    metadata,
    created_at: row.created_at,
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
    mapItem: (item) => parseAuditLog(item, 'getAuditLogs'),
  })
}
