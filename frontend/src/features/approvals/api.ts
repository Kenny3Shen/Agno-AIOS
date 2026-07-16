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

export interface ApprovalListResult {
  items: Approval[]
  total: number
  page: number
  limit: number
}

export const isSubmissionApproval = (approval: Approval) =>
  approval.resource_type === 'skill' || approval.resource_type === 'mcp'

/** Workflow Studio step HITL (not chat agent HITL, not upload). */
export const isWorkflowHitlApproval = (approval: Approval) =>
  approval.source_type === 'workflow' || Boolean(approval.workflow_id)

/** Chat / agent tool HITL. */
export const isAgentHitlApproval = (approval: Approval) =>
  !isSubmissionApproval(approval) && !isWorkflowHitlApproval(approval)

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

const fetchHitlPage = async (
  status: string,
  page: number,
  limit: number,
  sourceType?: string
) => {
  const search = new URLSearchParams()
  search.set('page', String(page))
  search.set('limit', String(limit))
  if (status) search.set('status', status)
  if (sourceType) search.set('source_type', sourceType)
  const payload = asRecord(await requestJson<unknown>(`/approvals?${search.toString()}`))
  const meta = asRecord(payload.meta)
  const rows = Array.isArray(payload.data) ? payload.data : []
  return {
    items: normalizeRows(rows),
    total: Number(meta.total_count ?? 0) || 0,
    page: Number(meta.page ?? page) || page,
    limit: Number(meta.limit ?? limit) || limit,
  }
}

/**
 * Fetch a HITL slice by absolute offset (for merging with submissions).
 * Uses Agno page/limit and local slice when offset is not page-aligned.
 */
const fetchHitlSlice = async (
  status: string,
  offset: number,
  count: number,
  sourceType?: string
) => {
  if (count <= 0) {
    const probe = await fetchHitlPage(status, 1, 1, sourceType)
    return { items: [] as Approval[], total: probe.total }
  }
  const safeOffset = Math.max(0, offset)
  const pageSize = count
  const apiPage = Math.floor(safeOffset / pageSize) + 1
  const skip = safeOffset % pageSize
  const first = await fetchHitlPage(status, apiPage, pageSize, sourceType)
  let rows = first.items.slice(skip)
  if (rows.length < count && safeOffset + rows.length < first.total) {
    const second = await fetchHitlPage(status, apiPage + 1, pageSize, sourceType)
    rows = [...rows, ...second.items].slice(0, count)
  } else {
    rows = rows.slice(0, count)
  }
  return { items: rows, total: first.total }
}

const fetchSubmissionsPage = async (status: string, page: number, limit: number) => {
  const shouldFetch = !status || ['pending', 'approved', 'rejected'].includes(status)
  if (!shouldFetch) {
    return { items: [] as Approval[], total: 0 }
  }
  const search = new URLSearchParams()
  if (status) search.set('status', status)
  search.set('page', String(page))
  search.set('limit', String(limit))
  const payload = asRecord(await requestJson<unknown>(`/approvals/submissions?${search}`))
  const meta = asRecord(payload.meta)
  const rows = Array.isArray(payload.data) ? payload.data : []
  return {
    items: normalizeRows(rows),
    total: Number(meta.total_count ?? rows.length) || 0,
  }
}

/** Absolute-offset slice of upload submissions (for virtual merge with HITL). */
const fetchSubmissionsSlice = async (status: string, offset: number, limit: number) => {
  if (limit <= 0) return { items: [] as Approval[], total: 0 }
  const pageSize = Math.min(100, Math.max(limit, 1))
  const startPage = Math.floor(offset / pageSize) + 1
  const page = await fetchSubmissionsPage(status, startPage, pageSize)
  const localStart = offset % pageSize
  return {
    items: page.items.slice(localStart, localStart + limit),
    total: page.total,
  }
}

/**
 * Combined Approvals list with real pagination.
 * Virtual order: upload submissions first, then Agno HITL rows.
 */
export const getApprovals = async (params: ApprovalListParams = {}): Promise<ApprovalListResult> => {
  const status = params.status ?? ''
  const kind: ApprovalKind = params.kind ?? 'all'
  const page = Math.max(1, Number(params.page ?? 1) || 1)
  const limit = Math.min(100, Math.max(1, Number(params.limit ?? 20) || 20))
  const start = (page - 1) * limit

  // Upload-only tab: skip Agno HITL merge.
  if (kind === 'upload') {
    const submissions = await fetchSubmissionsSlice(status, start, limit)
    return {
      items: submissions.items,
      total: submissions.total,
      page,
      limit,
    }
  }

  // Workflow HITL only (source_type=workflow).
  if (kind === 'workflow') {
    const hitl = await fetchHitlSlice(status, start, limit, 'workflow')
    return {
      items: hitl.items,
      total: hitl.total,
      page,
      limit,
    }
  }

  // Chat/agent HITL: client-filter non-workflow HITL (bounded scan).
  if (kind === 'agent') {
    const window: Approval[] = []
    let apiPage = 1
    let totalSeen = 0
    let hitlTotal = 0
    while (window.length < start + limit && apiPage <= 20) {
      const batch = await fetchHitlPage(status, apiPage, 50)
      hitlTotal = batch.total
      if (!batch.items.length) break
      for (const row of batch.items) {
        totalSeen += 1
        if (!isAgentHitlApproval(row)) continue
        window.push(row)
        if (window.length >= start + limit) break
      }
      if (batch.items.length < 50) break
      apiPage += 1
    }
    // Rough total: filtered density on scanned pages applied to overall HITL total.
    const scanned = Math.max(totalSeen, 1)
    const density = window.length / scanned
    const total = Math.max(window.length, Math.round(hitlTotal * density))
    return {
      items: window.slice(start, start + limit),
      total,
      page,
      limit,
    }
  }

  // kind === 'all': virtual merge uploads first, then all HITL.
  const submissions = await fetchSubmissionsSlice(status, start, limit)
  const submissionCount = submissions.total
  const pageSubmissions = submissions.items
  const hitlNeed = limit - pageSubmissions.length
  const hitlOffset = Math.max(0, start - submissionCount)
  const hitl = await fetchHitlSlice(status, hitlOffset, Math.max(hitlNeed, 0))

  return {
    items: [...pageSubmissions, ...hitl.items.slice(0, Math.max(hitlNeed, 0))],
    total: submissionCount + hitl.total,
    page,
    limit,
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

export const resolveApproval = (
  id: string,
  status: 'approved' | 'rejected',
  rejectionReasonOrOptions?: string | ResolveApprovalOptions
) => {
  const options: ResolveApprovalOptions =
    typeof rejectionReasonOrOptions === 'string' || rejectionReasonOrOptions == null
      ? { rejectionReason: rejectionReasonOrOptions }
      : rejectionReasonOrOptions
  return requestJson<Approval>(
    `/approvals/${encodeURIComponent(id)}/resolve`,
    jsonInit('POST', {
      status,
      ...(options.rejectionReason ? { rejection_reason: options.rejectionReason } : {}),
      ...(options.resolutionData ? { resolution_data: options.resolutionData } : {}),
    })
  ).then((row) => normalizeApproval(row) ?? (row as Approval))
}

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
