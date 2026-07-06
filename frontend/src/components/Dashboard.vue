<template>
  <div class="dashboard-page ag-page-flow">
    <header class="dashboard-header ag-content-panel">
      <div class="dashboard-header-copy">
        <h3>{{ t("dashboard.title") }}</h3>
        <p>{{ t("dashboard.description") }}</p>
      </div>

      <div class="dashboard-header-actions">
        <div class="dashboard-view-tabs" role="tablist" :aria-label="t('dashboard.tabs.ariaLabel')">
          <button
            v-for="tab in dashboardTabs"
            :key="tab.key"
            type="button"
            :class="{ active: activeTab === tab.key }"
            @click="activeTab = tab.key"
          >
            {{ tab.label }}
          </button>
        </div>
        <el-select v-model="timeScope" size="small" class="dashboard-range" @change="loadDashboard">
          <el-option :label="t('dashboard.timeScope.last24h')" value="24h" />
          <el-option :label="t('dashboard.timeScope.last7d')" value="7d" />
          <el-option :label="t('dashboard.timeScope.last30d')" value="30d" />
        </el-select>
        <el-button
          type="primary"
          size="small"
          :loading="loading"
          class="cursor-pointer"
          :aria-label="t('dashboard.actions.refresh')"
          @click="loadDashboard"
        >
          <el-icon><Refresh /></el-icon>
        </el-button>
      </div>
    </header>

    <section v-if="activeTab === 'health'" class="dashboard-section">
      <div class="dashboard-kpi-grid">
        <article v-for="metric in healthMetrics" :key="metric.label" class="dashboard-kpi-card ag-content-panel" :class="`tone-${metric.tone}`">
          <span>{{ metric.label }}</span>
          <strong :title="metric.hint">{{ metric.value }}</strong>
          <em>{{ metric.hint }}</em>
        </article>
      </div>

      <section class="dashboard-chart-grid wide-left">
        <article class="dashboard-panel ag-content-panel">
          <div class="dashboard-panel-title">
            <el-icon><TrendCharts /></el-icon>
            {{ t("dashboard.charts.latencyTrend") }}
          </div>
          <svg class="dashboard-line-chart" viewBox="0 0 320 140" role="img" :aria-label="t('dashboard.aria.latencyTrend')">
            <path class="chart-gridline" d="M0 35 H320 M0 70 H320 M0 105 H320" />
            <path v-if="latencyAreaPoints" class="latency-area" :d="`M ${latencyAreaPoints} Z`" />
            <polyline v-if="latencyTrendPoints" class="latency-line" :points="latencyTrendPoints" />
            <circle v-for="point in latencyDots" :key="`${point.x}-${point.y}`" class="latency-dot" :cx="point.x" :cy="point.y" r="2.6" />
          </svg>
          <div class="dashboard-chart-legend">
            <span>{{ t("dashboard.legend.recentRuns", { count: trendRuns.length }) }}</span>
            <strong>{{ t("dashboard.legend.peak", { value: formatDuration(maxTrendDuration) }) }}</strong>
          </div>
        </article>

        <article class="dashboard-panel ag-content-panel">
          <div class="dashboard-panel-title">
            <el-icon><Histogram /></el-icon>
            {{ t("dashboard.charts.statusDistribution") }}
          </div>
          <div class="dashboard-bars">
            <div v-for="item in statusBars" :key="item.label" class="dashboard-bar-row">
              <div>
                <span>{{ item.label }}</span>
                <strong>{{ item.count }}</strong>
              </div>
              <span class="dashboard-bar-track">
                <span class="dashboard-bar-fill" :class="item.className" :style="{ width: item.width }" />
              </span>
            </div>
          </div>
        </article>
      </section>

      <section class="dashboard-chart-grid wide-left">
        <article class="dashboard-panel ag-content-panel">
          <div class="dashboard-panel-title">
            <el-icon><DataBoard /></el-icon>
            {{ t("dashboard.charts.recentRuns") }}
          </div>
          <div class="dashboard-run-list">
            <div v-for="trace in recentRuns" :key="trace.trace_id" class="dashboard-run-row">
              <span class="run-status" :class="statusClass(trace.status, trace.error_count)" />
              <div class="dashboard-run-copy">
                <div>
                  <strong :title="trace.name">{{ trace.name || trace.trace_id }}</strong>
                  <span>{{ formatDuration(trace.duration_ms) }}</span>
                </div>
                <small>{{ shortId(trace.trace_id) }} · {{ t("dashboard.labels.session", { value: shortId(trace.session_id || "") }) }}</small>
              </div>
            </div>
            <div v-if="!recentRuns.length && !loading" class="dashboard-empty">{{ t("dashboard.empty.agentRuns") }}</div>
          </div>
        </article>

        <article class="dashboard-panel ag-content-panel">
          <div class="dashboard-panel-title">
            <el-icon><Warning /></el-icon>
            {{ t("dashboard.charts.incidents") }}
          </div>
          <div class="dashboard-run-list compact">
            <div v-for="trace in errorRuns" :key="trace.trace_id" class="dashboard-incident-row">
              <span class="run-status error" />
              <div>
                <strong :title="trace.name">{{ trace.name || shortId(trace.trace_id) }}</strong>
                <small>{{ t("dashboard.labels.incidentErrors", { count: trace.error_count ?? 0 }) }}</small>
              </div>
            </div>
            <div v-if="!errorRuns.length && !loading" class="dashboard-empty ok">{{ t("dashboard.empty.incidentsOk") }}</div>
          </div>
        </article>
      </section>
    </section>

    <section v-else-if="activeTab === 'usage'" class="dashboard-section">
      <div class="dashboard-kpi-grid">
        <article v-for="metric in usageMetrics" :key="metric.label" class="dashboard-kpi-card ag-content-panel" :class="`tone-${metric.tone}`">
          <span>{{ metric.label }}</span>
          <strong :title="metric.hint">{{ metric.value }}</strong>
          <em>{{ metric.hint }}</em>
        </article>
      </div>

      <section class="dashboard-chart-grid">
        <article class="dashboard-panel ag-content-panel">
          <div class="dashboard-panel-title">
            <el-icon><PieChart /></el-icon>
            {{ t("dashboard.charts.runMix") }}
          </div>
          <div class="dashboard-bars">
            <div v-for="item in runTypeBars" :key="item.label" class="dashboard-bar-row">
              <div>
                <span>{{ item.label }}</span>
                <strong>{{ item.count }}</strong>
              </div>
              <span class="dashboard-bar-track">
                <span class="dashboard-bar-fill" :class="item.className" :style="{ width: item.width }" />
              </span>
            </div>
          </div>
        </article>

        <article class="dashboard-panel ag-content-panel">
          <div class="dashboard-panel-title">
            <el-icon><Connection /></el-icon>
            {{ t("dashboard.charts.usageScope") }}
          </div>
          <div class="dashboard-scope-grid">
            <div v-for="item in usageScope" :key="item.label">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </article>
      </section>
    </section>

    <section v-else class="dashboard-section">
      <div class="dashboard-kpi-grid">
        <article v-for="metric in modelMetrics" :key="metric.label" class="dashboard-kpi-card ag-content-panel" :class="`tone-${metric.tone}`">
          <span>{{ metric.label }}</span>
          <strong :title="metric.hint">{{ metric.value }}</strong>
          <em>{{ metric.hint }}</em>
        </article>
      </div>

      <section class="dashboard-chart-grid wide-left">
        <article class="dashboard-panel ag-content-panel">
          <div class="dashboard-panel-title">
            <el-icon><Cpu /></el-icon>
            {{ t("dashboard.charts.modelBreakdown") }}
          </div>
          <div class="dashboard-model-list">
            <div v-for="row in modelRows" :key="row.id" class="dashboard-model-row">
              <div>
                <strong>{{ row.model }}</strong>
                <span>{{ row.provider }}</span>
              </div>
              <em>{{ t("dashboard.labels.modelUsage", { runs: row.runs, tokens: formatNumber(row.tokens) }) }}</em>
            </div>
            <div v-if="!modelRows.length && !loading" class="dashboard-empty">{{ t("dashboard.empty.models") }}</div>
          </div>
        </article>

        <article class="dashboard-panel ag-content-panel">
          <div class="dashboard-panel-title">
            <el-icon><DataAnalysis /></el-icon>
            {{ t("dashboard.charts.providerDistribution") }}
          </div>
          <div class="dashboard-bars">
            <div v-for="item in providerBars" :key="item.label" class="dashboard-bar-row">
              <div>
                <span>{{ item.label }}</span>
                <strong>{{ item.count }}</strong>
              </div>
              <span class="dashboard-bar-track">
                <span class="dashboard-bar-fill blue" :style="{ width: item.width }" />
              </span>
            </div>
            <div v-if="!providerBars.length && !loading" class="dashboard-empty">{{ t("dashboard.empty.providers") }}</div>
          </div>
        </article>
      </section>
    </section>

    <el-alert v-if="apiError" type="error" :title="apiError" show-icon />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { useI18n } from "vue-i18n"
import { Connection, Cpu, DataAnalysis, DataBoard, Histogram, PieChart, Refresh, TrendCharts, Warning } from "@element-plus/icons-vue"
import { useTracingApi } from "../composables/useApi"
import type { SpanItem, TraceItem } from "../types"

type TimeScope = "24h" | "7d" | "30d"
type DashboardTab = "health" | "usage" | "models"

interface MetricCard {
  label: string
  value: string | number
  hint: string
  tone: "blue" | "green" | "red" | "yellow"
}

const { t } = useI18n()
const { loading, error, listTraces, getTrace } = useTracingApi()
const traces = ref<TraceItem[]>([])
const spanSamples = ref<SpanItem[]>([])
const totalCount = ref(0)
const timeScope = ref<TimeScope>("30d")
const activeTab = ref<DashboardTab>("health")
const detailError = ref<string | null>(null)

const dashboardTabs = computed(() => [
  { key: "health" as const, label: t("dashboard.tabs.health") },
  { key: "usage" as const, label: t("dashboard.tabs.usage") },
  { key: "models" as const, label: t("dashboard.tabs.models") },
])

const apiError = computed(() => error.value || detailError.value)
const sampleSize = computed(() => traces.value.length)
const errorRunCount = computed(() => traces.value.filter((trace) => hasError(trace)).length)
const okRunCount = computed(() => traces.value.filter((trace) => trace.status === "OK" && !hasError(trace)).length)
const totalSpans = computed(() => traces.value.reduce((sum, trace) => sum + Number(trace.total_spans || 0), 0))
const avgDuration = computed(() => average(traces.value.map((trace) => Number(trace.duration_ms || 0))))
const p95Duration = computed(() => percentile(traces.value.map((trace) => Number(trace.duration_ms || 0)), 95))
const successRate = computed(() => sampleSize.value ? `${Math.round((okRunCount.value / sampleSize.value) * 100)}%` : "0%")
const errorRate = computed(() => sampleSize.value ? `${Math.round((errorRunCount.value / sampleSize.value) * 100)}%` : "0%")

const uniqueSessions = computed(() => countUnique(traces.value.map((trace) => trace.session_id)))
const uniqueUsers = computed(() => countUnique(traces.value.map((trace) => trace.user_id)))
const agentRunCount = computed(() => traces.value.filter((trace) => trace.agent_id).length)
const teamRunCount = computed(() => traces.value.filter((trace) => trace.team_id).length)
const workflowRunCount = computed(() => traces.value.filter((trace) => trace.workflow_id).length)
const activeRuntimeCount = computed(() => countUnique(traces.value.map((trace) => trace.agent_id || trace.team_id || trace.workflow_id)))
const totalTokens = computed(() => spanSamples.value.reduce((sum, span) => sum + spanTokenTotal(span), 0))

const healthMetrics = computed<MetricCard[]>(() => [
  { label: t("dashboard.metrics.runs"), value: totalCount.value, hint: t("dashboard.metrics.sampleHint", { count: sampleSize.value }), tone: "blue" },
  { label: t("dashboard.metrics.errorRate"), value: errorRate.value, hint: t("dashboard.metrics.errorRunsHint"), tone: errorRunCount.value ? "red" : "green" },
  { label: t("dashboard.metrics.p95Latency"), value: formatDuration(p95Duration.value), hint: t("dashboard.metrics.averageLatency", { value: formatDuration(avgDuration.value) }), tone: "yellow" },
  { label: t("dashboard.metrics.activeRuntimes"), value: activeRuntimeCount.value, hint: t("dashboard.metrics.spansObserved", { count: totalSpans.value }), tone: "green" },
])

const usageMetrics = computed<MetricCard[]>(() => [
  { label: t("dashboard.metrics.totalTokens"), value: totalTokens.value ? formatNumber(totalTokens.value) : "-", hint: t("dashboard.metrics.tokensHint"), tone: "blue" },
  { label: t("dashboard.metrics.users"), value: uniqueUsers.value || "-", hint: t("dashboard.metrics.usersHint"), tone: "green" },
  { label: t("dashboard.metrics.agentRuns"), value: agentRunCount.value, hint: t("dashboard.metrics.agentRunsHint"), tone: "blue" },
  { label: t("dashboard.metrics.sessions"), value: uniqueSessions.value || "-", hint: t("dashboard.metrics.sessionsHint"), tone: "yellow" },
])

const modelMetrics = computed<MetricCard[]>(() => [
  { label: t("dashboard.metrics.providers"), value: providerBars.value.length || "-", hint: t("dashboard.metrics.providersHint"), tone: "blue" },
  { label: t("dashboard.metrics.models"), value: modelRows.value.length || "-", hint: t("dashboard.metrics.modelsHint"), tone: "green" },
  { label: t("dashboard.metrics.modelRuns"), value: modelRows.value.reduce((sum, row) => sum + row.runs, 0) || "-", hint: t("dashboard.metrics.modelRunsHint"), tone: "yellow" },
  { label: t("dashboard.metrics.modelTokens"), value: totalTokens.value ? formatNumber(totalTokens.value) : "-", hint: t("dashboard.metrics.tokensHint"), tone: "blue" },
])

const recentRuns = computed(() => traces.value.slice(0, 10))
const errorRuns = computed(() => traces.value.filter((trace) => hasError(trace)).slice(0, 7))
const sortedRuns = computed(() => [...traces.value].sort((a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime()))
const trendRuns = computed(() => sortedRuns.value.slice(-24))
const maxTrendDuration = computed(() => Math.max(...trendRuns.value.map((trace) => Number(trace.duration_ms || 0)), 1))

const latencyDots = computed(() => {
  const runs = trendRuns.value
  if (!runs.length) return []
  const width = 320
  const height = 124
  const bottom = 132
  const step = runs.length === 1 ? 0 : width / (runs.length - 1)
  return runs.map((trace, index) => {
    const ratio = Math.min(Number(trace.duration_ms || 0) / maxTrendDuration.value, 1)
    return {
      x: Number((index * step).toFixed(2)),
      y: Number((bottom - ratio * height).toFixed(2)),
    }
  })
})
const latencyTrendPoints = computed(() => latencyDots.value.map((point) => `${point.x},${point.y}`).join(" "))
const latencyAreaPoints = computed(() => latencyDots.value.length ? `0,132 ${latencyTrendPoints.value} 320,132` : "")

const statusBars = computed(() => {
  const total = Math.max(sampleSize.value, 1)
  return [
    { label: "OK", count: okRunCount.value, className: "ok" },
    { label: "ERROR", count: errorRunCount.value, className: "error" },
    { label: "UNSET / OTHER", count: Math.max(sampleSize.value - okRunCount.value - errorRunCount.value, 0), className: "other" },
  ].map((item) => ({
    ...item,
    width: `${Math.max((item.count / total) * 100, item.count ? 6 : 0)}%`,
  }))
})

const runTypeBars = computed(() => {
  const total = Math.max(sampleSize.value, 1)
  return [
    { label: t("dashboard.labels.agentRuns"), count: agentRunCount.value, className: "blue" },
    { label: t("dashboard.labels.teamRuns"), count: teamRunCount.value, className: "green" },
    { label: t("dashboard.labels.workflowRuns"), count: workflowRunCount.value, className: "yellow" },
  ].map((item) => ({
    ...item,
    width: `${Math.max((item.count / total) * 100, item.count ? 6 : 0)}%`,
  }))
})

const usageScope = computed(() => [
  { label: t("dashboard.metrics.runSamples"), value: formatNumber(sampleSize.value) },
  { label: t("dashboard.metrics.spans"), value: formatNumber(totalSpans.value) },
  { label: t("dashboard.metrics.errorRuns"), value: formatNumber(errorRunCount.value) },
  { label: t("dashboard.metrics.successRate"), value: successRate.value },
])

const modelRows = computed(() => {
  const buckets = new Map<string, { id: string; provider: string; model: string; runs: number; tokens: number }>()
  for (const span of spanSamples.value) {
    const metadata = span.parsed?.metadata
    const model = metadata?.model || ""
    const provider = metadata?.provider || t("dashboard.labels.unknownProvider")
    if (!model) continue
    const id = `${provider}:${model}`
    const item = buckets.get(id) || { id, provider, model, runs: 0, tokens: 0 }
    item.runs += 1
    item.tokens += spanTokenTotal(span)
    buckets.set(id, item)
  }
  return [...buckets.values()].sort((a, b) => b.runs - a.runs || b.tokens - a.tokens).slice(0, 8)
})

const providerBars = computed(() => {
  const buckets = new Map<string, number>()
  for (const row of modelRows.value) {
    buckets.set(row.provider, (buckets.get(row.provider) || 0) + row.runs)
  }
  const maxRuns = Math.max(...buckets.values(), 1)
  return [...buckets.entries()].map(([label, count]) => ({
    label,
    count,
    width: `${Math.max((count / maxRuns) * 100, count ? 6 : 0)}%`,
  }))
})

const rangeStart = () => {
  const now = Date.now()
  const ranges: Record<TimeScope, number> = {
    "24h": 24 * 60 * 60 * 1000,
    "7d": 7 * 24 * 60 * 60 * 1000,
    "30d": 30 * 24 * 60 * 60 * 1000,
  }
  return new Date(now - ranges[timeScope.value]).toISOString()
}

const loadDashboard = async () => {
  detailError.value = null
  const response = await listTraces({
    page: 1,
    limit: 80,
    start_time: rangeStart(),
  })
  traces.value = response.items || []
  totalCount.value = response.total_count || 0
  await loadSpanSamples(traces.value.slice(0, 16))
}

const loadSpanSamples = async (items: TraceItem[]) => {
  try {
    const details = await Promise.allSettled(items.map((trace) => getTrace(trace.trace_id)))
    spanSamples.value = details.flatMap((result) => result.status === "fulfilled" ? result.value.spans || [] : [])
    const rejected = details.some((result) => result.status === "rejected")
    detailError.value = rejected ? t("dashboard.errors.partialDetails") : null
  } catch {
    spanSamples.value = []
    detailError.value = t("dashboard.errors.partialDetails")
  }
}

const hasError = (trace: TraceItem) => {
  return trace.status === "ERROR" || Number(trace.error_count || 0) > 0
}

const statusClass = (status: string, errorCount?: number) => {
  if (status === "ERROR" || Number(errorCount || 0) > 0) return "error"
  if (status === "OK") return "ok"
  return "other"
}

const spanTokenTotal = (span: SpanItem) => {
  const tokens = span.parsed?.metadata?.tokens
  const total = Number(tokens?.total)
  if (Number.isFinite(total) && total > 0) return total
  return Number(tokens?.prompt || 0) + Number(tokens?.completion || 0)
}

const countUnique = (values: Array<string | null | undefined>) => {
  return new Set(values.filter((value): value is string => Boolean(value))).size
}

const average = (values: number[]) => {
  const clean = values.filter((value) => Number.isFinite(value))
  return clean.length ? clean.reduce((sum, value) => sum + value, 0) / clean.length : 0
}

const percentile = (values: number[], pct: number) => {
  const clean = values.filter((value) => Number.isFinite(value)).sort((a, b) => a - b)
  if (!clean.length) return 0
  const index = Math.min(clean.length - 1, Math.ceil((pct / 100) * clean.length) - 1)
  return clean[index]
}

const shortId = (id: string) => {
  if (!id) return "-"
  return id.length > 14 ? `${id.slice(0, 6)}...${id.slice(-6)}` : id
}

const formatNumber = (value: number) => new Intl.NumberFormat().format(value)

const formatDuration = (durationMs: number | string | null | undefined): string => {
  const n = Number(durationMs)
  if (!Number.isFinite(n) || n < 0) return "-"
  if (n < 1000) return `${Math.round(n)} ms`
  const sec = n / 1000
  if (sec < 60) return `${sec < 10 ? sec.toFixed(2) : sec.toFixed(1)} s`
  const min = Math.floor(sec / 60)
  return `${min}m ${Math.round(sec % 60)}s`
}

onMounted(() => {
  loadDashboard()
})
</script>

<style>
.dashboard-page {
  font-family: "Fira Sans", "Microsoft YaHei", sans-serif;
  background: var(--ag-frame);
  color: var(--ag-text);
}

.dashboard-header,
.dashboard-header-actions,
.dashboard-view-tabs,
.dashboard-panel-title,
.dashboard-chart-legend,
.dashboard-bar-row > div,
.dashboard-run-copy > div,
.dashboard-model-row {
  display: flex;
  align-items: center;
}

.dashboard-header {
  justify-content: space-between;
  gap: 12px;
}

.dashboard-header-copy {
  min-width: 0;
}

.dashboard-header-copy h3 {
  margin: 0;
  color: var(--ag-heading);
  font-size: 14px;
  font-weight: 760;
}

.dashboard-header-copy p {
  margin: 5px 0 0;
  color: var(--ag-muted);
  font-size: 12px;
}

.dashboard-header-actions {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.dashboard-view-tabs {
  gap: 2px;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-control);
  background: var(--ag-panel-soft);
  padding: 2px;
}

.dashboard-view-tabs button {
  border: 0;
  border-radius: 5px;
  background: transparent;
  padding: 5px 10px;
  color: var(--ag-muted);
  cursor: pointer;
  font-size: 12px;
  font-weight: 720;
}

.dashboard-view-tabs button.active {
  background: var(--ag-panel);
  color: var(--ag-heading);
  box-shadow: inset 0 0 0 1px var(--ag-border);
}

.dashboard-range {
  width: 132px;
}

.dashboard-section {
  display: grid;
  gap: var(--ag-section-gap);
}

.dashboard-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--ag-section-gap);
}

.dashboard-kpi-card {
  display: grid;
  min-height: 104px;
  gap: 7px;
}

.dashboard-kpi-card span,
.dashboard-kpi-card em {
  min-width: 0;
  overflow: hidden;
  color: var(--ag-muted);
  font-size: 11px;
  font-style: normal;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dashboard-kpi-card span {
  font-weight: 760;
}

.dashboard-kpi-card strong {
  min-width: 0;
  overflow: hidden;
  color: var(--ag-heading);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 24px;
  font-weight: 820;
  line-height: 1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dashboard-kpi-card.tone-blue {
  border-color: color-mix(in srgb, var(--ag-blue) 30%, var(--ag-border));
}

.dashboard-kpi-card.tone-green {
  border-color: color-mix(in srgb, var(--ag-green) 30%, var(--ag-border));
}

.dashboard-kpi-card.tone-yellow {
  border-color: color-mix(in srgb, var(--ag-yellow) 32%, var(--ag-border));
}

.dashboard-kpi-card.tone-red {
  border-color: color-mix(in srgb, var(--ag-red) 32%, var(--ag-border));
}

.dashboard-chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--ag-section-gap);
}

.dashboard-chart-grid.wide-left {
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.65fr);
}

.dashboard-panel {
  min-height: 0;
  overflow: hidden;
}

.dashboard-panel-title {
  gap: 8px;
  color: var(--ag-heading);
  font-size: 13px;
  font-weight: 760;
}

.dashboard-line-chart {
  display: block;
  width: 100%;
  height: 180px;
  margin-top: 12px;
}

.chart-gridline {
  stroke: var(--ag-border);
  stroke-dasharray: 3 6;
  stroke-width: 1;
}

.latency-area {
  fill: color-mix(in srgb, var(--ag-blue) 14%, transparent);
}

.latency-line {
  fill: none;
  stroke: var(--ag-blue);
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 3;
}

.latency-dot {
  fill: var(--ag-panel);
  stroke: var(--ag-blue);
  stroke-width: 2;
}

.dashboard-chart-legend {
  justify-content: space-between;
  gap: 10px;
  color: var(--ag-muted);
  font-size: 11px;
}

.dashboard-chart-legend strong,
.dashboard-bar-row strong,
.dashboard-run-copy span,
.dashboard-model-row em,
.dashboard-scope-grid strong {
  color: var(--ag-heading);
  font-family: "JetBrains Mono", "Fira Code", monospace;
}

.dashboard-bars,
.dashboard-run-list,
.dashboard-model-list {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

.dashboard-run-list.compact {
  gap: 8px;
}

.dashboard-bar-row {
  display: grid;
  gap: 7px;
}

.dashboard-bar-row > div {
  justify-content: space-between;
  gap: 12px;
}

.dashboard-bar-row span,
.dashboard-model-row span,
.dashboard-scope-grid span,
.dashboard-run-copy small,
.dashboard-incident-row small {
  min-width: 0;
  overflow: hidden;
  color: var(--ag-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dashboard-bar-track {
  display: block;
  height: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--ag-panel-soft);
}

.dashboard-bar-fill {
  display: block;
  height: 100%;
  min-width: 4px;
  border-radius: inherit;
  background: var(--ag-blue);
}

.dashboard-bar-fill.ok,
.dashboard-bar-fill.green {
  background: var(--ag-green);
}

.dashboard-bar-fill.error {
  background: var(--ag-red);
}

.dashboard-bar-fill.other,
.dashboard-bar-fill.yellow {
  background: var(--ag-yellow);
}

.dashboard-run-row,
.dashboard-incident-row {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-panel);
  background: var(--ag-panel-soft);
  padding: 10px;
}

.dashboard-run-copy,
.dashboard-incident-row > div {
  display: grid;
  min-width: 0;
  flex: 1;
  gap: 4px;
}

.dashboard-run-copy > div {
  justify-content: space-between;
  gap: 12px;
}

.dashboard-run-copy strong,
.dashboard-incident-row strong,
.dashboard-model-row strong {
  min-width: 0;
  overflow: hidden;
  color: var(--ag-heading);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-status {
  width: 9px;
  height: 9px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: var(--ag-muted);
}

.run-status.ok {
  background: var(--ag-green);
}

.run-status.error {
  background: var(--ag-red);
}

.run-status.other {
  background: var(--ag-yellow);
}

.dashboard-scope-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 14px;
}

.dashboard-scope-grid > div {
  display: grid;
  gap: 6px;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-panel);
  background: var(--ag-panel-soft);
  padding: 12px;
}

.dashboard-scope-grid strong {
  font-size: 18px;
}

.dashboard-model-row {
  justify-content: space-between;
  gap: 12px;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-panel);
  background: var(--ag-panel-soft);
  padding: 10px;
}

.dashboard-model-row > div {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.dashboard-model-row em {
  flex: 0 0 auto;
  color: var(--ag-muted);
  font-size: 11px;
  font-style: normal;
}

.dashboard-empty {
  border: 1px dashed var(--ag-border);
  border-radius: var(--ag-radius-panel);
  padding: 24px;
  color: var(--ag-muted);
  font-size: 12px;
  text-align: center;
}

.dashboard-empty.ok {
  color: var(--ag-green);
}

@media (max-width: 1100px) {
  .dashboard-kpi-grid,
  .dashboard-chart-grid,
  .dashboard-chart-grid.wide-left {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .dashboard-header,
  .dashboard-header-actions,
  .dashboard-view-tabs {
    align-items: stretch;
  }

  .dashboard-header,
  .dashboard-header-actions {
    flex-direction: column;
  }

  .dashboard-view-tabs button,
  .dashboard-range {
    flex: 1;
    width: 100%;
  }

  .dashboard-kpi-grid,
  .dashboard-chart-grid,
  .dashboard-chart-grid.wide-left,
  .dashboard-scope-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
