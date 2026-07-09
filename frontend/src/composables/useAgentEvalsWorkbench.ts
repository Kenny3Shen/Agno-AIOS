import { computed, onMounted, reactive, ref } from "vue"
import { ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"
import { useAgentEvalsApi } from "./useAgentEvalsApi"
import { useAuthStore } from "../stores/auth"
import {
  buildEvalSummaryCards,
  evalTypeLabel,
  filterEvalCases,
  formatEvalTime,
  replayCaseRunId,
  scoreLabel,
  statusTone,
  toolCallTone,
} from "../modules/agentEvalsWorkbench"
import type {
  AgentEvalAgnoRun,
  AgentEvalCase,
  AgentEvalSuite,
  AgentEvalTrendResponse,
} from "../types"

export type EvalTab = "cases" | "runs" | "failures" | "trends"

export type EvalCaseRow = Omit<AgentEvalCase, "latest_status"> & {
  latest_status?: string
  suite_name: string
  tags: string[]
}

export type EvalFilters = {
  suiteId: string
  evalType: string
  status: string
  keyword: string
}

const emptyTrends = (): AgentEvalTrendResponse => ({
  by_date: [],
  by_eval_type: [],
  by_status: { passed: 0, failed: 0, unknown: 0 },
})

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

export function useAgentEvalsWorkbench() {
  const { t, locale } = useI18n()
  const authStore = useAuthStore()
  const api = useAgentEvalsApi()

  const activeTab = ref<EvalTab>("cases")
  const suites = ref<AgentEvalSuite[]>([])
  const cases = ref<AgentEvalCase[]>([])
  const agnoRuns = ref<AgentEvalAgnoRun[]>([])
  const failures = ref<AgentEvalAgnoRun[]>([])
  const trends = ref<AgentEvalTrendResponse>(emptyTrends())
  const selectedCaseId = ref<string | null>(null)
  const selectedRunId = ref<string | null>(null)
  const selectedFailureId = ref<string | null>(null)
  const filters = reactive<EvalFilters>({
    suiteId: "all",
    evalType: "all",
    status: "all",
    keyword: "",
  })
  const loading = ref(false)
  const error = ref<string | null>(null)

  const canWrite = computed(() => authStore.hasScope("evals:write"))
  const canRun = computed(() => authStore.hasScope("evals:write"))
  const selectedSuiteId = computed(() => filters.suiteId !== "all" ? filters.suiteId : "")
  const suiteNameById = computed(() => new Map(suites.value.map((suite) => [suite.id, suite.name])))

  const caseRows = computed<EvalCaseRow[]>(() => cases.value.map((item) => {
    const metadataTags = Array.isArray(item.metadata?.tags)
      ? item.metadata.tags.filter((tag): tag is string => typeof tag === "string")
      : []
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

  const verdictSegments = computed(() => {
    const passed = Number(trends.value.by_status.passed || 0)
    const failed = Number(trends.value.by_status.failed || 0)
    const unknown = Number(trends.value.by_status.unknown || 0)
    const hasData = passed + failed + unknown > 0
    const total = Math.max(passed + failed + unknown, 1)
    return [
      { key: "passed", tone: "green" as const, count: passed, label: t("agentEvals.verdict.passed") },
      { key: "failed", tone: "red" as const, count: failed, label: t("agentEvals.verdict.failed") },
      { key: "unknown", tone: "blue" as const, count: unknown, label: t("agentEvals.verdict.unknown") },
    ].map((item) => ({
      ...item,
      width: `${hasData ? Math.max((item.count / total) * 100, item.count ? 8 : 0) : item.key === "unknown" ? 100 : 0}%`,
      title: `${item.label}: ${item.count}`,
    }))
  })

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
  const toolCallStatuses = computed(() => {
    if (activeTab.value !== "cases") return ["expected"]
    const expected = selectedCase.value?.expected_tool_calls || []
    return expected.length ? expected.map(() => "expected") : ["unknown"]
  })

  const errorMessage = (err: unknown) => {
    if (err instanceof Error && err.message) return err.message
    return t("api.errors.agentEvalsRequestFailed")
  }

  const loadWorkbench = async (options: { notify?: boolean } = {}) => {
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
      if (options.notify && ![suiteItems, caseItems, agnoRunResult, failureItems, trendResult].some((item) => item.usedFallback)) {
        ElMessage.success(t("agentEvals.messages.loaded"))
      }
    } catch (err) {
      error.value = errorMessage(err)
    } finally {
      loading.value = false
    }
  }

  const refreshWorkbench = () => loadWorkbench({ notify: true })

  const showPermissionNotice = () => {
    ElMessage.info(t("agentEvals.messages.actionUnavailable"))
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

  const formatTime = (value?: string | number | null) => formatEvalTime(value, locale.value)

  onMounted(() => {
    void loadWorkbench()
  })

  return {
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
    loadWorkbench,
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
  }
}
