<template>
  <div class="evaluation-console ag-page-flow">
    <el-alert v-if="error" class="page-alert" type="error" :title="error" show-icon />

    <AgentEvalsCommandBar
      :loading="loading"
      :can-run="canRun"
      :selected-suite-id="selectedSuiteId"
      :filters="filters"
      :suites="suites"
      :summary-cards="summaryCards"
      :verdict-segments="verdictSegments"
      @refresh="refreshWorkbench"
      @run-suite="runSelectedSuite"
    />

    <main class="grid min-w-0 gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(320px,360px)]">
      <section class="ag-workspace-panel min-w-0 overflow-hidden">
        <el-tabs v-model="activeTab" class="min-w-0">
          <el-tab-pane :label="t('agentEvals.tabs.cases')" name="cases">
            <EvalCasesTab
              :case-rows="caseRows"
              :filtered-cases="filteredCases"
              :selected-case-id="selectedCase?.id || selectedCaseId"
              :loading="loading"
              :can-run="canRun"
              :can-write="canWrite"
              :selected-suite-id="selectedSuiteId"
              :eval-type-label="evalTypeLabel"
              :status-tone="statusTone"
              @select-case="selectedCaseId = $event"
              @run-suite="runSelectedSuite"
              @run-case="runSelectedCase"
              @permission-notice="showPermissionNotice"
            />
          </el-tab-pane>

          <el-tab-pane :label="t('agentEvals.tabs.runs')" name="runs">
            <EvalRunsTab
              :agno-runs="agnoRuns"
              :selected-run-id="selectedRun?.id || selectedRunId"
              :loading="loading"
              :eval-type-label="evalTypeLabel"
              :score-label="scoreLabel"
              :format-time="formatTime"
              @select-run="selectedRunId = $event"
            />
          </el-tab-pane>

          <el-tab-pane :label="t('agentEvals.tabs.failures')" name="failures">
            <EvalFailuresTab
              :failures="failures"
              :selected-failure-id="selectedFailure?.id || selectedFailureId"
              :selected-failure-replay-id="selectedFailureReplayId"
              :loading="loading"
              :can-run="canRun"
              :eval-type-label="evalTypeLabel"
              :format-time="formatTime"
              @select-failure="selectedFailureId = $event"
              @replay="replaySelectedFailure"
            />
          </el-tab-pane>

          <el-tab-pane :label="t('agentEvals.tabs.trends')" name="trends">
            <EvalTrendsPanel :trends="trends" :eval-type-label="evalTypeLabel" />
          </el-tab-pane>
        </el-tabs>
      </section>

      <AgentEvalDetailPanel
        :detail-item="detailItem"
        :selected-case="selectedCase"
        :detail-title="detailTitle"
        :detail-status="detailStatus"
        :detail-tone="detailTone"
        :detail-eval-type="detailEvalType"
        :detail-agent="detailAgent"
        :detail-time="detailTime"
        :tool-call-statuses="toolCallStatuses"
        :tool-call-tone="toolCallTone"
      />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n"
import { useAgentEvalsWorkbench } from "../composables/useAgentEvalsWorkbench"
import AgentEvalDetailPanel from "./evals/AgentEvalDetailPanel.vue"
import AgentEvalsCommandBar from "./evals/AgentEvalsCommandBar.vue"
import EvalCasesTab from "./evals/EvalCasesTab.vue"
import EvalFailuresTab from "./evals/EvalFailuresTab.vue"
import EvalRunsTab from "./evals/EvalRunsTab.vue"
import EvalTrendsPanel from "./evals/EvalTrendsPanel.vue"

const { t } = useI18n()
const {
  activeTab,
  suites,
  agnoRuns,
  failures,
  trends,
  selectedCaseId,
  selectedRunId,
  selectedFailureId,
  filters,
  loading,
  error,
  canWrite,
  canRun,
  selectedSuiteId,
  caseRows,
  filteredCases,
  selectedCase,
  selectedRun,
  selectedFailure,
  selectedFailureReplayId,
  summaryCards,
  verdictSegments,
  detailItem,
  detailTitle,
  detailStatus,
  detailTone,
  detailEvalType,
  detailAgent,
  detailTime,
  toolCallStatuses,
  refreshWorkbench,
  runSelectedSuite,
  runSelectedCase,
  replaySelectedFailure,
  showPermissionNotice,
  evalTypeLabel,
  statusTone,
  scoreLabel,
  toolCallTone,
  formatTime,
} = useAgentEvalsWorkbench()
</script>
