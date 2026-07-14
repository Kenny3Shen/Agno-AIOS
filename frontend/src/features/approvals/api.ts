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
  source_name?: string
  approval_type?: string
  pause_type?: string
  tool_name?: string
  tool_args?: Record<string, unknown>
  run_id?: string
  session_id?: string
  agent_id?: string
  team_id?: string
  workflow_id?: string
  user_id?: string
  schedule_id?: string
  created_at?: string | number
  updated_at?: string | number
  resource_type?: 'skill' | 'mcp' | string
  submitted_by?: ApprovalActor | string
  submitted_by_email?: string
  resolved_by?: ApprovalActor | string | null
  resolved_by_email?: string
  resolved_at?: string | number
  rejection_reason?: string | null
  resolution_data?: Record<string, unknown> | null
  run_status?: 'PAUSED' | 'RUNNING' | 'COMPLETED' | 'ERROR' | 'CANCELLED' | string | null
  payload?: Record<string, unknown>
}

export interface SkillSubmissionPreview {
  files: Array<{ name: string; size: number }>
  previews: Record<string, string>
  entry_count: number
}

export const isSubmissionApproval = (approval: Approval) =>
  approval.resource_type === 'skill' || approval.resource_type === 'mcp'

const asActor = (value: unknown): ApprovalActor | string | undefined => {
  if (value == null) return undefined
  if (typeof value === 'string') return value
  const row = asRecord(value)
  const id = String(row.id ?? '').trim()
  const email = String(row.email ?? '').trim()
  if (!id && !email) return undefined
  return { id, email }
}

/** Map Agno HITL / submission approval rows into UI records. */
export const normalizeApproval = (value: unknown): Approval | null => {
  const row = asRecord(value)
  const id = String(row.id ?? '').trim()
  if (!id) return null
  const toolArgs = row.tool_args
  const resolutionData = row.resolution_data
  const payload = row.payload
  return {
    id,
    status: String(row.status ?? ''),
    source_type: row.source_type != null ? String(row.source_type) : undefined,
    source_name: row.source_name != null ? String(row.source_name) : undefined,
    approval_type: row.approval_type != null ? String(row.approval_type) : undefined,
    pause_type: row.pause_type != null ? String(row.pause_type) : undefined,
    tool_name: row.tool_name != null ? String(row.tool_name) : undefined,
    tool_args:
      toolArgs && typeof toolArgs === 'object' && !Array.isArray(toolArgs)
        ? (toolArgs as Record<string, unknown>)
        : undefined,
    run_id: row.run_id != null ? String(row.run_id) : undefined,
    session_id: row.session_id != null ? String(row.session_id) : undefined,
    agent_id: row.agent_id != null ? String(row.agent_id) : undefined,
    team_id: row.team_id != null ? String(row.team_id) : undefined,
    workflow_id: row.workflow_id != null ? String(row.workflow_id) : undefined,
    user_id: row.user_id != null ? String(row.user_id) : undefined,
    schedule_id: row.schedule_id != null ? String(row.schedule_id) : undefined,
    created_at: row.created_at as string | number | undefined,
    updated_at: row.updated_at as string | number | undefined,
    resource_type: row.resource_type != null ? String(row.resource_type) : undefined,
    submitted_by: asActor(row.submitted_by),
    submitted_by_email: row.submitted_by_email != null ? String(row.submitted_by_email) : undefined,
    resolved_by: asActor(row.resolved_by) ?? null,
    resolved_by_email: row.resolved_by_email != null ? String(row.resolved_by_email) : undefined,
    resolved_at: row.resolved_at as string | number | undefined,
    rejection_reason: row.rejection_reason != null ? String(row.rejection_reason) : null,
    resolution_data:
      resolutionData && typeof resolutionData === 'object' && !Array.isArray(resolutionData)
        ? (resolutionData as Record<string, unknown>)
        : null,
    run_status: row.run_status != null ? String(row.run_status) : null,
    payload:
      payload && typeof payload === 'object' && !Array.isArray(payload)
        ? (payload as Record<string, unknown>)
        : undefined,
  }
}

export const getApprovals = async (status = '') => {
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  const shouldFetchSubmissions = !status || ['pending', 'approved', 'rejected'].includes(status)
  const [hitlPayload, submissions] = await Promise.all([
    requestJson<unknown>(`/approvals?limit=100${status ? `&status=${encodeURIComponent(status)}` : ''}`),
    shouldFetchSubmissions ? requestJson<unknown>(`/approvals/submissions${query}`) : Promise.resolve({ approvals: [] }),
  ])
  const hitl = asRecord(hitlPayload)
  const submissionData = asRecord(submissions)
  // HITL list: Agno-native { data, meta }. Submissions remain workbench { approvals }.
  const hitlRows = Array.isArray(hitl.data) ? hitl.data : []
  const submissionRows = asArray(submissionData.approvals)
  return [...submissionRows, ...hitlRows]
    .map((row) => normalizeApproval(row))
    .filter((row): row is Approval => row != null)
}

export const resolveApproval = (id: string, status: 'approved' | 'rejected', rejectionReason?: string) =>
  requestJson<Approval>(
    `/approvals/${encodeURIComponent(id)}/resolve`,
    jsonInit('POST', { status, ...(rejectionReason ? { rejection_reason: rejectionReason } : {}) })
  ).then((row) => normalizeApproval(row) ?? (row as Approval))

export const resumeApproval = (id: string) =>
  requestJson<Approval>(`/approvals/${encodeURIComponent(id)}/resume`, jsonInit('POST')).then(
    (row) => normalizeApproval(row) ?? (row as Approval)
  )

export const resolveSubmissionApproval = (id: string, status: 'approved' | 'rejected', rejectionReason?: string) =>
  requestJson<Approval>(
    `/approvals/submissions/${encodeURIComponent(id)}/resolve`,
    jsonInit('POST', { status, ...(rejectionReason ? { rejection_reason: rejectionReason } : {}) })
  ).then((row) => normalizeApproval(row) ?? (row as Approval))

export const getSkillSubmissionPreview = (id: string) =>
  requestJson<SkillSubmissionPreview>(`/approvals/submissions/${encodeURIComponent(id)}/skill-preview`)

export type ApprovalCountResult = {
  count: number
}

/** Pending HITL approval count (Agno-native ``{ count }``). */
export const getApprovalCount = async (userId?: string): Promise<number> => {
  const search = new URLSearchParams()
  if (userId) search.set('user_id', userId)
  const query = search.toString()
  const payload = asRecord(
    await requestJson<unknown>(`/approvals/count${query ? `?${query}` : ''}`)
  )
  const count = Number(payload.count ?? 0)
  if (!Number.isFinite(count) || count <= 0) return 0
  return Math.floor(count)
}

