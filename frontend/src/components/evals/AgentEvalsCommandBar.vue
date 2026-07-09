<template>
  <section class="ag-content-panel grid gap-3">
    <div class="flex min-w-0 flex-wrap items-start justify-between gap-3">
      <div class="grid min-w-0 gap-1">
        <span class="text-[10px] font-820 uppercase text-[var(--ag-muted)]">{{ t("agentEvals.gate.kicker") }}</span>
        <div class="flex min-w-0 flex-wrap items-center gap-2">
          <strong class="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[15px] font-780 text-[var(--ag-heading)]">
            {{ t("agentEvals.gate.title") }}
          </strong>
          <StatusChip tone="blue" :title="t('agentEvals.performance.hiddenRun')">
            {{ t("agentEvals.performance.label") }} · {{ t("agentEvals.performance.hiddenRun") }}
          </StatusChip>
        </div>
      </div>
      <div class="flex shrink-0 flex-wrap items-center gap-2">
        <el-button size="small" :loading="loading" @click="$emit('refresh')">
          {{ t("agentEvals.actions.refresh") }}
        </el-button>
        <el-button size="small" type="primary" :disabled="!canRun || !selectedSuiteId" @click="$emit('run-suite')">
          <el-icon><VideoPlay /></el-icon>
          {{ t("agentEvals.actions.runSuite") }}
        </el-button>
      </div>
    </div>

    <div class="flex h-[9px] overflow-hidden rounded-full border border-[var(--ag-border)] bg-[var(--ag-panel-soft)]" :aria-label="t('agentEvals.gate.verdictRail')">
      <span
        v-for="segment in verdictSegments"
        :key="segment.key"
        class="block min-w-0 transition-[inline-size]"
        :class="segmentClass(segment.tone)"
        :style="{ inlineSize: segment.width }"
        :title="segment.title"
      />
    </div>

    <div class="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(430px,0.85fr)]">
      <div class="grid min-w-0 grid-cols-2 gap-2 md:grid-cols-3 2xl:grid-cols-5">
        <MetricChip
          v-for="card in summaryCards"
          :key="card.label"
          :label="card.label"
          :value="card.value"
          :tone="card.tone"
          :title="card.hint"
        />
      </div>

      <div class="grid min-w-0 gap-2 sm:grid-cols-2 xl:grid-cols-[minmax(112px,1fr)_minmax(112px,0.9fr)_minmax(104px,0.8fr)_minmax(150px,1.2fr)]" :aria-label="t('agentEvals.filters.ariaLabel')">
        <el-select v-model="filters.suiteId" size="small" clearable filterable :placeholder="t('agentEvals.filters.suite')">
          <el-option :label="t('agentEvals.filters.all')" value="all" />
          <el-option v-for="suite in suites" :key="suite.id" :label="suite.name" :value="suite.id" />
        </el-select>
        <el-select v-model="filters.evalType" size="small" :placeholder="t('agentEvals.filters.evalType')">
          <el-option :label="t('agentEvals.filters.all')" value="all" />
          <el-option label="AccuracyEval" value="accuracy" />
          <el-option label="AgentJudgeEval" value="agent_as_judge" />
          <el-option label="ReliabilityEval" value="reliability" />
          <el-option label="PerformanceEval" value="performance" />
        </el-select>
        <el-select v-model="filters.status" size="small" :placeholder="t('agentEvals.filters.status')">
          <el-option :label="t('agentEvals.filters.all')" value="all" />
          <el-option label="passed" value="passed" />
          <el-option label="failed" value="failed" />
          <el-option label="queued" value="queued" />
          <el-option label="running" value="running" />
        </el-select>
        <el-input v-model="filters.keyword" size="small" clearable :placeholder="t('agentEvals.filters.keyword')">
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Search, VideoPlay } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import MetricChip from "../common/MetricChip.vue"
import StatusChip from "../common/StatusChip.vue"
import type { EvalFilters } from "../../composables/useAgentEvalsWorkbench"
import type { EvalSummaryCard, EvalTone } from "../../modules/agentEvalsWorkbench"
import type { AgentEvalSuite } from "../../types"

defineProps<{
  loading: boolean
  canRun: boolean
  selectedSuiteId: string
  filters: EvalFilters
  suites: AgentEvalSuite[]
  summaryCards: EvalSummaryCard[]
  verdictSegments: Array<{ key: string; tone: EvalTone; width: string; title: string }>
}>()

defineEmits<{
  refresh: []
  "run-suite": []
}>()

const { t } = useI18n()

const segmentClass = (tone: EvalTone) => {
  if (tone === "green") return "bg-[var(--ag-green)]"
  if (tone === "red") return "bg-[var(--ag-red)]"
  if (tone === "yellow") return "bg-[var(--ag-yellow)]"
  return "bg-[color-mix(in_srgb,var(--ag-blue)_62%,var(--ag-panel-soft))]"
}
</script>
