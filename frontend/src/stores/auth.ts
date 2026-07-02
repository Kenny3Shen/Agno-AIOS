import { computed, ref } from "vue"
import { defineStore } from "pinia"
import type { AuthUser } from "../types"

export type UserRole = "admin" | "user" | "guest"

export const useAuthStore = defineStore("auth", () => {
  const currentUser = ref<AuthUser | null>(null)
  const authBooting = ref(true)
  const loggingOut = ref(false)
  const userMenuOpen = ref(false)

  const role = computed<UserRole>(() => currentUser.value?.role ?? "guest")
  const canWrite = computed(() => role.value !== "guest")
  const canAdmin = computed(() => role.value === "admin")

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
    setCurrentUser,
    setAuthBooting,
    setLoggingOut,
    setUserMenuOpen,
  }
})
