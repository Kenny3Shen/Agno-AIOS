import { jsonInit, requestJson } from '@/shared/api/client'
import { asArray, asRecord } from '@/shared/lib/format'
export interface Suite {
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
  run_id?: string
  name?: string
  eval_type?: string
  passed?: boolean
  score?: number
  agent_id?: string
  created_at?: string
  data?: Record<string, unknown>
}
export const listSuites = () => requestJson<Suite[]>('/agent-evals/suites')
export const listCases = (suite = '') =>
  requestJson<EvalCase[]>(`/agent-evals/cases${suite ? `?suite_id=${encodeURIComponent(suite)}` : ''}`)
export const listRuns = async () => {
  const data = asRecord(await requestJson<unknown>('/agent-evals/agno-runs?limit=100&page=1'))
  return asArray<EvalRun>(data.items)
}
export const listFailures = async () => {
  const data = await requestJson<unknown>('/agent-evals/failures?limit=100')
  return asArray<EvalRun>(Array.isArray(data) ? data : asRecord(data).items)
}
export const runSuite = (id: string) => requestJson(`/agent-evals/suites/${encodeURIComponent(id)}/runs`, { method: 'POST' })
export const runCase = (id: string) => requestJson(`/agent-evals/cases/${encodeURIComponent(id)}/runs`, { method: 'POST' })
export const replay = (id: string) => requestJson(`/agent-evals/case-runs/${encodeURIComponent(id)}/replay`, { method: 'POST' })
export const createSuite = (payload: Partial<Suite>) => requestJson<Suite>('/agent-evals/suites', jsonInit('POST', payload))
export const createCase = (payload: Partial<EvalCase>) => requestJson<EvalCase>('/agent-evals/cases', jsonInit('POST', payload))
