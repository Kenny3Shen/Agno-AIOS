import { jsonInit, requestJson } from '@/shared/api/client'
import { asArray, asRecord } from '@/shared/lib/format'
export interface Approval {
  id: string
  status: string
  source_type?: string
  approval_type?: string
  tool_name?: string
  tool_args?: Record<string, unknown>
  run_id?: string
  session_id?: string
  created_at?: string
  updated_at?: string
}
export const getApprovals = async (status = '') => {
  const data = asRecord(await requestJson<unknown>(`/approvals?limit=100${status ? `&status=${status}` : ''}`))
  return asArray<Approval>(data.approvals ?? data.items)
}
export const resolveApproval = (id: string, status: 'approved' | 'rejected') =>
  requestJson<Approval>(`/approvals/${encodeURIComponent(id)}/resolve`, jsonInit('POST', { status }))
