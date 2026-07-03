import { computed, ref } from "vue"
import { defineStore } from "pinia"
import { hasRolePermission, type UserRole } from "../lib/permissions"
import type { AuthUser } from "../types"

export const useAuthStore = defineStore("auth", () => {
  const currentUser = ref<AuthUser | null>(null)
  const authBooting = ref(true)
  const loggingOut = ref(false)
  const userMenuOpen = ref(false)

  const role = computed<UserRole>(() => {
    if (currentUser.value?.is_superuser) return "admin"
    return currentUser.value?.role ?? "guest"
  })
  const canWrite = computed(() => hasRolePermission(role.value, "session:write:own"))
  const canAdmin = computed(() => role.value === "admin")
  const hasPermission = (permission: string) => hasRolePermission(role.value, permission)

  const setCurrentUser = (user: AuthUser | null) => {
    currentUser.value = user
  }

  const setAuthBooting = (value: boolean) => {
    authBooting.value = value
  }

  const setLoggingOut = (value: boolean) => {
    loggingOut.value = value
  }

  const setUserMenuOpen = (value: boolean) => {
    userMenuOpen.value = value
  }

  return {
    currentUser,
    authBooting,
    loggingOut,
    userMenuOpen,
    role,
    canWrite,
    canAdmin,
    hasPermission,
    setCurrentUser,
    setAuthBooting,
    setLoggingOut,
    setUserMenuOpen,
  }
})
