export type UserRole = "admin" | "user" | "guest"

const ROLE_PERMISSIONS: Record<UserRole, readonly string[]> = {
  admin: ["*"],
  user: [
    "session:read:own",
    "session:write:own",
    "trace:read:own",
    "memory:read:own",
    "metrics:read:own",
    "asset:read",
    "collect:write",
    "cve:read",
    "knowledge:read",
    "knowledge:write",
    "mcp:read",
    "skill:read",
    "settings:read",
  ],
  guest: [
    "session:read:own",
    "trace:read:own",
    "memory:read:own",
    "metrics:read:own",
    "asset:read",
    "cve:read",
    "knowledge:read",
  ],
}

export const hasRolePermission = (role: UserRole, permission: string) => {
  const permissions = ROLE_PERMISSIONS[role]
  return permissions.includes("*") || permissions.includes(permission)
}
