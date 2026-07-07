export type UserRole = "admin" | "user" | "guest"
export type PermissionUser = {
  role?: UserRole
  is_superuser?: boolean
  permissions?: readonly string[]
}

export const AGENT_EVAL_PERMISSIONS = [
  "agent_eval:read",
  "agent_eval:write",
  "agent_eval:run",
] as const

const ROLE_PERMISSIONS: Record<UserRole, readonly string[]> = {
  admin: ["*"],
  user: [
    "session:read:own",
    "session:write:own",
    "trace:read:own",
    "memory:read:own",
    "memory:write:own",
    "metrics:read:own",
    "collect:write",
    "cve:read",
    "knowledge:read",
    "knowledge:write",
    "mcp:read",
    "skill:read",
    "settings:read",
    "agent_eval:read",
  ],
  guest: [
    "session:read:own",
    "trace:read:own",
    "memory:read:own",
    "metrics:read:own",
    "cve:read",
    "knowledge:read",
  ],
}

export const hasRolePermission = (role: UserRole, permission: string) => {
  const permissions = ROLE_PERMISSIONS[role]
  return permissions.includes("*") || permissions.includes(permission)
}

export const userRole = (user: PermissionUser | null | undefined): UserRole => {
  if (user?.is_superuser) return "admin"
  return user?.role ?? "guest"
}

export const hasUserPermission = (
  user: PermissionUser | null | undefined,
  permission: string,
) => {
  const permissions = user?.permissions
  if (permissions) {
    return permissions.includes("*") || permissions.includes(permission)
  }
  return hasRolePermission(userRole(user), permission)
}
