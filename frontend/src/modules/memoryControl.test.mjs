import assert from "node:assert/strict"
import {
  defaultMemoryPayload,
  memoryDisplayStatus,
  memoryModeBadges,
  normalizeMemoryPayload,
  payloadAfterMemoryLoadFailure,
} from "./memoryControl.ts"

const previousPayload = {
  ...defaultMemoryPayload({ page: 1, limit: 50 }),
  memories: [
    {
      id: "mem-1",
      memory: "Prefers concise summaries",
      topics: ["preference"],
      input: "Keep it short",
      user_id: "u1",
      agent_id: "security-operations",
      team_id: "",
      feedback: "",
      created_at: "2026-07-01T00:00:00Z",
      updated_at: "2026-07-02T00:00:00Z",
      status: "stored",
    },
  ],
  memory_users: [
    {
      user_id: "u1",
      total_memories: 501,
      last_memory_updated_at: "2026-07-02T00:00:00Z",
      status: "risk",
    },
  ],
  memory_filters: {
    user_id: "u1",
    topic: "",
    search: "",
    page: 1,
    limit: 50,
    total: 1,
  },
}

assert.equal(
  payloadAfterMemoryLoadFailure(previousPayload, defaultMemoryPayload({ page: 1, limit: 50 })),
  previousPayload,
  "load failures must keep the previous memory payload instead of showing a false empty state",
)

assert.deepEqual(
  payloadAfterMemoryLoadFailure(null, defaultMemoryPayload({ page: 2, limit: 25 })).memory_filters,
  {
    user_id: "",
    topic: "",
    search: "",
    page: 2,
    limit: 25,
    total: 0,
  },
  "first-load failures should still use a scoped empty fallback",
)

assert.equal(
  memoryDisplayStatus(previousPayload.memories[0], previousPayload.memory_users),
  "risk",
  "stored memory rows should inherit the user's growth-risk status",
)

const normalizedPayload = normalizeMemoryPayload(
  {
    ...previousPayload,
    memories: null,
    memory_users: "bad",
    memory_topics: ["preference"],
    memory_filters: { page: 3, limit: 10, total: 0 },
    memory_mode: null,
  },
  defaultMemoryPayload({ page: 1, limit: 50 }),
)

assert.deepEqual(normalizedPayload.memories, [], "invalid memories should normalize to an empty array")
assert.deepEqual(normalizedPayload.memory_users, [], "invalid user summaries should normalize to an empty array")
assert.equal(normalizedPayload.memory_filters.page, 3, "server pagination should win when provided")
assert.equal(normalizedPayload.memory_mode.readonly, true, "missing mode should fall back to read-only")

assert.deepEqual(
  memoryModeBadges({
    type: "automatic",
    update_memory_on_run: true,
    enable_agentic_memory: false,
    enable_session_summaries: true,
    readonly: true,
  }).map((badge) => `${badge.key}:${badge.enabled}`),
  [
    "automatic:true",
    "session_summaries:true",
    "agentic:false",
    "readonly:true",
  ],
  "mode badges should expose automatic, agentic, summaries, and readonly flags",
)
