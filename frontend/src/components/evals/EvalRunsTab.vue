<template>
  <div class="grid min-w-0 gap-3">
    <SectionHeader :title="t('agentEvals.panels.runs')" :count="agnoRuns.length" />

    <div v-if="agnoRuns.length" class="grid min-w-0 gap-2">
      <button
        v-for="run in agnoRuns"
        :key="run.id"
        type="button"
        class="ag-surface-row grid w-full cursor-pointer items-center gap-2 text-left md:grid-cols-[minmax(0,1fr)_minmax(112px,0.55fr)_90px_122px]"
        :class="{ 'border-[color-mix(in_srgb,var(--ag-blue)_58%,var(--ag-border))] bg-[var(--ag-blue-soft)]': selectedRunId === run.id }"
        @click="$emit('select-run', run.id)"
      >
        <span class="flex min-w-0 items-center gap-2">
          <StatusDot :label="runStatus(run)" :tone="runTone(run)" />
          <strong class="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[13px] text-[var(--ag-heading)]" :title="run.name || run.run_id">
            {{ run.name || run.run_id }}
          </strong>
        </span>
        <span class="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-xs text-[var(--ag-muted)]">
          {{ evalTypeLabel(run.eval_type) }}
        </span>
        <DataChip :label="t('agentEvals.fields.score')" :value="scoreLabel(run.score)" />
        <small class="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-xs text-[var(--ag-muted)]">
          {{ formatTime(run.created_at) }}
        </small>
      </button>
    </div>

    <div v-else-if="!loading" class="ag-empty-state">
      <strong class="text-[13px] text-[var(--ag-heading)]">{{ t("agentEvals.empty.runsTitle") }}</strong>
      <span class="max-w-[360px]">{{ t("agentEvals.empty.runsDescription") }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n"
import DataChip from "../common/DataChip.vue"
import SectionHeader from "../common/SectionHeader.vue"
import StatusDot from "../common/StatusDot.vue"
import type { EvalTone } from "../../modules/agentEvalsWorkbench"
import type { AgentEvalAgnoRun } from "../../types"

defineProps<{
  agnoRuns: AgentEvalAgnoRun[]
  selectedRunId: string | null
  loading: boolean
  evalTypeLabel: (type: string) => string
  scoreLabel: (score?: number | null) => string
  formatTime: (value?: string | number | null) => string
}>()

defineEmits<{
  "select-run": [id: string]
}>()

const { t } = useI18n()

const runStatus = (run: AgentEvalAgnoRun) => {
  if (run.passed === false) return "failed"
  if (run.passed === true) return "passed"
  return "unknown"
}

const runTone = (run: AgentEvalAgnoRun): EvalTone => {
  if (run.passed === false) return "red"
  if (run.passed === true) return "green"
  return "blue"
}
</script>
