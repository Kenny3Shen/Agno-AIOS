import { queryOptions } from '@tanstack/react-query'
import { getHistory, getModels, listSessions } from './api'

export const chatKeys = { all: ['chat'] as const, sessionLists: ['chat', 'sessions'] as const, sessions: (includeArchived = false) => ['chat', 'sessions', { includeArchived }] as const, history: (id: string) => ['chat', 'history', id] as const, models: ['settings', 'models'] as const }
export const sessionsQuery = (includeArchived = false) => queryOptions({ queryKey: chatKeys.sessions(includeArchived), queryFn: () => listSessions(includeArchived) })
export const historyQuery = (id: string) => queryOptions({ queryKey: chatKeys.history(id), queryFn: () => getHistory(id), enabled: Boolean(id) })
export const modelsQuery = () => queryOptions({ queryKey: chatKeys.models, queryFn: getModels, staleTime: 60_000 })
