import { jsonInit, requestJson } from '@/shared/api/client'
import { asArray, asRecord } from '@/shared/lib/format'

export interface ApprovalActor {
  id: string
  email: string
}

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
  resource_type?: 'skill' | 'mcp' | string
  submitted_by?: ApprovalActor | string
  submitted_by_email?: string
  resolved_by?: ApprovalActor | string | null
  resolved_by_email?: string
  resolved_at?: string | number
  rejection_reason?: string | null
  resolution_data?: Record<string, unknown> | null
  payload?: Record<string, unknown>
}

export interface SkillSubmissionPreview {
  files: Array<{ name: string; size: number }>
  previews: Record<string, string>
  entry_count: number
}

export const isSubmissionApproval = (approval: Approval) => approval.resource_type === 'skill' || approval.resource_type === 'mcp'

export const getApprovals = async (status = '') => {
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  const shouldFetchSubmissions = !status || ['pending', 'approved', 'rejected'].includes(status)
  const [data, submissions] = await Promise.all([
    requestJson<unknown>(`/approvals?limit=100${status ? `&status=${encodeURIComponent(status)}` : ''}`),
    shouldFetchSubmissions ? requestJson<unknown>(`/approvals/submissions${query}`) : Promise.resolve({ approvals: [] }),
  ])
  const approvalData = asRecord(data)
  const submissionData = asRecord(submissions)
  return [...asArray<Approval>(submissionData.approvals), ...asArray<Approval>(approvalData.approvals ?? approvalData.items)]
}
export const resolveApproval = (id: string, status: 'approved' | 'rejected', rejectionReason?: string) =>
  requestJson<Approval>(
    `/approvals/${encodeURIComponent(id)}/resolve`,
    jsonInit('POST', { status, ...(rejectionReason ? { rejection_reason: rejectionReason } : {}) })
  )
export const resolveSubmissionApproval = (id: string, status: 'approved' | 'rejected', rejectionReason?: string) =>
  requestJson<Approval>(
    `/approvals/submissions/${encodeURIComponent(id)}/resolve`,
    jsonInit('POST', { status, ...(rejectionReason ? { rejection_reason: rejectionReason } : {}) })
  )
export const getSkillSubmissionPreview = (id: string) =>
  requestJson<SkillSubmissionPreview>(`/approvals/submissions/${encodeURIComponent(id)}/skill-preview`)
