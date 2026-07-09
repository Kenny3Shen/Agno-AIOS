<template>
  <aside class="ag-right-panel flex min-h-0 flex-col overflow-hidden">
    <template v-if="selectedMemory">
      <PanelHeader :title="t('workbench.memory.detailTitle')" :subtitle="selectedMemory.id">
        <template #actions>
          <StatusDot :label="statusLabel(selectedStatus)" :tone="selectedStatusTone">
            {{ statusLabel(selectedStatus) }}
          </StatusDot>
        </template>
      </PanelHeader>

      <section class="flex flex-0 flex-wrap gap-1.5 border-b border-[var(--ag-border)] px-3 py-2.5">
        <DataChip
          v-for="badge in modeBadges"
          :key="badge.key"
          :label="badge.label"
          :value="badge.enabled ? 'on' : 'off'"
          :tone="badge.enabled ? 'green' : 'muted'"
        />
      </section>

      <section class="min-h-0 overflow-auto p-3">
        <SectionHeader :title="t('workbench.memory.metadataLabel')" />
        <dl class="mt-2 grid gap-0">
          <div
            v-for="item in metadataItems"
            :key="item.key"
            class="grid grid-cols-[minmax(68px,92px)_minmax(0,1fr)] items-baseline gap-2 border-t border-[var(--ag-border)] py-2"
          >
            <dt class="text-[11px] font-800 uppercase text-[var(--ag-muted)]">{{ item.label }}</dt>
            <dd class="m-0 overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[11px] font-800 text-[var(--ag-heading)]" :title="item.raw">
              {{ item.value }}
            </dd>
          </div>
        </dl>

        <section class="mt-3 grid gap-2">
          <SectionHeader :title="t('workbench.memory.inputLabel')" />
          <PayloadViewer
            :key="selectedMemory.id"
            :text="selectedMemory.input"
            mode="text"
            :empty-text="t('workbench.memory.sourceEmpty')"
            :copy-label="t('workbench.memory.sourceCopy')"
            :expand-label="t('workbench.memory.sourceExpand')"
            :collapse-label="t('workbench.memory.sourceCollapse')"
            :max-collapsed-height="178"
          />
        </section>
      </section>
    </template>

    <EmptyState v-else class="min-h-[220px]" :icon="User">
      <span class="grid justify-items-center gap-1">
        <strong class="text-[var(--ag-heading)]">{{ t("workbench.memory.emptyTitle") }}</strong>
        <span class="max-w-[320px] text-xs text-[var(--ag-muted)]">
          {{ t("workbench.memory.emptyDescription") }}
        </span>
      </span>
    </EmptyState>
  </aside>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { User } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import DataChip from "../common/DataChip.vue"
import EmptyState from "../common/EmptyState.vue"
import PanelHeader from "../common/PanelHeader.vue"
import PayloadViewer from "../common/PayloadViewer.vue"
import SectionHeader from "../common/SectionHeader.vue"
import StatusDot from "../common/StatusDot.vue"
import type { MemoryTone } from "../../composables/useMemoryWorkbenchController"
import type { MemoryModeBadge } from "../../modules/memoryControl"
import type { MemoryItem } from "../../types"

const props = defineProps<{
  formatTime: (value?: string) => string
  modeBadges: MemoryModeBadge[]
  selectedMemory: MemoryItem | null
  selectedStatus: string
  selectedStatusTone: MemoryTone
  statusLabel: (status?: string) => string
}>()

const { t } = useI18n()

const metadataItems = computed(() => {
  const memory = props.selectedMemory
  if (!memory) return []
  return [
    {
      key: "user",
      label: t("workbench.memory.userLabel"),
      raw: memory.user_id,
      value: memory.user_id || "default",
    },
    {
      key: "agent",
      label: t("workbench.memory.agentLabel"),
      raw: memory.agent_id,
      value: memory.agent_id || "-",
    },
    {
      key: "team",
      label: t("workbench.memory.teamLabel"),
      raw: memory.team_id,
      value: memory.team_id || "-",
    },
    {
      key: "created",
      label: t("workbench.memory.createdLabel"),
      raw: memory.created_at,
      value: props.formatTime(memory.created_at),
    },
    {
      key: "updated",
      label: t("workbench.memory.updatedLabel"),
      raw: memory.updated_at,
      value: props.formatTime(memory.updated_at),
    },
    {
      key: "feedback",
      label: t("workbench.memory.feedbackLabel"),
      raw: memory.feedback,
      value: memory.feedback || "-",
    },
  ]
})
</script>
