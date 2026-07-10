<template>
  <aside class="ag-workspace-panel flex min-h-0 flex-col overflow-hidden border-transparent bg-[var(--ag-container-bg)] shadow-none">
    <PanelHeader class="px-4 pb-3 pt-4 sm:px-5" :title="t('workbench.memory.queueTitle')" :subtitle="userPanelSummary">
      <template #actions>
        <DataChip
          :label="t('workbench.memory.statusReview')"
          :value="thresholdSummary"
          tone="yellow"
          :title="thresholdTitle"
        />
      </template>
    </PanelHeader>

    <div class="grid flex-0 grid-cols-3 gap-2 px-4 pb-3 sm:px-5">
      <DataChip :label="t('workbench.memory.statusRisk')" :value="riskUserCount" tone="red" />
      <DataChip :label="t('workbench.memory.statusReview')" :value="reviewUserCount" tone="yellow" />
      <DataChip :label="t('workbench.memory.statusHealthy')" :value="healthyUserCount" tone="green" />
    </div>

    <div v-if="userOptions.length" class="min-h-0 overflow-auto px-2 pb-2 sm:px-3 sm:pb-3">
      <button
        v-for="user in userOptions"
        :key="user.user_id"
        type="button"
        :class="[
          'grid w-full grid-cols-[10px_minmax(0,1fr)_auto] items-center gap-3 rounded-xl border border-transparent px-3 py-3 text-left text-[var(--ag-text)] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--ag-blue)] sm:px-4',
          user.user_id === filters.user_id
            ? 'bg-[var(--ag-blue-soft)] shadow-[inset_0_0_0_1px_var(--ag-border)]'
            : 'bg-transparent hover:bg-[var(--ag-panel-soft)]',
        ]"
        :aria-pressed="user.user_id === filters.user_id"
        @click="$emit('filter-user', user.user_id)"
      >
        <span class="block h-11 w-[10px] overflow-hidden rounded-full bg-[var(--ag-panel-soft)]">
          <span class="block h-[var(--mem-user-size)] min-h-[10px] w-full rounded-full" :class="railToneClass(user.status)" :style="userBarStyle(user)" />
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
          <b class="rounded-[var(--ag-radius-control)] bg-[var(--ag-panel-soft)] px-2 py-0.5 font-mono text-[11px] text-[var(--ag-heading)]">
            {{ user.total_memories }}
          </b>
        </span>
      </button>
    </div>

    <EmptyState v-else-if="!loading" class="min-h-[140px] px-4 py-6">
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
