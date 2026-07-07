import { computed, ref } from "vue"
import { defineStore } from "pinia"
import { hasUserScope, userRole, type UserRole } from "../lib/scopes"
import type { AuthUser } from "../types"

export const useAuthStore = defineStore("auth", () => {
  const currentUser = ref<AuthUser | null>(null)
  const authBooting = ref(true)
  const loggingOut = ref(false)
  const userMenuOpen = ref(false)

  const role = computed<UserRole>(() => userRole(currentUser.value))
  const canWrite = computed(() => hasUserScope(currentUser.value, "sessions:write"))
  const canAdmin = computed(() => role.value === "admin")
  const hasScope = (scope: string) => hasUserScope(currentUser.value, scope)

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
    hasScope,
    setCurrentUser,
    setAuthBooting,
    setLoggingOut,
    setUserMenuOpen,
  }
})
