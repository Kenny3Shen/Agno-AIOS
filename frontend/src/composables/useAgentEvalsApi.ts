import { ref } from 'vue'
import { apiFetch } from '../lib/apiClient'
import { useApiMessage, messageFromUnknown, messageFromResponse } from './useApiCore'
import type {
  AgentEvalAgnoRun,
  AgentEvalCase,
  AgentEvalCaseCreateRequest,
  AgentEvalCaseRun,
  AgentEvalFailureResponse,
  AgentEvalSuite,
  AgentEvalSuiteCreateRequest,
  AgentEvalSuiteRun,
  AgentEvalTrendResponse,
  AgentEvalType
} from '../types'

/**
 * Agent evaluation API.
 */
export function useAgentEvalsApi() {
  const apiMessage = useApiMessage()
  const loading = ref(false)
  const error = ref<string | null>(null)
  const fallback = apiMessage('agentEvalsRequestFailed')
  const paths = {
    suites: '/agent-evals/suites',
    cases: '/agent-evals/cases',
    caseRuns: '/agent-evals/case-runs',
    agnoRuns: '/agent-evals/agno-runs',
    trends: '/agent-evals/trends',
    failures: '/agent-evals/failures'
  } as const

  const request = async <T>(path: string, options: RequestInit = {}): Promise<T> => {
    loading.value = true
    error.value = null
    try {
      const response = await apiFetch(path, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...(options.headers || {})
        }
      })
      if (!response.ok) {
        const data: unknown = await response.json().catch(() => ({}))
        throw new Error(messageFromResponse(data, fallback))
      }
      return await response.json()
    } catch (err: unknown) {
      error.value = messageFromUnknown(err, fallback)
      throw err
    } finally {
      loading.value = false
    }
  }

  const queryString = (params: Record<string, string | number | boolean | string[] | undefined | null>) => {
    const query = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === '') continue
      if (Array.isArray(value)) {
        for (const item of value) {
          if (item) query.append(key, item)
        }
      } else {
        query.set(key, String(value))
      }
    }
    return query.toString()
  }

  const withQuery = (path: string, params: Record<string, string | number | boolean | string[] | undefined | null>) => {
    const query = queryString(params)
    return query ? `${path}?${query}` : path
  }

  const listSuites = (params: { enabled?: boolean } = {}) => {
    return request<AgentEvalSuite[]>(withQuery(paths.suites, params))
  }

  const createSuite = (payload: AgentEvalSuiteCreateRequest) => request<AgentEvalSuite>(paths.suites, {
    method: 'POST',
    body: JSON.stringify(payload)
  })

  const listCases = (params: { suite_id?: string; enabled?: boolean } = {}) => {
    return request<AgentEvalCase[]>(withQuery(paths.cases, params))
  }

  const createCase = (payload: AgentEvalCaseCreateRequest) => request<AgentEvalCase>(paths.cases, {
    method: 'POST',
    body: JSON.stringify(payload)
  })

  const runSuite = (id: string) => {
    return request<AgentEvalSuiteRun>(`${paths.suites}/${encodeURIComponent(id)}/runs`, { method: 'POST' })
  }

  const runCase = (id: string) => {
    return request<AgentEvalCaseRun>(`${paths.cases}/${encodeURIComponent(id)}/runs`, { method: 'POST' })
  }

  const replayCaseRun = (id: string) => {
    return request<AgentEvalCaseRun>(`${paths.caseRuns}/${encodeURIComponent(id)}/replay`, { method: 'POST' })
  }

  const listAgnoRuns = (params: {
    limit?: number
    page?: number
    eval_type?: AgentEvalType[]
    agent_id?: string
  } = {}) => {
    return request<{
      items: AgentEvalAgnoRun[]
      total: number
      limit: number
      page: number
      trends: AgentEvalTrendResponse
    }>(withQuery(paths.agnoRuns, params))
  }

  const getAgnoRun = (id: string) => {
    return request<AgentEvalAgnoRun>(`${paths.agnoRuns}/${encodeURIComponent(id)}`)
  }

  const getTrends = (params: {
    limit?: number
    page?: number
    eval_type?: AgentEvalType[]
    agent_id?: string
  } = {}) => {
    return request<AgentEvalTrendResponse>(withQuery(paths.trends, params))
  }

  const listFailures = (params: { limit?: number } = {}) => {
    return request<AgentEvalFailureResponse>(withQuery(paths.failures, params))
  }

  return {
    loading,
    error,
    listSuites,
    createSuite,
    listCases,
    createCase,
    runSuite,
    runCase,
    replayCaseRun,
    listAgnoRuns,
    getAgnoRun,
    getTrends,
    listFailures
  }
}
