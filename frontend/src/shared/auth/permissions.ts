import type { AuthUser, UserRole } from '@/shared/types/auth'

export const roleOf = (user: AuthUser | null | undefined): UserRole => {
  if (user?.is_superuser) return 'admin'
  return user?.role ?? 'guest'
}

export const hasScope = (user: AuthUser | null | undefined, scope: string) => {
  if (user?.is_superuser || roleOf(user) === 'admin') return true
  return user?.scopes?.includes(scope) ?? false
}
