import type { AuditFilterValues, AuditLogQuery } from './types'

const textKeys = [
  'actor_user_id',
  'actor_email',
  'action',
  'resource_type',
  'resource_id',
  'status',
  'ip_address',
  'created_from',
  'created_to',
] as const

const trimmed = (value: unknown) => typeof value === 'string' ? value.trim() : ''

export function cleanAuditQuery(query: AuditLogQuery): AuditLogQuery {
  const cleaned: AuditLogQuery = {}
  if (query.page !== undefined) cleaned.page = Math.max(1, Number(query.page) || 1)
  if (query.limit !== undefined) cleaned.limit = Math.min(200, Math.max(1, Number(query.limit) || 25))
  textKeys.forEach((key) => {
    const value = trimmed(query[key])
    if (value) cleaned[key] = value
  })
  return cleaned
}

export function auditFormToQuery(values: AuditFilterValues, page: number, limit: number): AuditLogQuery {
  const [createdFrom, createdTo] = values.time_range ?? []
  return cleanAuditQuery({
    page,
    limit,
    actor_user_id: values.actor_user_id,
    actor_email: values.actor_email,
    action: values.action,
    resource_type: values.resource_type,
    resource_id: values.resource_id,
    status: values.status,
    ip_address: values.ip_address,
    created_from: createdFrom?.toISOString(),
    created_to: createdTo?.toISOString(),
  })
}

export function auditStatusColor(status?: string) {
  const normalized = trimmed(status).toLowerCase()
  if (['success', 'ok', 'allow', 'allowed'].includes(normalized)) return 'success'
  if (['failure', 'failed', 'error', 'denied', 'rejected'].includes(normalized)) return 'error'
  if (['pending', 'warning', 'warn'].includes(normalized)) return 'warning'
  return 'default'
}

export function hasAuditMetadata(metadata: unknown) {
  return metadata !== null && typeof metadata === 'object' && Object.keys(metadata).length > 0
}

export function initialAuditUserId() {
  const hash = window.location.hash
  const queryText = hash.includes('?') ? hash.slice(hash.indexOf('?') + 1) : window.location.search
  const params = new URLSearchParams(queryText)
  return params.get('actor_user_id') ?? params.get('user') ?? ''
}
