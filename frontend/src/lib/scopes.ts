export type UserRole = "admin" | "user" | "guest"
export type ScopeUser = {
  role?: UserRole
  is_superuser?: boolean
  scopes?: readonly string[]
}

export const ADMIN_SCOPE = "agent_os:admin"

export const AGENT_EVAL_SCOPES = [
  "evals:read",
  "evals:write",
  "evals:delete",
] as const

const ROLE_SCOPES: Record<UserRole, readonly string[]> = {
  admin: [ADMIN_SCOPE],
  user: [
    "sessions:read",
    "sessions:write",
    "traces:read",
    "memories:read",
    "memories:write",
    "memories:delete",
    "metrics:read",
    "collect:write",
    "cve:read",
    "knowledge:read",
    "knowledge:write",
    "knowledge:delete",
    "mcp:read",
    "skill:read",
    "config:read",
    "evals:read",
  ],
  guest: [
    "sessions:read",
    "traces:read",
    "memories:read",
    "metrics:read",
    "cve:read",
    "knowledge:read",
  ],
}

export const hasRoleScope = (role: UserRole, scope: string) => {
  const scopes = ROLE_SCOPES[role]
  return scopes.includes(ADMIN_SCOPE) || scopes.includes(scope)
}

export const userRole = (user: ScopeUser | null | undefined): UserRole => {
  if (user?.is_superuser) return "admin"
  return user?.role ?? "guest"
}

export const hasUserScope = (
  user: ScopeUser | null | undefined,
  scope: string,
) => {
  const scopes = user?.scopes
  if (scopes) {
    return scopes.includes(ADMIN_SCOPE) || scopes.includes(scope)
  }
  return hasRoleScope(userRole(user), scope)
}
