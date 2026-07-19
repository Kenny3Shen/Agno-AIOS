import { requestJson } from '@/shared/api/client'
import { asRecord } from '@/shared/lib/format'
import { normalizePaginatedList, type ListPaginationMeta } from '@/shared/lib/pagination'

interface Suite {
  id: string
  name: string
  description?: string
  target_agent_id?: string
  enabled: boolean
  tags?: string[]
}

export interface EvalCase {
  id: string
  suite_id: string
  name: string
  description?: string
  input: string
  expected_output?: string
  criteria?: string
  enabled: boolean
}

export interface EvalRun {
  id: string
  name?: string
  eval_type?: string
  passed?: boolean | null
  score?: number
  agent_id?: string
  created_at?: string | number
  eval_data?: Record<string, unknown>
  eval_input?: Record<string, unknown>
  case_run_id?: string
  case_id?: string
  suite_run_id?: string
}

/** Parse canonical Agno eval-run rows for the UI. */
const parseEvalRun = (value: unknown, context: string): EvalRun => {
  const row = asRecord(value)
  const id = String(row.id ?? '').trim()
  if (!id) throw new Error(`${context}: invalid eval run payload`)
  const evalDataRaw = row.eval_data
  const evalData =
    evalDataRaw && typeof evalDataRaw === 'object' && !Array.isArray(evalDataRaw)
      ? (evalDataRaw as Record<string, unknown>)
      : undefined
  const evalInputRaw = row.eval_input
  const evalInput =
    evalInputRaw && typeof evalInputRaw === 'object' && !Array.isArray(evalInputRaw)
      ? (evalInputRaw as Record<string, unknown>)
      : undefined
  const passedRaw = row.passed
  const passed =
    typeof passedRaw === 'boolean'
      ? passedRaw
      : passedRaw == null
        ? null
        : undefined
  const scoreRaw = row.score
  const score =
    typeof scoreRaw === 'number'
      ? scoreRaw
      : typeof scoreRaw === 'string' && scoreRaw.trim()
        ? Number(scoreRaw)
        : undefined
  return {
    id,
    name: row.name != null ? String(row.name) : undefined,
    eval_type: row.eval_type != null ? String(row.eval_type) : undefined,
    passed,
    score: score != null && Number.isFinite(score) ? score : undefined,
    agent_id: row.agent_id != null ? String(row.agent_id) : undefined,
    created_at: row.created_at as string | number | undefined,
    eval_data: evalData,
    eval_input: evalInput,
    case_run_id: row.case_run_id != null ? String(row.case_run_id) : undefined,
    case_id: row.case_id != null ? String(row.case_id) : undefined,
    suite_run_id: row.suite_run_id != null ? String(row.suite_run_id) : undefined,
  }
}

export const listSuites = async () => {
  return (await requestJson<{ data: Suite[] }>('/agent-evals/suites')).data
}

export const listCases = async (suite = '') => {
  const payload = await requestJson<{ data: EvalCase[] }>(
    `/agent-evals/cases${suite ? `?suite_id=${encodeURIComponent(suite)}` : ''}`,
  )
  return payload.data
}

type EvalListMeta = ListPaginationMeta

type EvalListResult = {
  data: EvalRun[]
  meta: EvalListMeta
}

export const listRuns = async (params: { page?: number; limit?: number } = {}): Promise<EvalListResult> => {
  const page = Math.max(1, params.page ?? 1)
  const limit = Math.min(100, Math.max(1, params.limit ?? 20))
  const search = new URLSearchParams({ page: String(page), limit: String(limit) })
  const payload = await requestJson<unknown>(`/agent-evals/agno-runs?${search}`)
  return normalizePaginatedList(payload, {
    mapItem: (item) => parseEvalRun(item, 'listRuns'),
  })
}

export const listFailures = async (params: { limit?: number } = {}): Promise<EvalRun[]> => {
  const limit = Math.min(100, Math.max(1, params.limit ?? 50))
  const raw = await requestJson<unknown>(`/agent-evals/failures?limit=${limit}`)
  const { data } = normalizePaginatedList(raw, {
    mapItem: (item) => parseEvalRun(item, 'listFailures'),
  })
  return data
}

export const runSuite = (id: string) =>
  requestJson(`/agent-evals/suites/${encodeURIComponent(id)}/runs`, { method: 'POST' })

export const runCase = (id: string) =>
  requestJson(`/agent-evals/cases/${encodeURIComponent(id)}/runs`, { method: 'POST' })

export const replay = (id: string) =>
  requestJson(`/agent-evals/case-runs/${encodeURIComponent(id)}/replay`, { method: 'POST' })
