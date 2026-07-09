<template>
  <aside class="ag-workspace-panel flex min-h-0 flex-col overflow-hidden">
    <PanelHeader :title="t('workbench.memory.queueTitle')" :subtitle="userPanelSummary">
      <template #actions>
        <DataChip
          :label="t('workbench.memory.statusReview')"
          :value="thresholdSummary"
          tone="yellow"
          :title="thresholdTitle"
        />
      </template>
    </PanelHeader>

    <div class="grid flex-0 grid-cols-3 gap-2 border-b border-[var(--ag-border)] p-2">
      <DataChip :label="t('workbench.memory.statusRisk')" :value="riskUserCount" tone="red" />
      <DataChip :label="t('workbench.memory.statusReview')" :value="reviewUserCount" tone="yellow" />
      <DataChip :label="t('workbench.memory.statusHealthy')" :value="healthyUserCount" tone="green" />
    </div>

    <div v-if="userOptions.length" class="min-h-0 overflow-auto">
      <button
        v-for="user in userOptions"
        :key="user.user_id"
        type="button"
        :class="[
          'grid w-full grid-cols-[8px_minmax(0,1fr)_auto] items-center gap-2 border-0 border-b border-[var(--ag-border)] bg-transparent px-3 py-2.5 text-left text-[var(--ag-text)] transition-colors hover:bg-[var(--ag-blue-soft)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--ag-blue)]',
          user.user_id === filters.user_id ? 'bg-[var(--ag-blue-soft)]' : '',
        ]"
        :aria-pressed="user.user_id === filters.user_id"
        @click="$emit('filter-user', user.user_id)"
      >
        <span class="mem-user-rail">
          <span :class="railToneClass(user.status)" :style="userBarStyle(user)" />
        </span>
        <span class="grid min-w-0 gap-1">
          <strong class="overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-850 text-[var(--ag-heading)]" :title="user.user_id">
            {{ user.user_id }}
          </strong>
          <small class="overflow-hidden text-ellipsis whitespace-nowrap text-[11px] text-[var(--ag-muted)]">
            {{ formatTime(user.last_memory_updated_at) }}
          </small>
        </span>
        <span class="grid justify-items-end gap-1">
          <StatusDot :label="statusLabel(user.status)" :tone="statusTone(user.status)">
            {{ statusLabel(user.status) }}
          </StatusDot>
          <b class="rounded-[var(--ag-radius-control)] border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] px-1.5 py-0.5 font-mono text-[11px] text-[var(--ag-heading)]">
            {{ user.total_memories }}
          </b>
        </span>
      </button>
    </div>

    <EmptyState v-else-if="!loading" class="min-h-[140px]">
      {{ t("workbench.memory.noUsers") }}
    </EmptyState>
  </aside>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n"
import DataChip from "../common/DataChip.vue"
import EmptyState from "../common/EmptyState.vue"
import PanelHeader from "../common/PanelHeader.vue"
import StatusDot from "../common/StatusDot.vue"
import type {
  MemoryTone,
  MemoryWorkbenchFilters,
} from "../../composables/useMemoryWorkbenchController"
import type { MemoryUserSummary } from "../../types"

defineProps<{
  filters: MemoryWorkbenchFilters
  formatTime: (value?: string) => string
  healthyUserCount: number
  loading: boolean
  reviewUserCount: number
  riskUserCount: number
  statusLabel: (status?: string) => string
  statusTone: (status?: string) => MemoryTone
  thresholdSummary: string
  thresholdTitle: string
  userBarStyle: (user: MemoryUserSummary) => Record<string, string>
  userOptions: MemoryUserSummary[]
  userPanelSummary: string
}>()

defineEmits<{
  "filter-user": [userId: string]
}>()

const { t } = useI18n()

const railToneClass = (status?: string) => {
  if (status === "risk") return "bg-[var(--ag-red)]"
  if (status === "review") return "bg-[var(--ag-yellow)]"
  if (status === "healthy" || status === "stored") return "bg-[var(--ag-green)]"
  return "bg-[var(--ag-blue)]"
}
</script>

<style scoped>
.mem-user-rail {
  display: block;
  width: 8px;
  height: 42px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--ag-panel-soft);
}

.mem-user-rail > span {
  display: block;
  width: 100%;
  height: var(--mem-user-size);
  min-height: 10px;
  border-radius: inherit;
}
</style>
