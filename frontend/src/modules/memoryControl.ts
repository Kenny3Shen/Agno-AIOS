import type {
  MemoryControlResponse,
  MemoryItem,
  MemoryMode,
  MemoryUserSummary,
} from "../types"

export type MemoryPayloadDefaults = {
  page: number
  limit: number
}

export type MemoryModeBadge = {
  key: "automatic" | "session_summaries" | "agentic" | "readonly"
  label: string
  enabled: boolean
}

const asRecord = (value: unknown): Record<string, unknown> => {
  return value && typeof value === "object" ? value as Record<string, unknown> : {}
}

export const defaultMemoryPayload = ({ page, limit }: MemoryPayloadDefaults): MemoryControlResponse => ({
  module: "memory",
  title: "Memory",
  description: "",
  status: "ok",
  metrics: [],
  records: [],
  generated_at: "",
  memories: [],
  memory_users: [],
  memory_topics: [],
  memory_filters: {
    user_id: "",
    topic: "",
    search: "",
    page,
    limit,
    total: 0,
  },
  memory_thresholds: {
    optimization_review: 0,
    abnormal_growth: 0,
  },
  memory_mode: {
    type: "automatic",
    update_memory_on_run: false,
    enable_agentic_memory: false,
    enable_session_summaries: false,
    readonly: true,
  },
})

export const normalizeMemoryPayload = (
  payload: unknown,
  fallback: MemoryControlResponse,
): MemoryControlResponse => {
  const record = asRecord(payload)
  const filters = asRecord(record.memory_filters)
  return {
    ...fallback,
    ...record,
    memories: Array.isArray(record.memories) ? record.memories as MemoryItem[] : [],
    memory_users: Array.isArray(record.memory_users) ? record.memory_users as MemoryUserSummary[] : [],
    memory_topics: Array.isArray(record.memory_topics) ? record.memory_topics as string[] : [],
    memory_filters: {
      ...fallback.memory_filters,
      ...filters,
    },
    memory_thresholds: {
      ...fallback.memory_thresholds,
      ...asRecord(record.memory_thresholds),
    },
    memory_mode: {
      ...fallback.memory_mode,
      ...asRecord(record.memory_mode),
    } as MemoryMode,
  } as MemoryControlResponse
}

export const payloadAfterMemoryLoadFailure = (
  currentPayload: MemoryControlResponse | null,
  fallback: MemoryControlResponse,
) => currentPayload ?? fallback

export const memoryDisplayStatus = (
  memory: Pick<MemoryItem, "status" | "user_id">,
  users: Pick<MemoryUserSummary, "user_id" | "status">[],
) => {
  const userStatus = users.find((user) => user.user_id === memory.user_id)?.status
  if (memory.status && memory.status !== "stored") return memory.status
  return userStatus || memory.status || "stored"
}

export const memoryModeBadges = (mode: MemoryMode): MemoryModeBadge[] => [
  {
    key: "automatic",
    label: mode.type || "automatic",
    enabled: Boolean(mode.update_memory_on_run),
  },
  {
    key: "session_summaries",
    label: "summaries",
    enabled: Boolean(mode.enable_session_summaries),
  },
  {
    key: "agentic",
    label: "agentic",
    enabled: Boolean(mode.enable_agentic_memory),
  },
  {
    key: "readonly",
    label: "read-only",
    enabled: Boolean(mode.readonly),
  },
]
