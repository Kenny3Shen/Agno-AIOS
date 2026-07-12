import { queryOptions } from '@tanstack/react-query'
import { getTrace, listTraceSessions, listTraces } from './api'
export const traceKeys = { all: ['traces'] as const, list: (params: Record<string, unknown>) => ['traces', 'list', params] as const, sessions: (params: Record<string, unknown>) => ['traces', 'sessions', params] as const, detail: (id: string) => ['traces', 'detail', id] as const }
export const tracesQuery = (params: Record<string, string | number | undefined>) => queryOptions({ queryKey: traceKeys.list(params), queryFn: () => listTraces(params) })
export const traceSessionsQuery = (params: Record<string, string | number | undefined>) => queryOptions({ queryKey: traceKeys.sessions(params), queryFn: () => listTraceSessions(params) })
export const traceQuery = (id: string) => queryOptions({ queryKey: traceKeys.detail(id), queryFn: () => getTrace(id), enabled: Boolean(id) })
