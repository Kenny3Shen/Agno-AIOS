import { ref } from "vue"
import { defineStore } from "pinia"
import type { ChatSession } from "../types"

export const useSessionStore = defineStore("sessions", () => {
  const chatSessions = ref<ChatSession[]>([])
  const currentChatSessionId = ref<string | null>(null)
  const loadingSessions = ref(false)
  const sessionError = ref<string | null>(null)

  const setChatSessions = (sessions: ChatSession[]) => {
    chatSessions.value = sessions
  }

  const setCurrentChatSessionId = (sessionId: string | null) => {
    currentChatSessionId.value = sessionId
  }

  const setLoadingSessions = (value: boolean) => {
    loadingSessions.value = value
  }

  const setSessionError = (message: string | null) => {
    sessionError.value = message
  }

  return {
    chatSessions,
    currentChatSessionId,
    loadingSessions,
    sessionError,
    setChatSessions,
    setCurrentChatSessionId,
    setLoadingSessions,
    setSessionError,
  }
})
