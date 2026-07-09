<template>
  <div class="grid min-w-0 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(220px,0.55fr)]">
    <section class="grid min-w-0 gap-3 rounded-[var(--ag-radius-panel)] border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] p-3">
      <SectionHeader :title="t('agentEvals.panels.trends')" :count="trends.by_eval_type.length" />
      <div v-if="trends.by_eval_type.length" class="grid min-w-0 gap-2">
        <div
          v-for="item in trends.by_eval_type"
          :key="item.eval_type"
          class="flex min-w-0 items-center justify-between gap-3 border-b border-[var(--ag-border)] py-2 last:border-b-0"
        >
          <span class="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-xs text-[var(--ag-muted)]">
            {{ evalTypeLabel(item.eval_type) }}
          </span>
          <DataChip label="passed" :value="`${item.passed} / ${item.total}`" tone="green" />
        </div>
      </div>
      <div v-else class="ag-empty-compact">{{ t("agentEvals.empty.runs") }}</div>
    </section>

    <section class="grid min-w-0 gap-3 rounded-[var(--ag-radius-panel)] border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] p-3">
      <SectionHeader :title="t('agentEvals.fields.status')" />
      <div class="flex min-w-0 flex-wrap gap-2">
        <StatusChip tone="green">passed {{ trends.by_status.passed }}</StatusChip>
        <StatusChip tone="red">failed {{ trends.by_status.failed }}</StatusChip>
        <StatusChip tone="blue">unknown {{ trends.by_status.unknown }}</StatusChip>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n"
import DataChip from "../common/DataChip.vue"
import SectionHeader from "../common/SectionHeader.vue"
import StatusChip from "../common/StatusChip.vue"
import type { AgentEvalTrendResponse } from "../../types"

defineProps<{
  trends: AgentEvalTrendResponse
  evalTypeLabel: (type: string) => string
}>()

const { t } = useI18n()
</script>
