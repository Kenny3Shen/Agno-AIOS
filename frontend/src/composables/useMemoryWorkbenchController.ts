import { computed, onMounted, reactive, ref, watch } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { useI18n } from "vue-i18n"
import { useMemoryControlApi } from "./useMemoryControlApi"
import {
  defaultMemoryPayload as buildDefaultMemoryPayload,
  memoryDisplayStatus,
  memoryModeBadges,
  normalizeMemoryPayload,
  payloadAfterMemoryLoadFailure,
} from "../modules/memoryControl"
import { useAuthStore } from "../stores/auth"
import type {
  MemoryItem,
  MemoryPayloadResponse,
  MemoryQueryParams,
  MemoryUserSummary,
} from "../types"

export type MemoryTone = "blue" | "green" | "yellow" | "red" | "muted"

export type MemoryPriorityCard = {
  key: string
  label: string
  value: string | number
  hint: string
  tone: MemoryTone
}

export type MemoryWorkbenchFilters = {
  user_id: string
  topic: string
  search: string
  page: number
  limit: number
}

export type MemoryEditForm = {
  memory: string
  topics: string[]
}

export const useMemoryWorkbenchController = () => {
  const { t, locale } = useI18n()
  const authStore = useAuthStore()
  const { loading, error, fetchMemory, deleteMemory, updateMemory } = useMemoryControlApi()
  const payload = ref<MemoryPayloadResponse | null>(null)
  const selectedMemoryId = ref("")
  const editDialogVisible = ref(false)

  const filters = reactive<MemoryWorkbenchFilters>({
    user_id: "",
    topic: "",
    search: "",
    page: 1,
    limit: 50,
  })

  const editForm = reactive<MemoryEditForm>({
    memory: "",
    topics: [],
  })

  const defaultMemoryPayload = (): MemoryPayloadResponse => buildDefaultMemoryPayload({
    page: filters.page,
    limit: filters.limit,
  })

  const memories = computed<MemoryItem[]>(() => payload.value?.memories || [])
  const userOptions = computed<MemoryUserSummary[]>(() => payload.value?.memory_users || [])
  const topicOptions = computed<string[]>(() => payload.value?.memory_topics || [])
  const total = computed(() => payload.value?.memory_filters?.total || 0)
  const thresholds = computed(() => payload.value?.memory_thresholds)
  const memoryMode = computed(() => payload.value?.memory_mode)
  const modeBadges = computed(() => memoryModeBadges(memoryMode.value || defaultMemoryPayload().memory_mode))
  const canWriteMemory = computed(() => authStore.hasScope("memories:write"))
  const canDeleteMemory = computed(() => authStore.hasScope("memories:delete"))
  const riskUserCount = computed(() => userOptions.value.filter((user) => user.status === "risk").length)
  const reviewUserCount = computed(() => userOptions.value.filter((user) => user.status === "review").length)
  const healthyUserCount = computed(() => {
    return userOptions.value.filter((user) => user.status === "healthy" || user.status === "stored").length
  })
  const maxUserMemories = computed(() => Math.max(1, ...userOptions.value.map((user) => user.total_memories)))

  const selectedMemory = computed<MemoryItem | null>(() => {
    if (!memories.value.length) return null
    return memories.value.find((memory) => memory.id === selectedMemoryId.value) || memories.value[0] || null
  })

  const selectedUser = computed(() => {
    const userId = selectedMemory.value?.user_id || filters.user_id
    return userOptions.value.find((user) => user.user_id === userId) || null
  })

  const selectedStatus = computed(() => {
    if (!selectedMemory.value) return selectedUser.value?.status || "stored"
    return memoryDisplayStatus(selectedMemory.value, userOptions.value)
  })
  const selectedStatusTone = computed(() => statusTone(selectedStatus.value))

  const activeFilterCount = computed(() => {
    return [filters.search.trim(), filters.user_id, filters.topic].filter(Boolean).length
  })

  const activeFilterSummary = computed(() => {
    const parts: string[] = []
    if (filters.search.trim()) parts.push(t("workbench.memory.activeSearch", { value: filters.search.trim() }))
    if (filters.user_id) parts.push(t("workbench.memory.activeUser", { value: filters.user_id }))
    if (filters.topic) parts.push(t("workbench.memory.activeTopic", { value: filters.topic }))
    return parts.length ? parts.join(" / ") : t("workbench.memory.allMemoryScope")
  })

  const priorityCards = computed<MemoryPriorityCard[]>(() => [
    {
      key: "risk",
      label: t("workbench.memory.statusRisk"),
      value: riskUserCount.value,
      hint: t("workbench.memory.riskHint"),
      tone: "red",
    },
    {
      key: "review",
      label: t("workbench.memory.statusReview"),
      value: reviewUserCount.value,
      hint: t("workbench.memory.reviewHint"),
      tone: "yellow",
    },
    {
      key: "stored",
      label: t("workbench.memory.storedMemories"),
      value: total.value,
      hint: t("workbench.memory.storedHint", { count: userOptions.value.length }),
      tone: "green",
    },
    {
      key: "mode",
      label: t("workbench.memory.modeLabel"),
      value: memoryMode.value?.type || "auto",
      hint: t("workbench.memory.modeLabel"),
      tone: "blue",
    },
  ])

  const userPanelSummary = computed(() => {
    return t("workbench.memory.usersSummary", {
      count: userOptions.value.length,
      review: reviewUserCount.value,
      risk: riskUserCount.value,
    })
  })

  const resultSummary = computed(() => {
    const start = total.value === 0 ? 0 : (filters.page - 1) * filters.limit + 1
    const end = Math.min(total.value, filters.page * filters.limit)
    return t("workbench.memory.resultSummary", {
      start,
      end,
      total: total.value,
    })
  })

  const thresholdSummary = computed(() => t("workbench.memory.thresholdSummary", {
    review: thresholds.value?.optimization_review ?? "-",
    risk: thresholds.value?.abnormal_growth ?? "-",
  }))

  const thresholdTitle = computed(() => t("workbench.memory.thresholdTitle", {
    review: thresholds.value?.optimization_review ?? "-",
    risk: thresholds.value?.abnormal_growth ?? "-",
  }))

  function statusTone(status?: string): MemoryTone {
    if (status === "risk") return "red"
    if (status === "review") return "yellow"
    if (status === "healthy" || status === "stored") return "green"
    return "blue"
  }

  const statusLabel = (status?: string) => {
    if (status === "risk") return t("workbench.memory.statusRisk")
    if (status === "review") return t("workbench.memory.statusReview")
    if (status === "healthy" || status === "stored") return t("workbench.memory.statusHealthy")
    return status || "-"
  }

  const memoryStatusTone = (memory: MemoryItem) => {
    return statusTone(memoryDisplayStatus(memory, userOptions.value))
  }

  const userBarStyle = (user: MemoryUserSummary) => {
    const size = Math.max(10, Math.round((user.total_memories / maxUserMemories.value) * 100))
    return { "--mem-user-size": `${size}%` }
  }

  const formatTime = (value?: string) => {
    if (!value) return "-"
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return value
    return date.toLocaleString(locale.value, {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    })
  }

  const queryParams = (): MemoryQueryParams => ({
    user_id: filters.user_id || undefined,
    topic: filters.topic || undefined,
    search: filters.search || undefined,
    page: filters.page,
    limit: filters.limit,
  })

  const loadMemory = async () => {
    const fallback = defaultMemoryPayload()
    const nextPayload = await fetchMemory(queryParams())
      .then((result) => normalizeMemoryPayload(result, fallback))
      .catch(() => payloadAfterMemoryLoadFailure(payload.value, fallback))
    payload.value = nextPayload
    const memoryFilters = nextPayload.memory_filters
    filters.page = memoryFilters.page
    filters.limit = memoryFilters.limit
  }

  const applyFilters = async () => {
    filters.page = 1
    await loadMemory()
  }

  const clearFilters = async () => {
    filters.user_id = ""
    filters.topic = ""
    filters.search = ""
    await applyFilters()
  }

  const filterByUser = async (userId: string) => {
    filters.user_id = userId
    await applyFilters()
  }

  const changePage = async (page: number) => {
    filters.page = page
    await loadMemory()
  }

  const selectMemory = (memoryId: string) => {
    selectedMemoryId.value = memoryId
  }

  const currentMutationUserId = (memory?: MemoryItem | null) => {
    return memory?.user_id || selectedMemory.value?.user_id || filters.user_id || undefined
  }

  const openEditMemoryDialog = (memory?: MemoryItem) => {
    const targetMemory = memory || selectedMemory.value
    if (!canWriteMemory.value || !targetMemory) return
    selectedMemoryId.value = targetMemory.id
    editForm.memory = targetMemory.memory
    editForm.topics = [...targetMemory.topics]
    editDialogVisible.value = true
  }

  const saveMemoryUpdate = async () => {
    if (!canWriteMemory.value || !selectedMemory.value) return
    const nextMemory = editForm.memory.trim()
    if (!nextMemory) {
      ElMessage.error(t("workbench.memory.updateEmpty"))
      return
    }
    try {
      await updateMemory(selectedMemory.value.id, {
        user_id: currentMutationUserId(selectedMemory.value),
        memory: nextMemory,
        topics: Array.from(new Set(editForm.topics.map((topic) => topic.trim()).filter(Boolean))),
      })
      editDialogVisible.value = false
      await loadMemory()
      ElMessage.success(t("workbench.memory.updateSuccess"))
    } catch (err) {
      ElMessage.error(err instanceof Error ? err.message : t("workbench.memory.updateFailed"))
    }
  }

  const deleteSelectedMemory = async (memory?: MemoryItem) => {
    const targetMemory = memory || selectedMemory.value
    if (!canDeleteMemory.value || !targetMemory) return
    selectedMemoryId.value = targetMemory.id
    try {
      await ElMessageBox.confirm(
        t("workbench.memory.deleteConfirmMessage"),
        t("workbench.memory.deleteConfirmTitle"),
        {
          confirmButtonText: t("common.actions.delete"),
          cancelButtonText: t("common.actions.cancel"),
          type: "warning",
        },
      )
      await deleteMemory(targetMemory.id, currentMutationUserId(targetMemory))
      await loadMemory()
      ElMessage.success(t("workbench.memory.deleteSuccess"))
    } catch (err) {
      if (err !== "cancel") {
        ElMessage.error(err instanceof Error ? err.message : t("workbench.memory.deleteFailed"))
      }
    }
  }

  watch(memories, (nextMemories) => {
    const stillSelected = nextMemories.some((memory) => memory.id === selectedMemoryId.value)
    if (!stillSelected) selectedMemoryId.value = nextMemories[0]?.id || ""
  }, { immediate: true })

  onMounted(() => {
    void loadMemory()
  })

  return {
    activeFilterCount,
    activeFilterSummary,
    applyFilters,
    canDeleteMemory,
    canWriteMemory,
    changePage,
    clearFilters,
    deleteSelectedMemory,
    editDialogVisible,
    editForm,
    error,
    filterByUser,
    filters,
    formatTime,
    healthyUserCount,
    loadMemory,
    loading,
    memories,
    memoryStatusTone,
    modeBadges,
    openEditMemoryDialog,
    priorityCards,
    resultSummary,
    reviewUserCount,
    riskUserCount,
    saveMemoryUpdate,
    selectMemory,
    selectedMemory,
    selectedStatus,
    selectedStatusTone,
    statusLabel,
    statusTone,
    thresholdSummary,
    thresholdTitle,
    topicOptions,
    total,
    userBarStyle,
    userOptions,
    userPanelSummary,
  }
}
