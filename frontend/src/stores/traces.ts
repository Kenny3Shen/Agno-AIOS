import { reactive, ref } from "vue"
import { defineStore } from "pinia"
import type { TraceItem, TraceStatus } from "../types"

export interface TraceFilters {
  session_id: string
  run_id: string
  user_id: string
  agent_id: string
  team_id: string
  workflow_id: string
  status: TraceStatus | ""
  timeRange: [string, string] | null
}

export const useTraceStore = defineStore("traces", () => {
  const traceItems = ref<TraceItem[]>([])
  const traceQueueItems = ref<TraceItem[]>([])
  const currentTraceId = ref<string | null>(null)
  const loadingTraceQueue = ref(false)
  const traceError = ref<string | null>(null)
  const traceFilters = reactive<TraceFilters>({
    session_id: "",
    run_id: "",
    user_id: "",
    agent_id: "",
    team_id: "",
    workflow_id: "",
    status: "",
    timeRange: null,
  })

  const setTraceItems = (items: TraceItem[]) => {
    traceItems.value = items
  }

  const setTraceQueueItems = (items: TraceItem[]) => {
    traceQueueItems.value = items
  }

  const setCurrentTraceId = (traceId: string | null) => {
    currentTraceId.value = traceId
  }

  const setLoadingTraceQueue = (value: boolean) => {
    loadingTraceQueue.value = value
  }

  const setTraceError = (message: string | null) => {
    traceError.value = message
  }

  const setTraceFilters = (filters: Partial<TraceFilters>) => {
    if (filters.session_id !== undefined) traceFilters.session_id = filters.session_id
    if (filters.run_id !== undefined) traceFilters.run_id = filters.run_id
    if (filters.user_id !== undefined) traceFilters.user_id = filters.user_id
    if (filters.agent_id !== undefined) traceFilters.agent_id = filters.agent_id
    if (filters.team_id !== undefined) traceFilters.team_id = filters.team_id
    if (filters.workflow_id !== undefined) traceFilters.workflow_id = filters.workflow_id
    if (filters.status !== undefined) traceFilters.status = filters.status
    if (filters.timeRange !== undefined) traceFilters.timeRange = filters.timeRange
  }

  const resetTraceFilters = () => {
    traceFilters.session_id = ""
    traceFilters.run_id = ""
    traceFilters.user_id = ""
    traceFilters.agent_id = ""
    traceFilters.team_id = ""
    traceFilters.workflow_id = ""
    traceFilters.status = ""
    traceFilters.timeRange = null
  }

  return {
    traceItems,
    traceQueueItems,
    currentTraceId,
    loadingTraceQueue,
    traceError,
    traceFilters,
    setTraceItems,
    setTraceQueueItems,
    setCurrentTraceId,
    setLoadingTraceQueue,
    setTraceError,
    setTraceFilters,
    resetTraceFilters,
  }
})
