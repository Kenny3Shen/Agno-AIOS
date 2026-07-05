<template>
  <div class="memory-control ag-page-flow">
    <section class="memory-priority-strip ag-stat-strip">
      <article
        v-for="card in priorityCards"
        :key="card.key"
        class="memory-priority-card ag-stat-chip"
        :class="`tone-${card.tone}`"
        :title="card.hint"
      >
        <span>{{ card.label }}</span>
        <strong :title="String(card.value)">{{ card.value }}</strong>
      </article>
    </section>

    <el-alert v-if="error" class="memory-alert" type="error" :title="error" show-icon />

    <section class="memory-query-panel ag-content-panel">
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
      <aside class="memory-queue-panel ag-workspace-panel">
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

      <section class="memory-list-panel ag-workspace-panel">
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
          <article
            v-for="memory in memories"
            :key="memory.id"
            class="memory-row"
            :class="{ selected: memory.id === selectedMemory?.id }"
          >
            <span class="memory-row-status" :class="`tone-${memoryStatusTone(memory)}`" />
            <button
              type="button"
              class="memory-row-main"
              :aria-pressed="memory.id === selectedMemory?.id"
              @click="selectMemory(memory.id)"
            >
              <span class="memory-row-copy">
                <strong :title="memory.memory">{{ memory.memory || t("agentOS.memory.emptyMemory") }}</strong>
              </span>
              <span class="memory-row-facts">
                <span v-if="!memory.topics.length" class="memory-chip">
                  {{ t("agentOS.memory.noTopics") }}
                </span>
                <span
                  v-for="topic in memory.topics"
                  :key="`${memory.id}-${topic}`"
                  class="memory-chip"
                  :title="topic"
                >
                  {{ topic }}
                </span>
              </span>
            </button>
            <span v-if="canWriteMemory" class="memory-row-actions">
              <el-button
                size="small"
                plain
                circle
                class="memory-action-button"
                :aria-label="t('agentOS.memory.editMemory')"
                :title="t('agentOS.memory.editMemory')"
                :disabled="loading"
                @click.stop="openEditMemoryDialog(memory)"
              >
                <el-icon><EditPen /></el-icon>
              </el-button>
              <el-button
                size="small"
                type="danger"
                plain
                circle
                class="memory-action-button"
                :aria-label="t('agentOS.memory.deleteMemory')"
                :title="t('agentOS.memory.deleteMemory')"
                :disabled="loading"
                @click.stop="deleteSelectedMemory(memory)"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </span>
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

      <aside class="memory-detail-panel ag-right-panel">
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

          <section class="memory-mode-flags">
            <span
              v-for="badge in modeBadges"
              :key="badge.key"
              class="memory-chip"
              :class="badge.enabled ? 'tone-green' : 'tone-muted'"
            >
              {{ badge.label }}: {{ badge.enabled ? "on" : "off" }}
            </span>
          </section>

          <section class="memory-metadata-panel">
            <div class="memory-section-head">
              <span>{{ t("agentOS.memory.metadataLabel") }}</span>
            </div>
            <dl class="memory-metadata-list">
              <div>
                <dt>{{ t("agentOS.memory.userLabel") }}</dt>
                <dd :title="selectedMemory.user_id">{{ selectedMemory.user_id || "default" }}</dd>
              </div>
              <div>
                <dt>{{ t("agentOS.memory.agentLabel") }}</dt>
                <dd :title="selectedMemory.agent_id">{{ selectedMemory.agent_id || "-" }}</dd>
              </div>
              <div>
                <dt>{{ t("agentOS.memory.teamLabel") }}</dt>
                <dd :title="selectedMemory.team_id">{{ selectedMemory.team_id || "-" }}</dd>
              </div>
              <div>
                <dt>{{ t("agentOS.memory.createdLabel") }}</dt>
                <dd :title="selectedMemory.created_at">{{ formatTime(selectedMemory.created_at) }}</dd>
              </div>
              <div>
                <dt>{{ t("agentOS.memory.updatedLabel") }}</dt>
                <dd :title="selectedMemory.updated_at">{{ formatTime(selectedMemory.updated_at) }}</dd>
              </div>
              <div>
                <dt>{{ t("agentOS.memory.feedbackLabel") }}</dt>
                <dd :title="selectedMemory.feedback">{{ selectedMemory.feedback || "-" }}</dd>
              </div>
              <div class="memory-source-row">
                <dt>{{ t("agentOS.memory.inputLabel") }}</dt>
                <dd class="memory-metadata-source" :title="selectedMemory.input">
                  <div
                    class="memory-source-viewer"
                    :class="{ expanded: sourceInputExpanded, empty: !selectedSourceInput.trim() }"
                  >
                    <div class="memory-source-toolbar">
                      <div class="memory-source-actions">
                        <el-select
                          v-model="sourceInputViewMode"
                          size="small"
                          class="memory-source-mode-select"
                          :aria-label="t('agentOS.memory.sourceModeLabel')"
                        >
                          <el-option :label="t('agentOS.memory.sourceModeText')" value="text" />
                          <el-option :label="t('agentOS.memory.sourceModeJson')" value="json" />
                          <el-option :label="t('agentOS.memory.sourceModeMarkdown')" value="markdown" />
                        </el-select>
                        <el-button
                          size="small"
                          plain
                          class="cursor-pointer"
                          :disabled="!selectedSourceInput.trim()"
                          @click="copySourceInput"
                        >
                          {{ t("agentOS.memory.sourceCopy") }}
                        </el-button>
                        <el-button size="small" plain class="cursor-pointer" @click="sourceInputExpanded = !sourceInputExpanded">
                          {{ sourceInputExpanded ? t("agentOS.memory.sourceCollapse") : t("agentOS.memory.sourceExpand") }}
                        </el-button>
                      </div>
                    </div>
                    <pre
                      v-if="sourceInputViewMode === 'json'"
                      class="memory-source-content memory-source-json"
                      :class="{ expanded: sourceInputExpanded, empty: !selectedSourceInput.trim() }"
                    >{{ sourceInputTextForMode("json") }}</pre>
                    <div
                      v-else
                      class="memory-source-content memory-source-render"
                      :class="{ expanded: sourceInputExpanded, empty: !selectedSourceInput.trim() }"
                      v-html="renderSourceInput()"
                    />
                  </div>
                </dd>
              </div>
            </dl>
          </section>
        </template>

        <div v-else class="memory-empty">
          <el-icon><User /></el-icon>
          <strong>{{ t("agentOS.memory.emptyTitle") }}</strong>
          <span>{{ t("agentOS.memory.emptyDescription") }}</span>
        </div>
      </aside>
    </main>

    <el-dialog
      v-model="editDialogVisible"
      class="memory-edit-dialog"
      :title="t('agentOS.memory.editMemoryTitle')"
      width="min(560px, calc(100vw - 32px))"
      destroy-on-close
    >
      <el-form label-position="top">
        <el-form-item :label="t('agentOS.memory.memoryLabel')">
          <el-input
            v-model="editForm.memory"
            type="textarea"
            :autosize="{ minRows: 4, maxRows: 8 }"
            :placeholder="t('agentOS.memory.editMemoryPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('agentOS.memory.topicsLabel')">
          <el-select
            v-model="editForm.topics"
            class="memory-topic-editor"
            multiple
            filterable
            allow-create
            default-first-option
            :placeholder="t('agentOS.memory.editTopicsPlaceholder')"
          >
            <el-option
              v-for="topic in topicOptions"
              :key="topic"
              :label="topic"
              :value="topic"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">
          {{ t("common.actions.cancel") }}
        </el-button>
        <el-button type="primary" :loading="loading" @click="saveMemoryUpdate">
          {{ t("agentOS.memory.saveMemory") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import {
  Delete,
  EditPen,
  Refresh,
  Search,
  User,
} from "@element-plus/icons-vue"
import { ElMessage, ElMessageBox } from "element-plus"
import MarkdownIt from "markdown-it"
import { useI18n } from "vue-i18n"
import { useOsControlApi } from "../composables/useApi"
import { copyToClipboard } from "../lib/clipboard"
import {
  defaultMemoryPayload as buildDefaultMemoryPayload,
  memoryDisplayStatus,
  memoryModeBadges,
  normalizeMemoryPayload,
  payloadAfterMemoryLoadFailure,
} from "../modules/memoryControl"
import { useAuthStore } from "../stores/auth"
import type {
  MemoryControlResponse,
  MemoryItem,
  MemoryQueryParams,
  MemoryUserSummary,
} from "../types"

const { t, locale } = useI18n()
const authStore = useAuthStore()
const { loading, error, fetchMemory, deleteMemory, updateMemory } = useOsControlApi()
const markdownRenderer = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})
const payload = ref<MemoryControlResponse | null>(null)
const selectedMemoryId = ref("")
const editDialogVisible = ref(false)
const sourceInputViewMode = ref<SourceInputViewMode>("text")
const sourceInputExpanded = ref(false)

type SourceInputViewMode = "text" | "json" | "markdown"

const filters = reactive({
  user_id: "",
  topic: "",
  search: "",
  page: 1,
  limit: 50,
})

const editForm = reactive({
  memory: "",
  topics: [] as string[],
})

const defaultMemoryPayload = (): MemoryControlResponse => buildDefaultMemoryPayload({
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
const canWriteMemory = computed(() => authStore.hasPermission("memory:write:own"))
const riskUserCount = computed(() => userOptions.value.filter((user) => user.status === "risk").length)
const reviewUserCount = computed(() => userOptions.value.filter((user) => user.status === "review").length)
const healthyUserCount = computed(() => userOptions.value.filter((user) => user.status === "healthy" || user.status === "stored").length)
const maxUserMemories = computed(() => Math.max(1, ...userOptions.value.map((user) => user.total_memories)))

const selectedMemory = computed<MemoryItem | null>(() => {
  if (!memories.value.length) return null
  return memories.value.find((memory) => memory.id === selectedMemoryId.value) || memories.value[0] || null
})
const selectedSourceInput = computed(() => selectedMemory.value?.input || "")

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
    hint: t("agentOS.memory.modeLabel"),
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
  return statusTone(memoryDisplayStatus(memory, userOptions.value))
}

const userBarStyle = (user: MemoryUserSummary) => {
  const size = Math.max(10, Math.round((user.total_memories / maxUserMemories.value) * 100))
  return { "--memory-user-size": `${size}%` }
}

const parseSourceInputJson = (text: string) => {
  try {
    return { ok: true as const, value: JSON.parse(text) as unknown }
  } catch {
    return { ok: false as const, value: null }
  }
}

const sourceInputTextForMode = (mode: SourceInputViewMode = sourceInputViewMode.value) => {
  const text = selectedSourceInput.value
  if (!text.trim()) return t("agentOS.memory.sourceEmpty")
  if (mode !== "json") return text
  const parsed = parseSourceInputJson(text)
  if (!parsed.ok) return text
  return JSON.stringify(parsed.value, null, 2)
}

const renderSourceInput = () => {
  const text = sourceInputTextForMode(sourceInputViewMode.value)
  return markdownRenderer.render(text)
}

const copySourceInput = async () => {
  const text = sourceInputTextForMode(sourceInputViewMode.value).trim()
  if (!text) return
  if (await copyToClipboard(text)) {
    ElMessage.success(t("common.clipboard.copied"))
  } else {
    ElMessage.error(t("common.clipboard.failed"))
  }
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

const selectMemory = (memoryId: string) => {
  selectedMemoryId.value = memoryId
  sourceInputExpanded.value = false
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
    ElMessage.error(t("agentOS.memory.updateEmpty"))
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
    ElMessage.success(t("agentOS.memory.updateSuccess"))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("agentOS.memory.updateFailed"))
  }
}

const deleteSelectedMemory = async (memory?: MemoryItem) => {
  const targetMemory = memory || selectedMemory.value
  if (!canWriteMemory.value || !targetMemory) return
  selectedMemoryId.value = targetMemory.id
  try {
    await ElMessageBox.confirm(
      t("agentOS.memory.deleteConfirmMessage"),
      t("agentOS.memory.deleteConfirmTitle"),
      {
        confirmButtonText: t("common.actions.delete"),
        cancelButtonText: t("common.actions.cancel"),
        type: "warning",
      },
    )
    await deleteMemory(targetMemory.id, currentMutationUserId(targetMemory))
    await loadMemory()
    ElMessage.success(t("agentOS.memory.deleteSuccess"))
  } catch (err) {
    if (err !== "cancel") {
      ElMessage.error(err instanceof Error ? err.message : t("agentOS.memory.deleteFailed"))
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
  color: var(--memory-text);
}

.memory-control :where(div, section, aside, main, article, p, span, strong, small, button, dl, dt, dd, pre, ol, ul, li, table, th, td) {
  min-width: 0;
}

.memory-panel-head p,
.memory-detail-head p,
.memory-section-head > span,
.memory-query-label strong {
  margin: 0;
  color: var(--memory-muted);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0;
  line-height: 1.35;
  text-transform: uppercase;
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

.memory-chip.tone-green {
  border-color: color-mix(in srgb, var(--memory-green) 38%, var(--memory-border));
  background: var(--memory-green-soft);
  color: var(--memory-green);
}

.memory-chip.tone-muted {
  color: var(--memory-muted);
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

.memory-user-row {
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
.memory-row-main:focus-visible {
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
.memory-row-copy small {
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
.memory-status-board .tone-green {
  border-color: color-mix(in srgb, var(--memory-green) 38%, var(--memory-border));
  background: var(--memory-green-soft);
  color: var(--memory-green);
}

.memory-status.tone-yellow,
.memory-status-board .tone-yellow {
  border-color: color-mix(in srgb, var(--memory-yellow) 44%, var(--memory-border));
  background: var(--memory-yellow-soft);
  color: var(--memory-yellow);
}

.memory-status.tone-red,
.memory-status-board .tone-red {
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
  display: grid;
  width: 100%;
  align-items: start;
  grid-template-columns: 4px minmax(0, 1fr) auto;
  gap: 12px;
  border-bottom: 1px solid var(--memory-row-border);
  padding: 12px;
  background: transparent;
  color: inherit;
  text-align: left;
}

.memory-row-status {
  display: block;
  width: 4px;
  height: 100%;
  min-height: 68px;
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

.memory-row-main {
  display: grid;
  min-width: 0;
  border: 0;
  background: transparent;
  padding: 0;
  color: inherit;
  cursor: pointer;
  gap: 8px;
  text-align: left;
}

.memory-row-copy strong {
  display: block;
  overflow: hidden;
  color: var(--memory-heading);
  font-size: 13px;
  font-weight: 850;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-row-facts {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  gap: 6px;
}

.memory-row-actions {
  display: flex;
  min-width: max-content;
  align-items: flex-start;
  justify-content: flex-end;
  gap: 6px;
}

.memory-row-actions :deep(.el-button) {
  margin-left: 0;
}

.memory-action-button {
  width: 28px;
  height: 28px;
  padding: 0;
}

.memory-action-button :deep(.el-icon) {
  margin: 0;
}

.memory-detail-head {
  align-items: center;
}

.memory-mode-flags {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  gap: 6px;
  border-bottom: 1px solid var(--memory-border);
  padding: 10px 12px 0;
}

.memory-metadata-panel {
  flex: 0 0 auto;
  padding: 12px;
  border-bottom: 1px solid var(--memory-border);
}

.memory-metadata-list {
  display: grid;
  margin: 8px 0 0;
}

.memory-metadata-list > div {
  display: grid;
  align-items: baseline;
  grid-template-columns: minmax(68px, 92px) minmax(0, 1fr);
  gap: 10px;
  border-top: 1px solid var(--memory-row-border);
  padding: 8px 0;
}

.memory-metadata-list dt {
  color: var(--memory-muted);
  font-size: 11px;
  font-weight: 800;
  line-height: 1.35;
  text-transform: uppercase;
}

.memory-metadata-list dd {
  overflow: hidden;
  margin: 0;
  color: var(--memory-heading);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  font-weight: 800;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-metadata-list .memory-metadata-source {
  overflow: visible;
  white-space: normal;
  word-break: normal;
}

.memory-metadata-list .memory-source-row {
  align-items: stretch;
  grid-template-columns: minmax(0, 1fr);
  gap: 6px;
}

.memory-source-viewer {
  overflow: hidden;
  border: 1px solid var(--memory-border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--memory-panel-raised) 70%, var(--memory-bg));
}

.memory-source-toolbar {
  border-bottom: 1px solid var(--memory-row-border);
  padding: 6px;
}

.memory-source-actions {
  display: grid;
  align-items: center;
  grid-template-columns: minmax(92px, 1fr) auto auto;
  gap: 6px;
  width: 100%;
}

.memory-source-mode-select {
  width: 100%;
}

.memory-source-content {
  overflow: auto;
  max-height: 178px;
  margin: 0;
  padding: 10px;
  color: var(--memory-heading);
  font-size: 12px;
  font-weight: 700;
  line-height: 1.6;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.memory-source-content.expanded {
  max-height: 440px;
}

.memory-source-content.empty {
  color: var(--memory-muted);
  font-style: italic;
}

.memory-source-json {
  font-family: "JetBrains Mono", "Fira Code", monospace;
  white-space: pre;
}

.memory-source-render {
  white-space: normal;
}

.memory-source-render :where(p, ul, ol, pre, blockquote, table) {
  margin: 0;
}

.memory-source-render :where(p + p, p + ul, p + ol, ul + p, ol + p, pre + p, blockquote + table) {
  margin-top: 10px;
}

.memory-source-render :where(ul, ol) {
  padding-left: 20px;
}

.memory-source-render li + li {
  margin-top: 4px;
}

.memory-source-render blockquote {
  border-left: 3px solid var(--memory-border-strong);
  padding-left: 9px;
  color: var(--memory-text);
}

.memory-source-render :where(strong, b) {
  color: var(--memory-heading);
  font-weight: 850;
}

.memory-source-render a {
  color: var(--memory-blue);
  font-weight: 800;
  text-decoration: none;
}

.memory-source-render code {
  border: 1px solid var(--memory-row-border);
  border-radius: 5px;
  background: var(--memory-panel-soft);
  padding: 1px 5px;
  color: var(--memory-blue);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 0.94em;
}

.memory-source-render pre {
  overflow: auto;
  border: 1px solid var(--memory-row-border);
  border-radius: 7px;
  background: var(--memory-panel-soft);
  padding: 9px;
}

.memory-source-render pre code {
  border: 0;
  background: transparent;
  padding: 0;
  color: inherit;
}

.memory-source-render table {
  display: block;
  overflow-x: auto;
  width: 100%;
  border-collapse: collapse;
}

.memory-source-render th,
.memory-source-render td {
  border-bottom: 1px solid var(--memory-row-border);
  padding: 5px 7px;
  text-align: left;
  vertical-align: top;
}

.memory-source-render th {
  color: var(--memory-heading);
  font-weight: 850;
}

.memory-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.memory-topic-editor {
  width: 100%;
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

@media (max-width: 1180px) {
  .memory-query-panel {
    grid-template-columns: 1fr;
  }

  .memory-query-controls {
    grid-template-columns: minmax(220px, 1fr) minmax(160px, 220px) minmax(150px, 200px);
  }

  .memory-query-actions {
    justify-content: flex-start;
    flex-wrap: wrap;
  }
}

@media (max-width: 1120px) {
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
    flex: 0 0 auto;
    grid-template-columns: 1fr;
    min-height: auto;
  }

  .memory-queue-panel {
    max-height: 320px;
  }

  .memory-list-panel,
  .memory-detail-panel {
    overflow: visible;
  }

  .memory-list {
    overflow: visible;
  }

  .memory-detail-panel {
    grid-column: auto;
    max-height: none;
  }
}

@media (max-width: 680px) {
  .memory-query-panel {
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

  .memory-row-actions {
    grid-column: 2;
    justify-content: flex-start;
    flex-wrap: wrap;
  }
}
</style>
