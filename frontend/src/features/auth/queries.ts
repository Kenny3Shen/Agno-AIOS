import { queryOptions } from '@tanstack/react-query'
import { getCurrentUser } from './api'

export const authKeys = { current: ['auth', 'current-user'] as const }
export const currentUserQuery = () => queryOptions({ queryKey: authKeys.current, queryFn: getCurrentUser, staleTime: 60_000 })
