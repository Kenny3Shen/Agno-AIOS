<template>
  <section class="ag-workspace-panel flex min-h-0 flex-col overflow-hidden">
    <PanelHeader :title="t('workbench.memory.memoriesTitle')" :subtitle="resultSummary">
      <template #actions>
        <span class="flex max-w-[min(420px,50vw)] flex-wrap justify-end gap-1.5" :title="activeFilterSummary">
          <DataChip
            v-if="filters.user_id"
            :label="t('workbench.memory.userLabel')"
            :value="filters.user_id"
            tone="blue"
          />
          <DataChip
            v-if="filters.topic"
            :label="t('workbench.memory.topicsLabel')"
            :value="filters.topic"
            tone="green"
          />
          <DataChip
            v-if="filters.search"
            :label="t('workbench.memory.searchChip')"
            :value="filters.search"
            tone="yellow"
          />
        </span>
      </template>
    </PanelHeader>

    <div v-if="memories.length" class="min-h-0 overflow-auto">
      <article
        v-for="memory in memories"
        :key="memory.id"
        :class="[
          'grid w-full grid-cols-[minmax(0,1fr)_auto] gap-3 border-b border-[var(--ag-border)] p-3 transition-colors hover:bg-[var(--ag-blue-soft)]',
          memory.id === selectedMemory?.id ? 'bg-[var(--ag-blue-soft)]' : '',
        ]"
      >
        <button
          type="button"
          class="grid min-w-0 gap-2 border-0 bg-transparent p-0 text-left text-[var(--ag-text)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--ag-blue)]"
          :aria-pressed="memory.id === selectedMemory?.id"
          @click="$emit('select', memory.id)"
        >
          <span class="flex min-w-0 items-start gap-2">
            <StatusDot :label="statusLabelForMemory(memory)" :tone="memoryStatusTone(memory)" />
            <strong class="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-850 text-[var(--ag-heading)]" :title="memory.memory">
              {{ memory.memory || t("workbench.memory.emptyMemory") }}
            </strong>
          </span>
          <span class="flex min-w-0 flex-wrap gap-1.5 pl-5">
            <DataChip
              v-if="!memory.topics.length"
              :label="t('workbench.memory.topicsLabel')"
              :value="t('workbench.memory.noTopics')"
              tone="muted"
            />
            <DataChip
              v-for="topic in memory.topics"
              :key="`${memory.id}-${topic}`"
              :label="t('workbench.memory.topicsLabel')"
              :value="topic"
              tone="muted"
              :title="topic"
            />
          </span>
        </button>

        <span v-if="canWriteMemory || canDeleteMemory" class="flex shrink-0 items-start gap-1.5">
          <el-button
            v-if="canWriteMemory"
            size="small"
            plain
            circle
            :aria-label="t('workbench.memory.editMemory')"
            :title="t('workbench.memory.editMemory')"
            :disabled="loading"
            @click.stop="$emit('edit', memory)"
          >
            <el-icon><EditPen /></el-icon>
          </el-button>
          <el-button
            v-if="canDeleteMemory"
            size="small"
            type="danger"
            plain
            circle
            :aria-label="t('workbench.memory.deleteMemory')"
            :title="t('workbench.memory.deleteMemory')"
            :disabled="loading"
            @click.stop="$emit('delete', memory)"
          >
            <el-icon><Delete /></el-icon>
          </el-button>
        </span>
      </article>
    </div>

    <EmptyState v-else-if="!loading" class="min-h-[220px]" :icon="User">
      <span class="grid justify-items-center gap-1">
        <strong class="text-[var(--ag-heading)]">{{ t("workbench.memory.emptyTitle") }}</strong>
        <span class="max-w-[360px] text-xs text-[var(--ag-muted)]">
          {{ t("workbench.memory.emptyDescription") }}
        </span>
      </span>
    </EmptyState>

    <div v-if="total > filters.limit" class="flex flex-0 justify-end border-t border-[var(--ag-border)] px-3 py-2">
      <el-pagination
        :current-page="filters.page"
        :page-size="filters.limit"
        layout="prev, pager, next"
        :total="total"
        @current-change="$emit('page-change', $event)"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { Delete, EditPen, User } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import DataChip from "../common/DataChip.vue"
import EmptyState from "../common/EmptyState.vue"
import PanelHeader from "../common/PanelHeader.vue"
import StatusDot from "../common/StatusDot.vue"
import type {
  MemoryTone,
  MemoryWorkbenchFilters,
} from "../../composables/useMemoryWorkbenchController"
import type { MemoryItem } from "../../types"

const props = defineProps<{
  activeFilterSummary: string
  canDeleteMemory: boolean
  canWriteMemory: boolean
  filters: MemoryWorkbenchFilters
  loading: boolean
  memories: MemoryItem[]
  memoryStatusTone: (memory: MemoryItem) => MemoryTone
  resultSummary: string
  selectedMemory: MemoryItem | null
  statusLabel: (status?: string) => string
  total: number
}>()

defineEmits<{
  delete: [memory: MemoryItem]
  edit: [memory: MemoryItem]
  "page-change": [page: number]
  select: [memoryId: string]
}>()

const { t } = useI18n()

const statusLabelForMemory = (memory: MemoryItem) => {
  const tone = props.memoryStatusTone(memory)
  if (tone === "red") return props.statusLabel("risk")
  if (tone === "yellow") return props.statusLabel("review")
  if (tone === "green") return props.statusLabel("stored")
  return props.statusLabel(memory.status)
}
</script>
