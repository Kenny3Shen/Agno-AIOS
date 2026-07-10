<template>
  <aside class="ag-right-panel flex min-h-0 flex-col overflow-hidden border-transparent bg-[var(--ag-container-bg)] p-0 shadow-none lg:col-span-2 xl:col-span-1">
    <template v-if="selectedMemory">
      <PanelHeader class="px-4 pb-3 pt-4 sm:px-5" :title="t('workbench.memory.detailTitle')" :subtitle="selectedMemory.id">
        <template #actions>
          <StatusDot :label="statusLabel(selectedStatus)" :tone="selectedStatusTone">
            {{ statusLabel(selectedStatus) }}
          </StatusDot>
        </template>
      </PanelHeader>

      <section class="min-h-0 overflow-auto px-4 pb-4 sm:px-5 sm:pb-5">
        <div class="flex flex-wrap gap-2 border-b border-[var(--ag-border)] pb-4">
          <DataChip
            v-for="badge in modeBadges"
            :key="badge.key"
            :label="badge.label"
            :value="badge.enabled ? 'on' : 'off'"
            :tone="badge.enabled ? 'green' : 'muted'"
          />
        </div>

        <section class="grid gap-3 pt-5">
          <SectionHeader :title="t('workbench.memory.metadataLabel')" />
          <dl class="grid gap-3 sm:grid-cols-2">
            <div
              v-for="item in metadataItems"
              :key="item.key"
              class="grid gap-1 rounded-lg bg-[var(--ag-panel-soft)] px-3 py-3"
            >
              <dt class="text-[11px] font-800 uppercase tracking-[0.04em] text-[var(--ag-muted)]">{{ item.label }}</dt>
              <dd class="m-0 overflow-hidden text-ellipsis whitespace-nowrap font-mono text-xs font-760 text-[var(--ag-heading)]" :title="item.raw">
                {{ item.value }}
              </dd>
            </div>
          </dl>
        </section>

        <section class="grid gap-3 pt-5">
          <SectionHeader :title="t('workbench.memory.inputLabel')" />
          <div
            class="overflow-hidden rounded-xl border border-[var(--ag-border)] bg-[var(--ag-panel)]"
          >
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
          </div>
        </section>
      </section>
    </template>

    <EmptyState v-else class="min-h-[220px] px-4 py-6" :icon="User">
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
