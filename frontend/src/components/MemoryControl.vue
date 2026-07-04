<template>
  <div class="memory-control">
    <section class="memory-summary ag-stat-strip">
      <article
        v-for="metric in payload?.metrics || fallbackMetrics"
        :key="metric.label"
        class="memory-summary-chip ag-stat-chip"
        :class="`tone-${metric.tone || 'blue'}`"
      >
        <span>{{ metric.label }}</span>
        <strong :title="metric.hint || metric.label">{{ metric.value }}</strong>
      </article>
    </section>

    <el-alert v-if="error" class="memory-alert" type="error" :title="error" show-icon />

    <section class="memory-toolbar">
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
      <el-button type="primary" :loading="loading" @click="applyFilters">
        <el-icon><Search /></el-icon>
        {{ t("agentOS.memory.apply") }}
      </el-button>
      <el-button :loading="loading" @click="loadMemory">
        <el-icon><Refresh /></el-icon>
      </el-button>
    </section>

    <main class="memory-workbench">
      <aside class="memory-users-panel">
        <div class="memory-panel-head">
          <div>
            <p>{{ t("agentOS.memory.usersTitle") }}</p>
            <span>{{ userPanelSummary }}</span>
          </div>
        </div>
        <div v-if="userOptions.length" class="memory-user-list">
          <button
            v-for="user in userOptions"
            :key="user.user_id"
            type="button"
            class="memory-user-row"
            :class="{ selected: user.user_id === filters.user_id }"
            @click="filterByUser(user.user_id)"
          >
            <span class="memory-dot" :class="statusTone(user.status)" />
            <span class="memory-user-main">
              <strong :title="user.user_id">{{ user.user_id }}</strong>
              <small>{{ formatTime(user.last_memory_updated_at) }}</small>
            </span>
            <span class="memory-user-count">{{ user.total_memories }}</span>
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
          <span class="memory-mode">
            {{ t("agentOS.memory.modeAutomatic") }}
          </span>
        </div>

        <div v-if="memories.length" class="memory-list">
          <article
            v-for="memory in memories"
            :key="memory.id"
            class="memory-row"
          >
            <div class="memory-row-main">
              <span class="memory-dot green" />
              <div>
                <strong :title="memory.memory">{{ memory.memory || t("agentOS.memory.emptyMemory") }}</strong>
                <p v-if="memory.input" :title="memory.input">{{ memory.input }}</p>
              </div>
            </div>
            <div class="memory-row-meta">
              <span class="memory-chip user" :title="memory.user_id">{{ memory.user_id || "default" }}</span>
              <span
                v-for="topic in memory.topics"
                :key="`${memory.id}-${topic}`"
                class="memory-chip"
              >
                {{ topic }}
              </span>
              <small>{{ formatTime(memory.updated_at) }}</small>
            </div>
          </article>
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
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue"
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
  OsControlMetric,
} from "../types"

const { t, locale } = useI18n()
const { loading, error, fetchMemory } = useOsControlApi()
const payload = ref<MemoryControlResponse | null>(null)

const filters = reactive({
  user_id: "",
  topic: "",
  search: "",
  page: 1,
  limit: 50,
})

const fallbackMetrics = computed<OsControlMetric[]>(() => [
  {
    label: t("agentOS.metricFallback.label"),
    value: t("agentOS.metricFallback.value"),
    hint: t("agentOS.metricFallback.hint"),
    tone: "blue",
  },
])

const memories = computed<MemoryItem[]>(() => payload.value?.memories || [])
const userOptions = computed<MemoryUserSummary[]>(() => payload.value?.memory_users || [])
const topicOptions = computed<string[]>(() => payload.value?.memory_topics || [])
const total = computed(() => payload.value?.memory_filters.total || 0)

const userPanelSummary = computed(() => {
  const review = userOptions.value.filter((user) => user.status === "review").length
  const risk = userOptions.value.filter((user) => user.status === "risk").length
  return t("agentOS.memory.usersSummary", {
    count: userOptions.value.length,
    review,
    risk,
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

const statusTone = (status: string) => {
  if (status === "risk") return "red"
  if (status === "review") return "yellow"
  if (status === "healthy" || status === "stored") return "green"
  return "blue"
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
  const nextPayload = await fetchMemory(queryParams())
  payload.value = nextPayload
  filters.page = nextPayload.memory_filters.page
  filters.limit = nextPayload.memory_filters.limit
}

const applyFilters = async () => {
  filters.page = 1
  await loadMemory()
}

const filterByUser = async (userId: string) => {
  filters.user_id = userId
  await applyFilters()
}

onMounted(() => {
  void loadMemory()
})
</script>

<style scoped>
.memory-control {
  --memory-bg: var(--ag-frame);
  --memory-panel: var(--ag-panel);
  --memory-panel-soft: var(--ag-panel-soft);
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

.memory-control :where(div, section, aside, main, article, p, span, strong, small, button) {
  min-width: 0;
}

.memory-summary {
  display: grid;
  flex: 0 0 auto;
  gap: 8px;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  padding: 12px 14px 0;
}

.memory-summary-chip {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--memory-border);
  border-radius: 8px;
  background: var(--memory-panel-soft);
  padding: 8px 10px;
}

.memory-summary-chip::before {
  position: absolute;
  inset: 0 auto 0 0;
  width: 2px;
  background: var(--memory-blue);
  content: "";
}

.memory-summary-chip.tone-green::before {
  background: var(--memory-green);
}

.memory-summary-chip.tone-yellow::before {
  background: var(--memory-yellow);
}

.memory-summary-chip.tone-red::before {
  background: var(--memory-red);
}

.memory-summary-chip span {
  display: block;
  color: var(--memory-muted);
  font-size: 10px;
  line-height: 1.35;
}

.memory-summary-chip strong {
  display: block;
  margin-top: 2px;
  overflow: hidden;
  color: var(--memory-heading);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 16px;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-alert {
  flex: 0 0 auto;
  margin: 12px 14px 0;
}

.memory-toolbar {
  display: grid;
  flex: 0 0 auto;
  gap: 8px;
  grid-template-columns: minmax(220px, 1fr) minmax(180px, 260px) minmax(160px, 220px) auto auto;
  padding: 12px 14px;
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
  grid-template-columns: minmax(240px, 320px) minmax(0, 1fr);
  min-height: 0;
  padding: 0 14px 14px;
}

.memory-users-panel,
.memory-list-panel {
  display: flex;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--memory-border);
  border-radius: 8px;
  background: var(--memory-panel);
  box-shadow: var(--ag-shadow-panel);
}

.memory-panel-head {
  display: flex;
  flex: 0 0 auto;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  border-bottom: 1px solid var(--memory-border);
  padding: 12px;
}

.memory-panel-head p {
  margin: 0;
  color: var(--memory-muted);
  font-size: 11px;
  font-weight: 800;
  line-height: 1.35;
  text-transform: uppercase;
}

.memory-panel-head span {
  display: block;
  margin-top: 4px;
  color: var(--memory-muted);
  font-size: 12px;
  line-height: 1.45;
}

.memory-mode,
.memory-chip {
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
  font-weight: 700;
  line-height: 1.35;
}

.memory-user-list,
.memory-list {
  min-height: 0;
  overflow: auto;
}

.memory-user-row {
  display: grid;
  width: 100%;
  grid-template-columns: 8px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  border: 0;
  border-bottom: 1px solid var(--memory-row-border);
  background: transparent;
  padding: 10px 12px;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.memory-user-row:hover,
.memory-user-row.selected {
  background: var(--memory-blue-soft);
}

.memory-dot {
  display: block;
  width: 8px;
  height: 24px;
  border-radius: 4px;
  background: var(--memory-blue);
}

.memory-dot.green {
  background: var(--memory-green);
}

.memory-dot.yellow {
  background: var(--memory-yellow);
}

.memory-dot.red {
  background: var(--memory-red);
}

.memory-user-main strong,
.memory-row-main strong {
  display: block;
  overflow: hidden;
  color: var(--memory-heading);
  font-size: 13px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-user-main small,
.memory-row-meta small {
  display: block;
  margin-top: 3px;
  color: var(--memory-muted);
  font-size: 11px;
  line-height: 1.35;
}

.memory-user-count {
  border: 1px solid var(--memory-border);
  border-radius: 6px;
  padding: 2px 6px;
  background: var(--memory-panel-soft);
  color: var(--memory-heading);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  font-weight: 800;
}

.memory-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(220px, 34%);
  gap: 12px;
  border-bottom: 1px solid var(--memory-row-border);
  padding: 12px;
}

.memory-row-main {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr);
  gap: 10px;
}

.memory-row-main p {
  display: -webkit-box;
  margin: 5px 0 0;
  overflow: hidden;
  color: var(--memory-muted);
  font-size: 12px;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
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

@media (max-width: 1100px) {
  .memory-summary {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .memory-toolbar {
    grid-template-columns: minmax(0, 1fr) minmax(160px, 1fr);
  }

  .memory-workbench {
    grid-template-columns: 1fr;
  }

  .memory-users-panel {
    max-height: 260px;
  }
}

@media (max-width: 680px) {
  .memory-summary,
  .memory-toolbar {
    grid-template-columns: 1fr;
  }

  .memory-row {
    grid-template-columns: 1fr;
  }

  .memory-row-meta {
    justify-content: flex-start;
  }
}
</style>
