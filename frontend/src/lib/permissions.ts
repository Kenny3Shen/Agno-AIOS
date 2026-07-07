export type UserRole = "admin" | "user" | "guest"
export type PermissionUser = {
  role?: UserRole
  is_superuser?: boolean
  permissions?: readonly string[]
  scopes?: readonly string[]
}

export const ADMIN_SCOPE = "agent_os:admin"

export const AGENT_EVAL_PERMISSIONS = [
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

export const hasRolePermission = (role: UserRole, permission: string) => {
  const permissions = ROLE_SCOPES[role]
  return permissions.includes(ADMIN_SCOPE) || permissions.includes(permission)
}

export const userRole = (user: PermissionUser | null | undefined): UserRole => {
  if (user?.is_superuser) return "admin"
  return user?.role ?? "guest"
}

export const hasUserPermission = (
  user: PermissionUser | null | undefined,
  permission: string,
) => {
  const permissions = user?.scopes ?? user?.permissions
  if (permissions) {
    return permissions.includes(ADMIN_SCOPE) || permissions.includes(permission)
  }
  return hasRolePermission(userRole(user), permission)
}
