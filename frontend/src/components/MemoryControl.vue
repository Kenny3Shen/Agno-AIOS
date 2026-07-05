<template>
  <div class="memory-control">
    <section class="memory-command">
      <div class="memory-command-copy">
        <span class="memory-kicker">
          {{ t("agentOS.memory.modeAutomatic") }}
        </span>
        <h2>{{ t("agentOS.memory.deskTitle") }}</h2>
        <p>{{ memoryModeDetails }}</p>
      </div>

      <div class="memory-priority-grid">
        <article
          v-for="card in priorityCards"
          :key="card.key"
          class="memory-priority-card"
          :class="`tone-${card.tone}`"
        >
          <span>{{ card.label }}</span>
          <strong :title="String(card.value)">{{ card.value }}</strong>
          <small>{{ card.hint }}</small>
        </article>
      </div>
    </section>

    <el-alert v-if="error" class="memory-alert" type="error" :title="error" show-icon />

    <section class="memory-query-panel">
      <div class="memory-query-label">
        <el-icon><Search /></el-icon>
        <div>
          <strong>{{ t("agentOS.memory.queryTitle") }}</strong>
          <span>{{ activeFilterSummary }}</span>
        </div>
      </div>

      <div class="memory-query-controls">
        <el-input
          v-model="filters.search"
          class="memory-search"
          clearable
          :placeholder="t('agentOS.memory.searchPlaceholder')"
          @keyup.enter="applyFilters"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select
          v-model="filters.user_id"
          class="memory-filter"
          clearable
          filterable
          :placeholder="t('agentOS.memory.userPlaceholder')"
          @change="applyFilters"
        >
          <el-option
            v-for="user in userOptions"
            :key="user.user_id"
            :label="user.user_id"
            :value="user.user_id"
          />
        </el-select>
        <el-select
          v-model="filters.topic"
          class="memory-filter"
          clearable
          filterable
          :placeholder="t('agentOS.memory.topicPlaceholder')"
          @change="applyFilters"
        >
          <el-option
            v-for="topic in topicOptions"
            :key="topic"
            :label="topic"
            :value="topic"
          />
        </el-select>
      </div>

      <div class="memory-query-actions">
        <el-button :disabled="!activeFilterCount" @click="clearFilters">
          {{ t("agentOS.memory.clearFilters") }}
        </el-button>
        <el-button type="primary" :loading="loading" @click="applyFilters">
          <el-icon><Search /></el-icon>
          {{ t("agentOS.memory.apply") }}
        </el-button>
        <el-button :loading="loading" @click="loadMemory">
          <el-icon><Refresh /></el-icon>
        </el-button>
      </div>
    </section>

    <main class="memory-workbench">
      <aside class="memory-queue-panel">
        <div class="memory-panel-head">
          <div>
            <p>{{ t("agentOS.memory.queueTitle") }}</p>
            <span>{{ userPanelSummary }}</span>
          </div>
          <span class="memory-threshold" :title="thresholdTitle">
            {{ thresholdSummary }}
          </span>
        </div>

        <div class="memory-status-board">
          <article class="tone-red">
            <span>{{ t("agentOS.memory.statusRisk") }}</span>
            <strong>{{ riskUserCount }}</strong>
          </article>
          <article class="tone-yellow">
            <span>{{ t("agentOS.memory.statusReview") }}</span>
            <strong>{{ reviewUserCount }}</strong>
          </article>
          <article class="tone-green">
            <span>{{ t("agentOS.memory.statusHealthy") }}</span>
            <strong>{{ healthyUserCount }}</strong>
          </article>
        </div>

        <div v-if="userOptions.length" class="memory-user-list">
          <button
            v-for="user in userOptions"
            :key="user.user_id"
            type="button"
            class="memory-user-row"
            :class="[`tone-${statusTone(user.status)}`, { selected: user.user_id === filters.user_id }]"
            :aria-pressed="user.user_id === filters.user_id"
            @click="filterByUser(user.user_id)"
          >
            <span class="memory-queue-rail">
              <span :style="userBarStyle(user)" />
            </span>
            <span class="memory-user-main">
              <strong :title="user.user_id">{{ user.user_id }}</strong>
              <small>{{ formatTime(user.last_memory_updated_at) }}</small>
            </span>
            <span class="memory-user-side">
              <span class="memory-status" :class="`tone-${statusTone(user.status)}`">
                {{ statusLabel(user.status) }}
              </span>
              <b>{{ user.total_memories }}</b>
            </span>
          </button>
        </div>

        <div v-else-if="!loading" class="memory-empty compact">
          <strong>{{ t("agentOS.memory.noUsers") }}</strong>
        </div>
      </aside>

      <section class="memory-list-panel">
        <div class="memory-panel-head">
          <div>
            <p>{{ t("agentOS.memory.memoriesTitle") }}</p>
            <span>{{ resultSummary }}</span>
          </div>
          <div class="memory-active-scope" :title="activeFilterSummary">
            <span v-if="filters.user_id">{{ filters.user_id }}</span>
            <span v-if="filters.topic">{{ filters.topic }}</span>
            <span v-if="filters.search">{{ t("agentOS.memory.searchChip") }}</span>
          </div>
        </div>

        <div v-if="memories.length" class="memory-list">
          <button
            v-for="memory in memories"
            :key="memory.id"
            type="button"
            class="memory-row"
            :class="{ selected: memory.id === selectedMemory?.id }"
            :aria-pressed="memory.id === selectedMemory?.id"
            @click="selectMemory(memory.id)"
          >
            <span class="memory-row-status" :class="`tone-${memoryStatusTone(memory)}`" />
            <span class="memory-row-copy">
              <strong :title="memory.memory">{{ memory.memory || t("agentOS.memory.emptyMemory") }}</strong>
              <small v-if="memory.input" :title="memory.input">{{ memory.input }}</small>
            </span>
            <span class="memory-row-meta">
              <span class="memory-chip user" :title="memory.user_id">{{ memory.user_id || "default" }}</span>
              <span
                v-for="topic in memory.topics.slice(0, 3)"
                :key="`${memory.id}-${topic}`"
                class="memory-chip"
                :title="topic"
              >
                {{ topic }}
              </span>
              <small>{{ formatTime(memory.updated_at) }}</small>
            </span>
          </button>
        </div>

        <div v-else-if="!loading" class="memory-empty">
          <el-icon><User /></el-icon>
          <strong>{{ t("agentOS.memory.emptyTitle") }}</strong>
          <span>{{ t("agentOS.memory.emptyDescription") }}</span>
        </div>

        <div v-if="total > filters.limit" class="memory-pagination">
          <el-pagination
            v-model:current-page="filters.page"
            :page-size="filters.limit"
            layout="prev, pager, next"
            :total="total"
            @current-change="loadMemory"
          />
        </div>
      </section>

      <aside class="memory-detail-panel">
        <template v-if="selectedMemory">
          <div class="memory-detail-head">
            <div>
              <p>{{ t("agentOS.memory.detailTitle") }}</p>
              <strong :title="selectedMemory.id">{{ selectedMemory.id }}</strong>
            </div>
            <span class="memory-status" :class="`tone-${selectedStatusTone}`">
              {{ statusLabel(selectedStatus) }}
            </span>
          </div>

          <article class="memory-reading">
            <span>{{ t("agentOS.memory.memoryLabel") }}</span>
            <p>{{ selectedMemory.memory || t("agentOS.memory.emptyMemory") }}</p>
          </article>

          <dl class="memory-detail-grid">
            <div>
              <dt>{{ t("agentOS.memory.userLabel") }}</dt>
              <dd :title="selectedMemory.user_id">{{ selectedMemory.user_id || "default" }}</dd>
            </div>
            <div>
              <dt>{{ t("agentOS.memory.updatedLabel") }}</dt>
              <dd>{{ formatTime(selectedMemory.updated_at) }}</dd>
            </div>
            <div>
              <dt>{{ t("agentOS.memory.agentLabel") }}</dt>
              <dd :title="selectedMemory.agent_id">{{ selectedMemory.agent_id || "-" }}</dd>
            </div>
            <div>
              <dt>{{ t("agentOS.memory.teamLabel") }}</dt>
              <dd :title="selectedMemory.team_id">{{ selectedMemory.team_id || "-" }}</dd>
            </div>
          </dl>

          <section class="memory-topic-stack">
            <p>{{ t("agentOS.memory.topicsLabel") }}</p>
            <div>
              <span
                v-for="topic in selectedMemory.topics"
                :key="`${selectedMemory.id}-detail-${topic}`"
                class="memory-chip"
                :title="topic"
              >
                {{ topic }}
              </span>
              <span v-if="!selectedMemory.topics.length" class="memory-chip">
                -
              </span>
            </div>
          </section>

          <section v-if="selectedMemory.input" class="memory-evidence">
            <p>{{ t("agentOS.memory.inputLabel") }}</p>
            <pre>{{ selectedMemory.input }}</pre>
          </section>

          <section class="memory-lifecycle">
            <p>{{ t("agentOS.memory.workflowTitle") }}</p>
            <ol>
              <li
                v-for="stage in workflowStages"
                :key="stage.key"
                :class="`tone-${stage.tone}`"
              >
                <span />
                <div>
                  <strong>{{ stage.label }}</strong>
                  <small>{{ stage.value }}</small>
                </div>
              </li>
            </ol>
          </section>
        </template>

        <div v-else class="memory-empty">
          <el-icon><User /></el-icon>
          <strong>{{ t("agentOS.memory.emptyTitle") }}</strong>
          <span>{{ t("agentOS.memory.emptyDescription") }}</span>
        </div>
      </aside>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import {
  Refresh,
  Search,
  User,
} from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import { useOsControlApi } from "../composables/useApi"
import type {
  MemoryControlResponse,
  MemoryItem,
  MemoryQueryParams,
  MemoryUserSummary,
} from "../types"

const { t, locale } = useI18n()
const { loading, error, fetchMemory } = useOsControlApi()
const payload = ref<MemoryControlResponse | null>(null)
const selectedMemoryId = ref("")

const filters = reactive({
  user_id: "",
  topic: "",
  search: "",
  page: 1,
  limit: 50,
})

const defaultMemoryPayload = (): MemoryControlResponse => ({
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
    page: filters.page,
    limit: filters.limit,
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

const memories = computed<MemoryItem[]>(() => payload.value?.memories || [])
const userOptions = computed<MemoryUserSummary[]>(() => payload.value?.memory_users || [])
const topicOptions = computed<string[]>(() => payload.value?.memory_topics || [])
const total = computed(() => payload.value?.memory_filters?.total || 0)
const thresholds = computed(() => payload.value?.memory_thresholds)
const memoryMode = computed(() => payload.value?.memory_mode)
const riskUserCount = computed(() => userOptions.value.filter((user) => user.status === "risk").length)
const reviewUserCount = computed(() => userOptions.value.filter((user) => user.status === "review").length)
const healthyUserCount = computed(() => userOptions.value.filter((user) => user.status === "healthy" || user.status === "stored").length)
const maxUserMemories = computed(() => Math.max(1, ...userOptions.value.map((user) => user.total_memories)))

const selectedMemory = computed<MemoryItem | null>(() => {
  if (!memories.value.length) return null
  return memories.value.find((memory) => memory.id === selectedMemoryId.value) || memories.value[0] || null
})

const selectedUser = computed(() => {
  const userId = selectedMemory.value?.user_id || filters.user_id
  return userOptions.value.find((user) => user.user_id === userId) || null
})

const selectedStatus = computed(() => selectedMemory.value?.status || selectedUser.value?.status || "stored")
const selectedStatusTone = computed(() => statusTone(selectedStatus.value))

const activeFilterCount = computed(() => {
  return [filters.search.trim(), filters.user_id, filters.topic].filter(Boolean).length
})

const activeFilterSummary = computed(() => {
  const parts: string[] = []
  if (filters.search.trim()) parts.push(t("agentOS.memory.activeSearch", { value: filters.search.trim() }))
  if (filters.user_id) parts.push(t("agentOS.memory.activeUser", { value: filters.user_id }))
  if (filters.topic) parts.push(t("agentOS.memory.activeTopic", { value: filters.topic }))
  return parts.length ? parts.join(" / ") : t("agentOS.memory.allMemoryScope")
})

const priorityCards = computed(() => [
  {
    key: "risk",
    label: t("agentOS.memory.statusRisk"),
    value: riskUserCount.value,
    hint: t("agentOS.memory.riskHint"),
    tone: "red",
  },
  {
    key: "review",
    label: t("agentOS.memory.statusReview"),
    value: reviewUserCount.value,
    hint: t("agentOS.memory.reviewHint"),
    tone: "yellow",
  },
  {
    key: "stored",
    label: t("agentOS.memory.storedMemories"),
    value: total.value,
    hint: t("agentOS.memory.storedHint", { count: userOptions.value.length }),
    tone: "green",
  },
  {
    key: "mode",
    label: t("agentOS.memory.modeLabel"),
    value: memoryMode.value?.type || "auto",
    hint: memoryModeDetails.value,
    tone: "blue",
  },
])

const userPanelSummary = computed(() => {
  return t("agentOS.memory.usersSummary", {
    count: userOptions.value.length,
    review: reviewUserCount.value,
    risk: riskUserCount.value,
  })
})

const resultSummary = computed(() => {
  const start = total.value === 0 ? 0 : (filters.page - 1) * filters.limit + 1
  const end = Math.min(total.value, filters.page * filters.limit)
  return t("agentOS.memory.resultSummary", {
    start,
    end,
    total: total.value,
  })
})

const thresholdSummary = computed(() => t("agentOS.memory.thresholdSummary", {
  review: thresholds.value?.optimization_review ?? "-",
  risk: thresholds.value?.abnormal_growth ?? "-",
}))

const thresholdTitle = computed(() => t("agentOS.memory.thresholdTitle", {
  review: thresholds.value?.optimization_review ?? "-",
  risk: thresholds.value?.abnormal_growth ?? "-",
}))

const memoryModeDetails = computed(() => {
  const mode = memoryMode.value
  if (!mode) return "-"
  const details = [
    mode.update_memory_on_run ? t("agentOS.memory.updateOnRun") : t("agentOS.memory.updateDisabled"),
    mode.enable_session_summaries ? t("agentOS.memory.sessionSummaries") : t("agentOS.memory.sessionSummariesOff"),
    mode.readonly ? t("agentOS.memory.readonly") : t("agentOS.memory.writeEnabled"),
  ]
  return details.join(" / ")
})

const workflowStages = computed(() => {
  const memory = selectedMemory.value
  if (!memory) return []
  return [
    {
      key: "capture",
      label: t("agentOS.memory.workflowCaptured"),
      value: formatTime(memory.created_at),
      tone: "green",
    },
    {
      key: "review",
      label: statusLabel(selectedStatus.value),
      value: thresholdSummary.value,
      tone: selectedStatusTone.value,
    },
    {
      key: "recall",
      label: t("agentOS.memory.workflowRecall"),
      value: memory.topics.length ? memory.topics.join(" / ") : t("agentOS.memory.noTopics"),
      tone: "blue",
    },
  ]
})

const statusTone = (status?: string) => {
  if (status === "risk") return "red"
  if (status === "review") return "yellow"
  if (status === "healthy" || status === "stored") return "green"
  return "blue"
}

const statusLabel = (status?: string) => {
  if (status === "risk") return t("agentOS.memory.statusRisk")
  if (status === "review") return t("agentOS.memory.statusReview")
  if (status === "healthy" || status === "stored") return t("agentOS.memory.statusHealthy")
  return status || "-"
}

const memoryStatusTone = (memory: MemoryItem) => {
  const user = userOptions.value.find((item) => item.user_id === memory.user_id)
  return statusTone(memory.status || user?.status || "stored")
}

const userBarStyle = (user: MemoryUserSummary) => {
  const size = Math.max(10, Math.round((user.total_memories / maxUserMemories.value) * 100))
  return { "--memory-user-size": `${size}%` }
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
  const nextPayload = await fetchMemory(queryParams()).catch(() => defaultMemoryPayload())
  const memoryFilters = nextPayload.memory_filters || defaultMemoryPayload().memory_filters
  payload.value = {
    ...defaultMemoryPayload(),
    ...nextPayload,
    memories: Array.isArray(nextPayload.memories) ? nextPayload.memories : [],
    memory_users: Array.isArray(nextPayload.memory_users) ? nextPayload.memory_users : [],
    memory_topics: Array.isArray(nextPayload.memory_topics) ? nextPayload.memory_topics : [],
    memory_filters: memoryFilters,
    memory_thresholds: nextPayload.memory_thresholds || defaultMemoryPayload().memory_thresholds,
    memory_mode: nextPayload.memory_mode || defaultMemoryPayload().memory_mode,
  }
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

const selectMemory = (memoryId: string) => {
  selectedMemoryId.value = memoryId
}

watch(memories, (nextMemories) => {
  const stillSelected = nextMemories.some((memory) => memory.id === selectedMemoryId.value)
  if (!stillSelected) selectedMemoryId.value = nextMemories[0]?.id || ""
}, { immediate: true })

onMounted(() => {
  void loadMemory()
})
</script>

<style scoped>
.memory-control {
  --memory-bg: var(--ag-frame);
  --memory-panel: var(--ag-panel);
  --memory-panel-soft: var(--ag-panel-soft);
  --memory-panel-raised: var(--ag-panel-raised);
  --memory-border: var(--ag-border);
  --memory-border-strong: var(--ag-border-strong);
  --memory-text: var(--ag-text);
  --memory-heading: var(--ag-heading);
  --memory-muted: var(--ag-muted);
  --memory-muted-strong: var(--ag-muted-strong);
  --memory-blue: var(--ag-blue);
  --memory-blue-soft: var(--ag-blue-soft);
  --memory-green: var(--ag-green);
  --memory-green-soft: var(--ag-green-soft);
  --memory-yellow: var(--ag-yellow);
  --memory-yellow-soft: var(--ag-yellow-soft);
  --memory-red: var(--ag-red);
  --memory-red-soft: var(--ag-red-soft);
  --memory-row-border: color-mix(in srgb, var(--memory-border) 74%, transparent);
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  background: var(--memory-bg);
  color: var(--memory-text);
}

.memory-control :where(div, section, aside, main, article, p, span, strong, small, button, dl, dt, dd, pre, ol, li) {
  min-width: 0;
}

.memory-command {
  display: grid;
  flex: 0 0 auto;
  gap: 12px;
  grid-template-columns: minmax(260px, 0.9fr) minmax(480px, 1.5fr);
  padding: 14px 14px 0;
}

.memory-command-copy,
.memory-priority-card,
.memory-query-panel,
.memory-queue-panel,
.memory-list-panel,
.memory-detail-panel {
  border: 1px solid var(--memory-border);
  border-radius: 8px;
  background: var(--memory-panel);
  box-shadow: var(--ag-shadow-panel);
}

.memory-command-copy {
  display: grid;
  align-content: center;
  gap: 6px;
  overflow: hidden;
  padding: 14px;
}

.memory-kicker,
.memory-panel-head p,
.memory-detail-head p,
.memory-reading span,
.memory-topic-stack p,
.memory-evidence p,
.memory-lifecycle p,
.memory-query-label strong {
  margin: 0;
  color: var(--memory-muted);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0;
  line-height: 1.35;
  text-transform: uppercase;
}

.memory-command-copy h2 {
  margin: 0;
  color: var(--memory-heading);
  font-size: 22px;
  font-weight: 900;
  line-height: 1.15;
}

.memory-command-copy p {
  margin: 0;
  overflow: hidden;
  color: var(--memory-muted-strong);
  font-size: 12px;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-priority-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.memory-priority-card {
  position: relative;
  overflow: hidden;
  padding: 12px;
}

.memory-priority-card::before {
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: var(--memory-blue);
  content: "";
}

.memory-priority-card.tone-green::before {
  background: var(--memory-green);
}

.memory-priority-card.tone-yellow::before {
  background: var(--memory-yellow);
}

.memory-priority-card.tone-red::before {
  background: var(--memory-red);
}

.memory-priority-card span,
.memory-priority-card small {
  display: block;
  overflow: hidden;
  color: var(--memory-muted);
  font-size: 11px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-priority-card strong {
  display: block;
  margin-top: 7px;
  overflow: hidden;
  color: var(--memory-heading);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 24px;
  font-weight: 900;
  line-height: 1.05;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-priority-card small {
  margin-top: 7px;
  color: var(--memory-muted-strong);
}

.memory-alert {
  flex: 0 0 auto;
  margin: 12px 14px 0;
}

.memory-query-panel {
  display: grid;
  flex: 0 0 auto;
  gap: 10px;
  grid-template-columns: minmax(180px, 260px) minmax(360px, 1fr) auto;
  align-items: center;
  margin: 12px 14px 0;
  padding: 10px;
}

.memory-query-label {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
}

.memory-query-label .el-icon {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border: 1px solid var(--memory-border);
  border-radius: 6px;
  background: var(--memory-panel-soft);
  color: var(--memory-blue);
}

.memory-query-label span {
  display: block;
  overflow: hidden;
  margin-top: 2px;
  color: var(--memory-muted);
  font-size: 11px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-query-controls {
  display: grid;
  gap: 8px;
  grid-template-columns: minmax(220px, 1fr) minmax(160px, 240px) minmax(150px, 220px);
}

.memory-query-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.memory-search,
.memory-filter {
  width: 100%;
}

.memory-control :deep(.el-input__wrapper),
.memory-control :deep(.el-select__wrapper) {
  border: 1px solid var(--memory-border);
  background: var(--memory-panel-soft);
  box-shadow: none;
}

.memory-control :deep(.el-input__inner),
.memory-control :deep(.el-select__placeholder),
.memory-control :deep(.el-input__prefix),
.memory-control :deep(.el-select__caret) {
  color: var(--memory-muted-strong);
}

.memory-control :deep(.el-input__inner::placeholder) {
  color: var(--memory-muted);
}

.memory-workbench {
  display: grid;
  flex: 1 1 auto;
  gap: 12px;
  grid-template-columns: minmax(230px, 280px) minmax(300px, 1fr) minmax(280px, 340px);
  min-height: 0;
  padding: 12px 14px 14px;
}

.memory-queue-panel,
.memory-list-panel,
.memory-detail-panel {
  display: flex;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
}

.memory-panel-head,
.memory-detail-head {
  display: flex;
  flex: 0 0 auto;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  border-bottom: 1px solid var(--memory-border);
  padding: 12px;
}

.memory-panel-head span {
  display: block;
  margin-top: 4px;
  color: var(--memory-muted);
  font-size: 12px;
  line-height: 1.45;
}

.memory-threshold,
.memory-status,
.memory-chip,
.memory-active-scope span {
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  border: 1px solid var(--memory-border);
  border-radius: 6px;
  background: var(--memory-panel-soft);
  padding: 3px 7px;
  color: var(--memory-muted);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
  font-weight: 800;
  line-height: 1.35;
}

.memory-threshold {
  flex: 0 0 auto;
  margin-top: 0 !important;
  color: var(--memory-yellow) !important;
}

.memory-status-board {
  display: grid;
  flex: 0 0 auto;
  gap: 8px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  border-bottom: 1px solid var(--memory-border);
  padding: 10px;
}

.memory-status-board article {
  overflow: hidden;
  border: 1px solid var(--memory-border);
  border-radius: 8px;
  background: var(--memory-panel-soft);
  padding: 8px;
}

.memory-status-board span {
  display: block;
  overflow: hidden;
  color: var(--memory-muted);
  font-size: 10px;
  font-weight: 800;
  line-height: 1.25;
  text-overflow: ellipsis;
  text-transform: uppercase;
  white-space: nowrap;
}

.memory-status-board strong {
  display: block;
  margin-top: 5px;
  color: var(--memory-heading);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 18px;
  line-height: 1.1;
}

.memory-user-list,
.memory-list,
.memory-detail-panel {
  min-height: 0;
  overflow: auto;
}

.memory-user-row,
.memory-row {
  display: grid;
  width: 100%;
  align-items: center;
  border: 0;
  border-bottom: 1px solid var(--memory-row-border);
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.memory-user-row {
  grid-template-columns: 8px minmax(0, 1fr) auto;
  gap: 10px;
  padding: 10px 12px;
}

.memory-user-row:hover,
.memory-user-row.selected,
.memory-row:hover,
.memory-row.selected {
  background: var(--memory-blue-soft);
}

.memory-user-row:focus-visible,
.memory-row:focus-visible {
  outline: 2px solid var(--memory-blue);
  outline-offset: -2px;
}

.memory-queue-rail {
  display: block;
  width: 8px;
  height: 42px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--memory-panel-soft);
}

.memory-queue-rail span {
  display: block;
  width: 100%;
  height: var(--memory-user-size);
  min-height: 10px;
  border-radius: inherit;
  background: var(--memory-blue);
}

.memory-user-row.tone-green .memory-queue-rail span {
  background: var(--memory-green);
}

.memory-user-row.tone-yellow .memory-queue-rail span {
  background: var(--memory-yellow);
}

.memory-user-row.tone-red .memory-queue-rail span {
  background: var(--memory-red);
}

.memory-user-main strong,
.memory-row-copy strong,
.memory-detail-head strong {
  display: block;
  overflow: hidden;
  color: var(--memory-heading);
  font-size: 13px;
  font-weight: 850;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-user-main small,
.memory-row-copy small,
.memory-row-meta small {
  display: -webkit-box;
  margin-top: 4px;
  overflow: hidden;
  color: var(--memory-muted);
  font-size: 11px;
  line-height: 1.35;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.memory-user-side {
  display: grid;
  justify-items: end;
  gap: 4px;
}

.memory-user-side b {
  border: 1px solid var(--memory-border);
  border-radius: 6px;
  padding: 2px 6px;
  background: var(--memory-panel-soft);
  color: var(--memory-heading);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  line-height: 1.25;
}

.memory-status {
  min-width: 58px;
  justify-content: center;
  padding-inline: 6px;
}

.memory-status.tone-green,
.memory-status-board .tone-green,
.memory-lifecycle li.tone-green span {
  border-color: color-mix(in srgb, var(--memory-green) 38%, var(--memory-border));
  background: var(--memory-green-soft);
  color: var(--memory-green);
}

.memory-status.tone-yellow,
.memory-status-board .tone-yellow,
.memory-lifecycle li.tone-yellow span {
  border-color: color-mix(in srgb, var(--memory-yellow) 44%, var(--memory-border));
  background: var(--memory-yellow-soft);
  color: var(--memory-yellow);
}

.memory-status.tone-red,
.memory-status-board .tone-red,
.memory-lifecycle li.tone-red span {
  border-color: color-mix(in srgb, var(--memory-red) 44%, var(--memory-border));
  background: var(--memory-red-soft);
  color: var(--memory-red);
}

.memory-active-scope {
  display: flex;
  max-width: 50%;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.memory-row {
  grid-template-columns: 4px minmax(0, 1fr) minmax(180px, 31%);
  gap: 12px;
  padding: 12px;
}

.memory-row-status {
  display: block;
  width: 4px;
  height: 54px;
  border-radius: 999px;
  background: var(--memory-blue);
}

.memory-row-status.tone-green {
  background: var(--memory-green);
}

.memory-row-status.tone-yellow {
  background: var(--memory-yellow);
}

.memory-row-status.tone-red {
  background: var(--memory-red);
}

.memory-row-meta {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-content: flex-start;
  justify-content: flex-end;
  gap: 6px;
}

.memory-chip.user {
  color: var(--memory-blue);
}

.memory-detail-panel {
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--memory-blue-soft) 42%, transparent), transparent 160px),
    var(--memory-panel);
}

.memory-detail-head {
  align-items: center;
}

.memory-reading {
  flex: 0 0 auto;
  margin: 12px;
  border: 1px solid var(--memory-border);
  border-radius: 8px;
  background: var(--memory-panel-raised);
  padding: 12px;
}

.memory-reading p {
  margin: 8px 0 0;
  color: var(--memory-heading);
  font-size: 14px;
  font-weight: 750;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.memory-detail-grid {
  display: grid;
  flex: 0 0 auto;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin: 0;
  padding: 0 12px 12px;
}

.memory-detail-grid div {
  overflow: hidden;
  border: 1px solid var(--memory-border);
  border-radius: 8px;
  background: var(--memory-panel-soft);
  padding: 9px;
}

.memory-detail-grid dt {
  margin: 0;
  color: var(--memory-muted);
  font-size: 10px;
  font-weight: 800;
  line-height: 1.25;
  text-transform: uppercase;
}

.memory-detail-grid dd {
  margin: 5px 0 0;
  overflow: hidden;
  color: var(--memory-heading);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  font-weight: 800;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-topic-stack,
.memory-evidence,
.memory-lifecycle {
  flex: 0 0 auto;
  border-top: 1px solid var(--memory-border);
  padding: 12px;
}

.memory-topic-stack div {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.memory-evidence pre {
  max-height: 160px;
  margin: 8px 0 0;
  overflow: auto;
  border: 1px solid var(--memory-border);
  border-radius: 8px;
  background: var(--ag-code-bg);
  padding: 10px;
  color: var(--ag-code-text);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.memory-lifecycle ol {
  display: grid;
  gap: 8px;
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}

.memory-lifecycle li {
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr);
  gap: 9px;
  align-items: start;
}

.memory-lifecycle li > span {
  width: 12px;
  height: 12px;
  margin-top: 3px;
  border: 1px solid var(--memory-border);
  border-radius: 999px;
  background: var(--memory-blue-soft);
}

.memory-lifecycle li.tone-blue > span {
  border-color: color-mix(in srgb, var(--memory-blue) 44%, var(--memory-border));
  background: var(--memory-blue-soft);
}

.memory-lifecycle strong {
  display: block;
  color: var(--memory-heading);
  font-size: 12px;
  line-height: 1.35;
}

.memory-lifecycle small {
  display: block;
  overflow: hidden;
  margin-top: 2px;
  color: var(--memory-muted);
  font-size: 11px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-empty {
  display: grid;
  flex: 1 1 auto;
  place-items: center;
  align-content: center;
  gap: 6px;
  min-height: 180px;
  padding: 24px;
  color: var(--memory-muted);
  text-align: center;
}

.memory-empty.compact {
  min-height: 120px;
}

.memory-empty strong {
  color: var(--memory-heading);
  font-size: 14px;
}

.memory-empty span {
  max-width: 360px;
  font-size: 12px;
  line-height: 1.45;
}

.memory-pagination {
  display: flex;
  flex: 0 0 auto;
  justify-content: flex-end;
  border-top: 1px solid var(--memory-border);
  padding: 8px 12px;
}

@media (max-width: 1120px) {
  .memory-command {
    grid-template-columns: 1fr;
  }

  .memory-workbench {
    grid-template-columns: minmax(240px, 300px) minmax(0, 1fr);
  }

  .memory-detail-panel {
    grid-column: 1 / -1;
    max-height: 360px;
  }
}

@media (max-width: 980px) {
  .memory-query-panel {
    grid-template-columns: 1fr;
  }

  .memory-query-controls {
    grid-template-columns: 1fr;
  }

  .memory-query-actions {
    justify-content: flex-start;
    flex-wrap: wrap;
  }

  .memory-workbench {
    grid-template-columns: 1fr;
  }

  .memory-queue-panel {
    max-height: 320px;
  }

  .memory-detail-panel {
    grid-column: auto;
  }
}

@media (max-width: 680px) {
  .memory-command,
  .memory-query-panel {
    padding-inline: 10px;
  }

  .memory-priority-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .memory-workbench {
    padding-inline: 10px;
  }

  .memory-panel-head,
  .memory-detail-head {
    flex-wrap: wrap;
  }

  .memory-active-scope {
    max-width: 100%;
    justify-content: flex-start;
  }

  .memory-row {
    grid-template-columns: 4px minmax(0, 1fr);
  }

  .memory-row-meta {
    grid-column: 2;
    justify-content: flex-start;
  }

  .memory-detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
