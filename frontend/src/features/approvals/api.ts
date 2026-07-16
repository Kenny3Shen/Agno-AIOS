import { jsonInit, requestJson } from '@/shared/api/client'
import { asRecord } from '@/shared/lib/format'

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
  resolved_by?: ApprovalActor | string | null
  resolved_at?: string | number
  /** Upload submissions only (workbench field). HITL reasons live in resolution_data.note. */
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

export type ApprovalKind = 'all' | 'workflow' | 'upload' | 'agent'

export interface ApprovalListParams {
  status?: string
  /** On-call filter: workflow HITL vs upload submissions vs chat agent HITL. */
  kind?: ApprovalKind
  page?: number
  limit?: number
}

export interface ApprovalListMeta {
  page: number
  limit: number
  total_count: number
  total_pages: number
  search_time_ms: number
}

/** Combined Approvals list (Agno-style ``{data, meta}``; server merge for kind=all). */
export interface ApprovalListResult {
  data: Approval[]
  meta: ApprovalListMeta
}

export const isSubmissionApproval = (approval: Approval) =>
  approval.resource_type === 'skill' || approval.resource_type === 'mcp'

/** Workflow Studio step HITL (not chat agent HITL, not upload). */
export const isWorkflowHitlApproval = (approval: Approval) =>
  approval.source_type === 'workflow' || Boolean(approval.workflow_id)

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

const normalizeRows = (rows: unknown[]): Approval[] =>
  rows.map((row) => normalizeApproval(row)).filter((row): row is Approval => row != null)

const listMeta = (
  page: number,
  limit: number,
  totalCount: number,
  searchTimeMs = 0
): ApprovalListMeta => {
  const safePage = Math.max(1, page)
  const safeLimit = Math.max(1, limit)
  const total = Math.max(0, totalCount)
  return {
    page: safePage,
    limit: safeLimit,
    total_count: total,
    total_pages: total ? Math.ceil(total / safeLimit) : 0,
    search_time_ms: searchTimeMs,
  }
}

const fetchHitlPage = async (
  status: string,
  page: number,
  limit: number,
  sourceType?: string,
): Promise<{ data: Approval[]; total_count: number }> => {
  const search = new URLSearchParams()
  search.set('page', String(page))
  search.set('limit', String(limit))
  if (status) search.set('status', status)
  if (sourceType) search.set('source_type', sourceType)
  const payload = asRecord(await requestJson<unknown>(`/approvals?${search.toString()}`))
  const meta = asRecord(payload.meta)
  const rows = Array.isArray(payload.data) ? payload.data : []
  return {
    data: normalizeRows(rows),
    total_count: Number(meta.total_count ?? 0) || 0,
  }
}

const fetchSubmissionsPage = async (
  status: string,
  page: number,
  limit: number,
): Promise<{ data: Approval[]; total_count: number }> => {
  const shouldFetch = !status || ['pending', 'approved', 'rejected'].includes(status)
  if (!shouldFetch) {
    return { data: [], total_count: 0 }
  }
  const search = new URLSearchParams()
  if (status) search.set('status', status)
  search.set('page', String(page))
  search.set('limit', String(limit))
  const payload = asRecord(await requestJson<unknown>(`/approvals/submissions?${search}`))
  const meta = asRecord(payload.meta)
  const rows = Array.isArray(payload.data) ? payload.data : []
  return {
    data: normalizeRows(rows),
    total_count: Number(meta.total_count ?? rows.length) || 0,
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
    const submissions = await fetchSubmissionsPage(status, page, limit)
    return {
      data: submissions.data,
      meta: listMeta(page, limit, submissions.total_count),
    }
  }

  if (kind === 'workflow' || kind === 'agent') {
    const hitl = await fetchHitlPage(status, page, limit, kind)
    return {
      data: hitl.data,
      meta: listMeta(page, limit, hitl.total_count),
    }
  }

  const search = new URLSearchParams()
  if (status) search.set('status', status)
  search.set('combined', 'true')
  search.set('page', String(page))
  search.set('limit', String(limit))
  const payload = asRecord(await requestJson<unknown>(`/approvals?${search.toString()}`))
  const meta = asRecord(payload.meta)
  const data = normalizeRows(Array.isArray(payload.data) ? payload.data : [])
  const total = Number(meta.total_count ?? data.length) || 0
  return {
    data,
    meta: listMeta(page, limit, total, Number(meta.search_time_ms ?? 0) || 0),
  }
}


export const getApproval = async (id: string): Promise<Approval | null> => {
  const row = await requestJson<unknown>(`/approvals/${encodeURIComponent(id)}`)
  return normalizeApproval(row)
}

export type ResolveApprovalOptions = {
  rejectionReason?: string
  resolutionData?: Record<string, unknown>
}

const requireApproval = (row: unknown, context: string): Approval => {
  const normalized = normalizeApproval(row)
  if (!normalized) {
    throw new Error(`${context}: invalid approval payload`)
  }
  return normalized
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
  return requireApproval(row, 'resolveApproval')
}

export const resumeApproval = async (id: string): Promise<Approval> => {
  const row = await requestJson<unknown>(`/approvals/${encodeURIComponent(id)}/resume`, jsonInit('POST'))
  return requireApproval(row, 'resumeApproval')
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
  return requireApproval(row, 'resolveSubmissionApproval')
}

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
