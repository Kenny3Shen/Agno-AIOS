import type { ListPaginationMeta } from '@/shared/lib/pagination'
import type { JsonRecord } from '@/shared/types/common'

export interface AuditLog {
  id: number | string
  actor_user_id: string
  actor_email: string
  actor_role: string
  action: string
  resource_type: string
  resource_id: string
  status: string
  ip_address: string
  user_agent: string
  metadata: JsonRecord
  created_at: string
}

export interface AuditLogQuery {
  page?: number
  limit?: number
  actor_user_id?: string
  actor_email?: string
  action?: string
  resource_type?: string
  resource_id?: string
  status?: string
  ip_address?: string
  created_from?: string
  created_to?: string
}

export type AuditLogResponse = {
  data: AuditLog[]
  meta: ListPaginationMeta
}

export interface AuditFilterValues {
  actor_user_id?: string
  actor_email?: string
  action?: string
  resource_type?: string
  resource_id?: string
  status?: string
  ip_address?: string
  time_range?: [{ toISOString: () => string } | null, { toISOString: () => string } | null] | null
}
