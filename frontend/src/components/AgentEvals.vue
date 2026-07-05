<template>
  <div class="agent-evals ag-page-flow">
    <section class="agent-evals-kpis ag-stat-strip">
      <article
        v-for="card in summaryCards"
        :key="card.label"
        class="agent-evals-kpi ag-stat-chip"
        :class="`tone-${card.tone}`"
        :title="card.hint"
      >
        <span>{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
      </article>
      <article class="agent-evals-kpi ag-stat-chip tone-blue performance-eval-chip" :title="t('agentEvals.performance.hiddenRun')">
        <span>{{ t("agentEvals.performance.label") }}</span>
        <strong>{{ t("agentEvals.performance.hiddenRun") }}</strong>
      </article>
    </section>

    <el-alert v-if="error" class="agent-evals-alert" type="error" :title="error" show-icon />

    <section class="agent-evals-filters ag-content-panel">
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
    </section>

    <main class="agent-evals-workbench">
      <section class="agent-evals-main ag-workspace-panel">
        <el-tabs v-model="activeTab" class="agent-evals-tabs">
          <el-tab-pane :label="t('agentEvals.tabs.cases')" name="cases">
            <div class="agent-evals-panel-head">
              <div>
                <p>{{ t("agentEvals.panels.cases") }}</p>
                <span>{{ filteredCases.length }} / {{ caseRows.length }}</span>
              </div>
              <el-button size="small" type="primary" :disabled="!canRun || !selectedSuiteId" @click="runSelectedSuite">
                <el-icon><VideoPlay /></el-icon>
                {{ t("agentEvals.actions.runSuite") }}
              </el-button>
            </div>

            <div v-if="filteredCases.length" class="agent-evals-case-list">
              <article
                v-for="item in filteredCases"
                :key="item.id"
                class="agent-evals-case-row"
                :class="{ selected: selectedCase?.id === item.id }"
                @click="selectedCaseId = item.id"
              >
                <div class="agent-evals-case-main">
                  <strong :title="item.name">{{ item.name }}</strong>
                  <span :title="item.description">{{ item.description || item.input }}</span>
                </div>
                <div class="agent-evals-case-meta">
                  <span class="agent-evals-chip">{{ item.suite_name }}</span>
                  <span v-for="type in item.eval_types" :key="`${item.id}-${type}`" class="agent-evals-chip">
                    {{ evalTypeLabel(type) }}
                  </span>
                  <span class="agent-evals-chip" :class="`tone-${statusTone(item.latest_status)}`">
                    {{ item.latest_status || "unknown" }}
                  </span>
                  <span class="agent-evals-chip" :title="item.target_agent_id">
                    {{ item.target_agent_id || "-" }}
                  </span>
                </div>
                <div class="agent-evals-row-actions">
                  <el-tooltip :content="t('agentEvals.actions.runCase')" placement="top">
                    <el-button circle size="small" :disabled="!canRun" :aria-label="t('agentEvals.actions.runCase')" @click.stop="runSelectedCase(item.id)">
                      <el-icon><VideoPlay /></el-icon>
                    </el-button>
                  </el-tooltip>
                  <el-tooltip v-if="canWrite" :content="t('agentEvals.actions.edit')" placement="top">
                    <el-button circle size="small" :aria-label="t('agentEvals.actions.edit')" @click.stop="showPermissionNotice">
                      <el-icon><Edit /></el-icon>
                    </el-button>
                  </el-tooltip>
                </div>
              </article>
            </div>
            <div v-else-if="!loading" class="agent-evals-empty">{{ t("agentEvals.empty.cases") }}</div>
          </el-tab-pane>

          <el-tab-pane :label="t('agentEvals.tabs.runs')" name="runs">
            <div class="agent-evals-panel-head">
              <div>
                <p>{{ t("agentEvals.panels.runs") }}</p>
                <span>{{ agnoRuns.length }}</span>
              </div>
            </div>
            <div v-if="agnoRuns.length" class="agent-evals-run-list">
              <button
                v-for="run in agnoRuns"
                :key="run.id"
                type="button"
                class="agent-evals-run-row"
                :class="{ selected: selectedRun?.id === run.id }"
                @click="selectedRunId = run.id"
              >
                <span class="agent-evals-run-status" :class="`tone-${run.passed === false ? 'red' : run.passed === true ? 'green' : 'blue'}`" />
                <strong :title="run.name">{{ run.name || run.run_id }}</strong>
                <em>{{ evalTypeLabel(run.eval_type) }}</em>
                <span>{{ scoreLabel(run.score) }}</span>
                <small>{{ formatTime(run.created_at) }}</small>
              </button>
            </div>
            <div v-else-if="!loading" class="agent-evals-empty">{{ t("agentEvals.empty.runs") }}</div>
          </el-tab-pane>

          <el-tab-pane :label="t('agentEvals.tabs.failures')" name="failures">
            <div class="agent-evals-panel-head">
              <div>
                <p>{{ t("agentEvals.panels.failures") }}</p>
                <span>{{ failures.length }}</span>
              </div>
              <el-button size="small" type="primary" :disabled="!canRun || !selectedFailureReplayId" @click="replaySelectedFailure">
                <el-icon><RefreshRight /></el-icon>
                {{ t("agentEvals.actions.replay") }}
              </el-button>
            </div>
            <div v-if="failures.length" class="agent-evals-failure-list">
              <button
                v-for="failure in failures"
                :key="failure.id"
                type="button"
                class="agent-evals-failure-row"
                :class="{ selected: selectedFailure?.id === failure.id }"
                @click="selectedFailureId = failure.id"
              >
                <span class="agent-evals-chip tone-red">{{ evalTypeLabel(failure.eval_type) }}</span>
                <strong :title="failure.name">{{ failure.name || failure.run_id }}</strong>
                <small>{{ failure.agent_id || "-" }}</small>
                <em>{{ formatTime(failure.created_at) }}</em>
              </button>
            </div>
            <div v-else-if="!loading" class="agent-evals-empty">{{ t("agentEvals.empty.failures") }}</div>
          </el-tab-pane>

          <el-tab-pane :label="t('agentEvals.tabs.trends')" name="trends">
            <div class="agent-evals-trends">
              <section>
                <p>{{ t("agentEvals.panels.trends") }}</p>
                <div v-for="item in trends.by_eval_type" :key="item.eval_type" class="agent-evals-trend-row">
                  <span>{{ evalTypeLabel(item.eval_type) }}</span>
                  <strong>{{ item.passed }} / {{ item.total }}</strong>
                </div>
              </section>
              <section>
                <p>{{ t("agentEvals.fields.status") }}</p>
                <div class="agent-evals-status-grid">
                  <span class="tone-green">passed {{ trends.by_status.passed }}</span>
                  <span class="tone-red">failed {{ trends.by_status.failed }}</span>
                  <span class="tone-blue">unknown {{ trends.by_status.unknown }}</span>
                </div>
              </section>
            </div>
          </el-tab-pane>
        </el-tabs>
      </section>

      <aside class="agent-evals-detail ag-right-panel">
        <template v-if="detailItem">
          <div class="agent-evals-detail-head">
            <div>
              <p>{{ t("agentEvals.panels.detail") }}</p>
              <strong :title="detailTitle">{{ detailTitle }}</strong>
            </div>
            <span class="agent-evals-chip" :class="`tone-${detailTone}`">{{ detailStatus }}</span>
          </div>
          <dl class="agent-evals-detail-grid">
            <div>
              <dt>{{ t("agentEvals.fields.suite") }}</dt>
              <dd>{{ selectedCase?.suite_name || "-" }}</dd>
            </div>
            <div>
              <dt>{{ t("agentEvals.fields.evalTypes") }}</dt>
              <dd>{{ detailEvalType }}</dd>
            </div>
            <div>
              <dt>{{ t("agentEvals.fields.targetAgent") }}</dt>
              <dd :title="detailAgent">{{ detailAgent }}</dd>
            </div>
            <div>
              <dt>{{ t("agentEvals.fields.createdAt") }}</dt>
              <dd>{{ detailTime }}</dd>
            </div>
          </dl>
          <section class="agent-evals-evidence">
            <p>{{ t("agentEvals.fields.toolCalls") }}</p>
            <div class="agent-evals-tool-row">
              <span
                v-for="status in toolCallStatuses"
                :key="status"
                class="agent-evals-chip"
                :class="`tone-${toolCallTone(status)}`"
              >
                {{ status }}
              </span>
            </div>
          </section>
          <section class="agent-evals-evidence">
            <p>Payload</p>
            <pre>{{ detailPayload }}</pre>
          </section>
        </template>
        <div v-else class="agent-evals-empty detail">{{ t("agentEvals.panels.detail") }}</div>
      </aside>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue"
import { useI18n } from "vue-i18n"
import { ElMessage } from "element-plus"
import {
  Edit,
  RefreshRight,
  Search,
  VideoPlay,
} from "@element-plus/icons-vue"
import { useAgentEvalsApi } from "../composables/useApi"
import { buildEvalSummaryCards, filterEvalCases, toolCallTone } from "../modules/agentEvalsWorkbench"
import { useAuthStore } from "../stores/auth"
import type {
  AgentEvalAgnoRun,
  AgentEvalCase,
  AgentEvalSuite,
  AgentEvalTrendResponse,
  AgentEvalType,
} from "../types"

type EvalTab = "cases" | "runs" | "failures" | "trends"
type EvalCaseRow = Omit<AgentEvalCase, "latest_status"> & {
  latest_status?: string
  suite_name: string
  tags: string[]
}

const { t, locale } = useI18n()
const authStore = useAuthStore()
const api = useAgentEvalsApi()

const activeTab = ref<EvalTab>("cases")
const suites = ref<AgentEvalSuite[]>([])
const cases = ref<AgentEvalCase[]>([])
const agnoRuns = ref<AgentEvalAgnoRun[]>([])
const failures = ref<AgentEvalAgnoRun[]>([])
const trends = ref<AgentEvalTrendResponse>({
  by_date: [],
  by_eval_type: [],
  by_status: { passed: 0, failed: 0, unknown: 0 },
})
const selectedCaseId = ref<string | null>(null)
const selectedRunId = ref<string | null>(null)
const selectedFailureId = ref<string | null>(null)
const filters = reactive({
  suiteId: "all",
  evalType: "all",
  status: "all",
  keyword: "",
})
const loading = ref(false)
const error = ref<string | null>(null)

const canWrite = computed(() => authStore.hasPermission("agent_eval:write"))
const canRun = computed(() => authStore.hasPermission("agent_eval:run"))
const selectedSuiteId = computed(() => filters.suiteId !== "all" ? filters.suiteId : "")
const suiteNameById = computed(() => new Map(suites.value.map((suite) => [suite.id, suite.name])))

const caseRows = computed<EvalCaseRow[]>(() => cases.value.map((item) => {
  const metadataTags = Array.isArray(item.metadata?.tags) ? item.metadata.tags.filter((tag): tag is string => typeof tag === "string") : []
  return {
    ...item,
    latest_status: item.latest_status ?? undefined,
    suite_name: suiteNameById.value.get(item.suite_id) || item.suite_id,
    tags: metadataTags,
  }
}))

const filteredCases = computed(() => {
  const suiteFiltered = filters.suiteId === "all"
    ? caseRows.value
    : caseRows.value.filter((item) => item.suite_id === filters.suiteId)
  return filterEvalCases(suiteFiltered, {
    keyword: filters.keyword,
    evalType: filters.evalType,
    status: filters.status,
    tag: "all",
  })
})

const selectedCase = computed(() => (
  caseRows.value.find((item) => item.id === selectedCaseId.value) ?? filteredCases.value[0] ?? null
))
const selectedRun = computed(() => agnoRuns.value.find((item) => item.id === selectedRunId.value) ?? agnoRuns.value[0] ?? null)
const selectedFailure = computed(() => failures.value.find((item) => item.id === selectedFailureId.value) ?? failures.value[0] ?? null)
const selectedFailureReplayId = computed(() => replayCaseRunId(selectedFailure.value))

const summaryCards = computed(() => buildEvalSummaryCards({
  suiteCount: suites.value.length,
  caseCount: cases.value.length,
  passed: trends.value.by_status.passed,
  failed: trends.value.by_status.failed,
  latestRun: agnoRuns.value[0]?.created_at ? String(agnoRuns.value[0].created_at) : "-",
  performanceSamples: agnoRuns.value.filter((run) => run.eval_type === "performance").length,
}))

const detailItem = computed(() => {
  if (activeTab.value === "failures") return selectedFailure.value
  if (activeTab.value === "runs") return selectedRun.value
  return selectedCase.value
})
const detailTitle = computed(() => {
  const item = detailItem.value
  if (!item) return "-"
  return item.name || item.id
})
const detailStatus = computed(() => {
  if (activeTab.value === "cases") return selectedCase.value?.latest_status || "unknown"
  const run = detailItem.value as AgentEvalAgnoRun | null
  if (!run || run.passed === null || run.passed === undefined) return "unknown"
  return run.passed ? "passed" : "failed"
})
const detailTone = computed(() => statusTone(detailStatus.value))
const detailEvalType = computed(() => {
  if (activeTab.value === "cases") return selectedCase.value?.eval_types.map(evalTypeLabel).join(", ") || "-"
  const run = detailItem.value as AgentEvalAgnoRun | null
  return run ? evalTypeLabel(run.eval_type) : "-"
})
const detailAgent = computed(() => {
  if (activeTab.value === "cases") return selectedCase.value?.target_agent_id || "-"
  const run = detailItem.value as AgentEvalAgnoRun | null
  return run?.agent_id || "-"
})
const detailTime = computed(() => {
  if (activeTab.value === "cases") return formatTime(selectedCase.value?.updated_at)
  const run = detailItem.value as AgentEvalAgnoRun | null
  return formatTime(run?.created_at)
})
const detailPayload = computed(() => JSON.stringify(detailItem.value || {}, null, 2))
const toolCallStatuses = computed(() => {
  if (activeTab.value !== "cases") return ["expected"]
  const expected = selectedCase.value?.expected_tool_calls || []
  return expected.length ? expected.map(() => "expected") : ["unknown"]
})

const emptyTrends = (): AgentEvalTrendResponse => ({
  by_date: [],
  by_eval_type: [],
  by_status: { passed: 0, failed: 0, unknown: 0 },
})

const errorMessage = (err: unknown) => {
  if (err instanceof Error && err.message) return err.message
  return t("api.errors.agentEvalsRequestFailed")
}

const isNotFoundError = (err: unknown) => (
  err instanceof Error && err.message.trim().toLowerCase() === "not found"
)

const requestOrFallback = async <T>(request: () => Promise<T>, fallback: T) => {
  try {
    return { data: await request(), usedFallback: false }
  } catch (err) {
    if (isNotFoundError(err)) return { data: fallback, usedFallback: true }
    throw err
  }
}

const loadWorkbench = async () => {
  loading.value = true
  error.value = null
  try {
    const [suiteItems, caseItems, agnoRunResult, failureItems, trendResult] = await Promise.all([
      requestOrFallback(() => api.listSuites(), []),
      requestOrFallback(() => api.listCases(), []),
      requestOrFallback(() => api.listAgnoRuns({ limit: 50 }), {
        items: [],
        total: 0,
        limit: 50,
        page: 1,
        trends: emptyTrends(),
      }),
      requestOrFallback(() => api.listFailures({ limit: 50 }), []),
      requestOrFallback(() => api.getTrends({ limit: 30 }), emptyTrends()),
    ])
    suites.value = suiteItems.data
    cases.value = caseItems.data
    agnoRuns.value = agnoRunResult.data.items
    failures.value = failureItems.data
    trends.value = trendResult.data
    selectedCaseId.value = filteredCases.value[0]?.id ?? null
    selectedRunId.value = agnoRuns.value[0]?.id ?? null
    selectedFailureId.value = failures.value[0]?.id ?? null
    if (![suiteItems, caseItems, agnoRunResult, failureItems, trendResult].some((item) => item.usedFallback)) {
      ElMessage.success(t("agentEvals.messages.loaded"))
    }
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    loading.value = false
  }
}

const runSelectedSuite = async () => {
  if (!canRun.value || !selectedSuiteId.value) return showPermissionNotice()
  await api.runSuite(selectedSuiteId.value)
  ElMessage.success(t("agentEvals.messages.runQueued"))
  await loadWorkbench()
}

const runSelectedCase = async (caseId: string) => {
  if (!canRun.value) return showPermissionNotice()
  await api.runCase(caseId)
  ElMessage.success(t("agentEvals.messages.runQueued"))
  await loadWorkbench()
}

const replaySelectedFailure = async () => {
  if (!canRun.value || !selectedFailureReplayId.value) return showPermissionNotice()
  await api.replayCaseRun(selectedFailureReplayId.value)
  ElMessage.success(t("agentEvals.messages.replayQueued"))
  await loadWorkbench()
}

const showPermissionNotice = () => {
  ElMessage.info(t("agentEvals.messages.actionUnavailable"))
}

const evalTypeLabel = (type: AgentEvalType | string) => {
  if (type === "accuracy") return "AccuracyEval"
  if (type === "agent_as_judge") return "AgentJudgeEval"
  if (type === "reliability") return "ReliabilityEval"
  if (type === "performance") return "PerformanceEval"
  return type || "-"
}

const statusTone = (status?: string | null) => {
  if (status === "failed" || status === "error") return "red"
  if (status === "passed" || status === "completed") return "green"
  if (status === "running" || status === "queued") return "yellow"
  return "blue"
}

const scoreLabel = (score?: number | null) => {
  if (score === null || score === undefined) return "-"
  return Number.isInteger(score) ? String(score) : score.toFixed(2)
}

const replayCaseRunId = (run: AgentEvalAgnoRun | null) => {
  if (!run) return ""
  const candidates = [
    run.case_run_id,
    run.data?.case_run_id,
    run.data?.caseRunId,
    run.eval_input?.case_run_id,
    run.eval_input?.caseRunId,
  ]
  for (const candidate of candidates) {
    if (typeof candidate === "string" && candidate.trim()) return candidate.trim()
  }
  return ""
}

const formatTime = (value?: string | number | null) => {
  if (!value) return "-"
  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString(locale.value, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

onMounted(() => {
  void loadWorkbench()
})
</script>

<style scoped>
.agent-evals {
  gap: 12px;
  padding: 14px;
}

.agent-evals-filters {
  align-items: center;
  gap: 10px;
}

.agent-evals-panel-head p,
.agent-evals-detail-head p,
.agent-evals-trends p,
.agent-evals-evidence p {
  margin: 0;
  color: var(--ag-text, #e6edf3);
  font-size: 13px;
  font-weight: 700;
}

.agent-evals-panel-head span {
  display: block;
  margin-top: 3px;
  overflow: hidden;
  color: var(--ag-muted, #8ea0ad);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-evals-row-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
}

.agent-evals .agent-evals-kpis {
  align-items: stretch;
  display: grid;
  flex: 0 0 auto;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  grid-auto-rows: minmax(34px, auto);
  height: auto;
  block-size: auto;
  min-height: var(--ag-stat-strip-height);
  overflow: visible;
}

.agent-evals-kpi {
  min-height: 34px;
}

.agent-evals-filters {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) 150px 130px minmax(180px, 1.4fr);
}

.agent-evals-workbench {
  display: grid;
  flex: 0 0 auto;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 340px);
  gap: 12px;
  min-height: 0;
}

.agent-evals-main,
.agent-evals-detail {
  min-width: 0;
  min-height: 520px;
}

.agent-evals-tabs :deep(.el-tabs__header) {
  margin: 0;
  border-bottom: 1px solid rgba(130, 151, 165, 0.2);
  border-radius: 8px 8px 0 0;
  background: rgba(12, 19, 26, 0.72);
  padding: 6px 10px;
}

.agent-evals-tabs :deep(.el-tabs__nav-wrap::after),
.agent-evals-tabs :deep(.el-tabs__active-bar) {
  display: none;
}

.agent-evals-tabs :deep(.el-tabs__nav) {
  display: flex;
  gap: 6px;
}

.agent-evals-tabs :deep(.el-tabs__item) {
  height: 30px;
  border: 1px solid transparent;
  border-radius: 6px;
  padding: 0 11px;
  color: var(--ag-muted, #8ea0ad);
  font-size: 12px;
  font-weight: 700;
  line-height: 30px;
}

.agent-evals-tabs :deep(.el-tabs__item.is-top:nth-child(2)),
.agent-evals-tabs :deep(.el-tabs__item.is-top:last-child) {
  padding: 0 11px;
}

.agent-evals-tabs :deep(.el-tabs__item:hover) {
  border-color: rgba(96, 165, 250, 0.22);
  background: rgba(96, 165, 250, 0.08);
  color: var(--ag-text, #e6edf3);
}

.agent-evals-tabs :deep(.el-tabs__item.is-active) {
  border-color: rgba(64, 158, 255, 0.42);
  background: rgba(64, 158, 255, 0.16);
  color: #93c5fd;
}

.agent-evals-tabs :deep(.el-tabs__content) {
  padding: 12px;
}

.agent-evals-panel-head,
.agent-evals-detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.agent-evals-case-list,
.agent-evals-run-list,
.agent-evals-failure-list {
  display: grid;
  gap: 8px;
}

.agent-evals-case-row,
.agent-evals-run-row,
.agent-evals-failure-row {
  display: grid;
  width: 100%;
  min-width: 0;
  border: 1px solid rgba(130, 151, 165, 0.18);
  border-radius: 8px;
  background: rgba(9, 17, 23, 0.52);
  color: var(--ag-text, #e6edf3);
  text-align: left;
}

.agent-evals-case-row {
  grid-template-columns: minmax(180px, 1fr) minmax(260px, 1.5fr) auto;
  align-items: center;
  gap: 10px;
  padding: 10px;
}

.agent-evals-run-row,
.agent-evals-failure-row {
  grid-template-columns: 10px minmax(140px, 1fr) 120px 80px 120px;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
}

.agent-evals-failure-row {
  grid-template-columns: 120px minmax(140px, 1fr) 120px 120px;
}

.agent-evals-case-row.selected,
.agent-evals-run-row.selected,
.agent-evals-failure-row.selected {
  border-color: rgba(64, 158, 255, 0.56);
  background: rgba(21, 42, 58, 0.72);
}

.agent-evals-case-main {
  min-width: 0;
}

.agent-evals-case-main strong,
.agent-evals-run-row strong,
.agent-evals-failure-row strong {
  display: block;
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-evals-case-main span,
.agent-evals-run-row em,
.agent-evals-run-row small,
.agent-evals-failure-row em,
.agent-evals-failure-row small {
  overflow: hidden;
  color: var(--ag-muted, #8ea0ad);
  font-size: 12px;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-evals-case-meta,
.agent-evals-tool-row,
.agent-evals-status-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}

.agent-evals-chip {
  max-width: 160px;
  overflow: hidden;
  border: 1px solid rgba(130, 151, 165, 0.18);
  border-radius: 6px;
  padding: 3px 7px;
  background: rgba(130, 151, 165, 0.1);
  color: var(--ag-text, #e6edf3);
  font-size: 11px;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-evals-chip.tone-red,
.agent-evals-status-grid .tone-red {
  border-color: rgba(248, 113, 113, 0.38);
  color: #fca5a5;
}

.agent-evals-chip.tone-green,
.agent-evals-status-grid .tone-green {
  border-color: rgba(74, 222, 128, 0.34);
  color: #86efac;
}

.agent-evals-chip.tone-yellow,
.agent-evals-status-grid .tone-yellow {
  border-color: rgba(250, 204, 21, 0.34);
  color: #fde68a;
}

.agent-evals-chip.tone-blue,
.agent-evals-status-grid .tone-blue {
  border-color: rgba(96, 165, 250, 0.32);
  color: #93c5fd;
}

.agent-evals-run-status {
  width: 8px;
  height: 32px;
  border-radius: 4px;
  background: #60a5fa;
}

.agent-evals-run-status.tone-red {
  background: #f87171;
}

.agent-evals-run-status.tone-green {
  background: #4ade80;
}

.agent-evals-trends {
  display: grid;
  flex: 0 0 auto;
  grid-template-columns: minmax(0, 1fr) minmax(220px, 0.6fr);
  gap: 12px;
}

.agent-evals-trends section,
.agent-evals-evidence {
  border: 1px solid rgba(130, 151, 165, 0.16);
  border-radius: 8px;
  padding: 10px;
  background: rgba(9, 17, 23, 0.42);
}

.agent-evals-trend-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(130, 151, 165, 0.12);
  color: var(--ag-muted, #8ea0ad);
  font-size: 12px;
}

.agent-evals-detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin: 0 0 10px;
}

.agent-evals-detail-grid div {
  min-width: 0;
  border: 1px solid rgba(130, 151, 165, 0.14);
  border-radius: 8px;
  padding: 8px;
  background: rgba(9, 17, 23, 0.36);
}

.agent-evals-detail-grid dt {
  color: var(--ag-muted, #8ea0ad);
  font-size: 11px;
}

.agent-evals-detail-grid dd {
  margin: 3px 0 0;
  overflow: hidden;
  color: var(--ag-text, #e6edf3);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-evals-evidence {
  margin-top: 10px;
}

.agent-evals-evidence pre {
  max-height: 260px;
  margin: 8px 0 0;
  overflow: auto;
  color: #b7c8d6;
  font-size: 11px;
  white-space: pre-wrap;
}

.agent-evals-empty {
  display: grid;
  min-height: 160px;
  place-items: center;
  color: var(--ag-muted, #8ea0ad);
  font-size: 12px;
}

.agent-evals-empty.detail {
  min-height: 420px;
}

@media (max-width: 1180px) {
  .agent-evals-workbench,
  .agent-evals-trends {
    grid-template-columns: 1fr;
  }

  .agent-evals .agent-evals-kpis {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .agent-evals-filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .agent-evals-filters,
  .agent-evals-case-row,
  .agent-evals-run-row,
  .agent-evals-failure-row,
  .agent-evals-detail-grid {
    grid-template-columns: 1fr;
  }

  .agent-evals .agent-evals-kpis {
    grid-template-columns: 1fr;
  }

  .performance-eval-chip {
    min-height: 34px;
    align-items: center;
    flex-direction: row;
    justify-content: space-between;
    gap: 8px;
  }

  .agent-evals-main,
  .agent-evals-detail {
    min-height: auto;
  }

  .agent-evals-empty {
    min-height: 120px;
  }

  .agent-evals-empty.detail {
    min-height: 180px;
  }

  .agent-evals-panel-head,
  .agent-evals-detail-head {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .agent-evals-run-status {
    width: 100%;
    height: 4px;
  }
}
</style>
