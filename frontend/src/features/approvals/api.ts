import { ApiError, jsonInit, requestJson } from '@/shared/api/client'
import { asRecord } from '@/shared/lib/format'
import { listPaginationMeta, normalizePaginatedList, type ListPaginationMeta } from '@/shared/lib/pagination'

interface ApprovalActor {
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
  submitted_by?: ApprovalActor
  resolved_by?: ApprovalActor | null
  resolved_at?: string | number
  /** Upload submissions only (workbench field). HITL reasons live in resolution_data.note. */
  rejection_reason?: string | null
  resolution_data?: Record<string, unknown> | null
  run_status?: 'PAUSED' | 'RUNNING' | 'COMPLETED' | 'ERROR' | 'CANCELLED' | string | null
  payload?: Record<string, unknown>
}

interface SkillSubmissionPreview {
  files: Array<{ name: string; size: number }>
  previews: Record<string, string>
  entry_count: number
}

export type ApprovalKind = 'all' | 'workflow' | 'upload' | 'agent'

interface ApprovalListParams {
  status?: string
  /** On-call filter: workflow HITL vs upload submissions vs chat agent HITL. */
  kind?: ApprovalKind
  page?: number
  limit?: number
}

type ApprovalListMeta = ListPaginationMeta

/** Combined Approvals list (Agno-style ``{data, meta}``; server merge for kind=all). */
type ApprovalListResult = {
  data: Approval[]
  meta: ApprovalListMeta
}

export const isSubmissionApproval = (approval: Approval) =>
  approval.resource_type === 'skill' || approval.resource_type === 'mcp'

/** Workflow Studio step HITL (not chat agent HITL, not upload). */
export const isWorkflowHitlApproval = (approval: Approval) =>
  approval.source_type === 'workflow' || Boolean(approval.workflow_id)

const asActor = (value: unknown): ApprovalActor | undefined => {
  const row = asRecord(value)
  const id = String(row.id ?? '').trim()
  const email = String(row.email ?? '').trim()
  if (!id && !email) return undefined
  return { id, email }
}

/** Parse canonical Agno HITL / submission approval rows for the UI. */
const parseApproval = (value: unknown, context: string): Approval => {
  const row = asRecord(value)
  const id = String(row.id ?? '').trim()
  if (!id) throw new Error(`${context}: invalid approval payload`)
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
    resolved_by: asActor(row.resolved_by) ?? null,
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


/**
 * Approvals list with real pagination.
 * ``kind=all`` uses server ``combined=true`` (uploads then HITL).
 */
export const getApprovals = async (params: ApprovalListParams = {}): Promise<ApprovalListResult> => {
  const status = params.status ?? ''
  const kind: ApprovalKind = params.kind ?? 'all'
  const page = Math.max(1, Number(params.page ?? 1) || 1)
  const limit = Math.min(100, Math.max(1, Number(params.limit ?? 20) || 20))

  if (kind === 'upload') {
    if (status && !['pending', 'approved', 'rejected'].includes(status)) {
      return { data: [], meta: listPaginationMeta(page, limit, 0) }
    }
    const search = new URLSearchParams()
    if (status) search.set('status', status)
    search.set('page', String(page))
    search.set('limit', String(limit))
    return normalizePaginatedList(await requestJson<unknown>(`/approvals/submissions?${search}`), {
      mapItem: (item) => parseApproval(item, 'getApprovals'),
    })
  }

  if (kind === 'workflow' || kind === 'agent') {
    const search = new URLSearchParams()
    search.set('page', String(page))
    search.set('limit', String(limit))
    if (status) search.set('status', status)
    search.set('source_type', kind)
    return normalizePaginatedList(await requestJson<unknown>(`/approvals?${search.toString()}`), {
      mapItem: (item) => parseApproval(item, 'getApprovals'),
    })
  }

  const search = new URLSearchParams()
  if (status) search.set('status', status)
  search.set('combined', 'true')
  search.set('page', String(page))
  search.set('limit', String(limit))
  return normalizePaginatedList(await requestJson<unknown>(`/approvals?${search.toString()}`), {
    mapItem: (item) => parseApproval(item, 'getApprovals'),
  })
}


export const getApproval = async (id: string): Promise<Approval | null> => {
  try {
    const row = await requestJson<unknown>(`/approvals/${encodeURIComponent(id)}`)
    return parseApproval(row, 'getApproval')
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}

type ResolveApprovalOptions = {
  rejectionReason?: string
  resolutionData?: Record<string, unknown>
}

export const resolveApproval = async (
  id: string,
  status: 'approved' | 'rejected',
  options: ResolveApprovalOptions = {},
): Promise<Approval> => {
  const row = await requestJson<unknown>(
    `/approvals/${encodeURIComponent(id)}/resolve`,
    jsonInit('POST', {
      status,
      ...(options.rejectionReason ? { rejection_reason: options.rejectionReason } : {}),
      ...(options.resolutionData ? { resolution_data: options.resolutionData } : {}),
    }),
  )
  return parseApproval(row, 'resolveApproval')
}

export const resumeApproval = async (id: string): Promise<Approval> => {
  const row = await requestJson<unknown>(`/approvals/${encodeURIComponent(id)}/resume`, jsonInit('POST'))
  return parseApproval(row, 'resumeApproval')
}

export const resolveSubmissionApproval = async (
  id: string,
  status: 'approved' | 'rejected',
  rejectionReason?: string,
): Promise<Approval> => {
  const row = await requestJson<unknown>(
    `/approvals/submissions/${encodeURIComponent(id)}/resolve`,
    jsonInit('POST', { status, ...(rejectionReason ? { rejection_reason: rejectionReason } : {}) }),
  )
  return parseApproval(row, 'resolveSubmissionApproval')
}

export const getSkillSubmissionPreview = (id: string) =>
  requestJson<SkillSubmissionPreview>(`/approvals/submissions/${encodeURIComponent(id)}/skill-preview`)

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
