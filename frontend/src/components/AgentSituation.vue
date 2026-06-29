<template>
  <div class="situation-page h-full min-h-0 overflow-y-auto bg-[#F5F7FA] p-3 text-[#15202B] dark:bg-[#071014] dark:text-[#DCE7EF]">
    <header class="situation-header">
      <div class="flex min-w-0 items-center gap-3">
        <div class="situation-core" :class="{ warning: errorRunCount > 0 }">
          <el-icon><DataBoard /></el-icon>
        </div>
        <div class="min-w-0">
          <h3 class="truncate text-sm font-semibold text-[#15202B] dark:text-white">安全运营态势总览</h3>
          <p class="mt-1 text-xs text-[#6B7C8A] dark:text-[#91A4B3]">资产、漏洞、响应链路、异常态势与 Agent 负载</p>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <el-select v-model="timeScope" size="small" class="w-[132px]" @change="loadSituation">
          <el-option label="最近 24 小时" value="24h" />
          <el-option label="最近 7 天" value="7d" />
          <el-option label="最近 30 天" value="30d" />
        </el-select>
        <el-button type="primary" size="small" :loading="loading" class="cursor-pointer" @click="loadSituation">
          <el-icon class="mr-1"><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </header>

    <section class="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <article v-for="metric in topMetrics" :key="metric.label" class="situation-metric">
        <div class="flex items-center justify-between gap-2">
          <span>{{ metric.label }}</span>
          <el-icon><component :is="metric.icon" /></el-icon>
        </div>
        <strong>{{ metric.value }}</strong>
        <em>{{ metric.hint }}</em>
      </article>
    </section>

    <section class="mt-3 grid gap-3 xl:grid-cols-[minmax(0,1.4fr)_minmax(360px,0.8fr)]">
      <article class="situation-panel min-w-0">
        <div class="panel-title">
          <el-icon><TrendCharts /></el-icon>
          最近研判链路
        </div>
        <div class="mt-4 space-y-2">
          <div v-for="trace in recentRuns" :key="trace.trace_id" class="run-row">
            <span class="run-status" :class="statusClass(trace.status, trace.error_count)" />
            <div class="min-w-0 flex-1">
              <div class="flex items-center justify-between gap-3">
                <strong class="truncate" :title="trace.name">{{ trace.name || trace.trace_id }}</strong>
                <span class="font-mono text-[11px] text-[#6B7C8A] dark:text-[#91A4B3]">{{ formatDuration(trace.duration_ms) }}</span>
              </div>
              <div class="mt-2 flex items-center gap-2">
                <span class="duration-track">
                  <span class="duration-bar" :class="{ error: hasError(trace) }" :style="{ width: durationWidth(trace.duration_ms) }" />
                </span>
                <span class="shrink-0 font-mono text-[10px] text-[#8A99A6]">{{ shortId(trace.trace_id) }}</span>
              </div>
              <div class="mt-2 flex flex-wrap gap-1.5">
                <span class="record-chip mono">会话 {{ shortId(trace.session_id || "") }}</span>
                <span class="record-chip mono">运行 {{ shortId(trace.run_id || "") }}</span>
                <span class="record-chip">Agent {{ shortId(trace.agent_id || trace.team_id || trace.workflow_id || "") }}</span>
              </div>
            </div>
          </div>

          <div v-if="!recentRuns.length && !loading" class="empty-box">暂无 Agent 运行数据</div>
        </div>
      </article>

      <article class="situation-panel">
        <div class="panel-title">
          <el-icon><Histogram /></el-icon>
          状态分布
        </div>
        <div class="mt-4 space-y-3">
          <div v-for="item in statusBars" :key="item.label">
            <div class="mb-1 flex items-center justify-between text-xs">
              <span class="text-[#6B7C8A] dark:text-[#91A4B3]">{{ item.label }}</span>
              <strong class="text-[#15202B] dark:text-[#DCE7EF]">{{ item.count }}</strong>
            </div>
            <span class="status-track">
              <span class="status-bar" :class="item.className" :style="{ width: item.width }" />
            </span>
          </div>
        </div>
      </article>
    </section>

    <section class="mt-3 grid gap-3 xl:grid-cols-[minmax(360px,0.9fr)_minmax(0,1.1fr)]">
      <article class="situation-panel">
        <div class="panel-title">
          <el-icon><Cpu /></el-icon>
          Agent 响应负载
        </div>
        <div class="mt-4 space-y-2">
          <div v-for="agent in agentRows" :key="agent.id" class="agent-load-row">
            <div class="min-w-0">
              <strong class="truncate">{{ agent.id }}</strong>
              <span>{{ agent.runs }} runs · {{ agent.errors }} errors</span>
            </div>
            <em>{{ formatDuration(agent.avgDuration) }}</em>
          </div>
          <div v-if="!agentRows.length && !loading" class="empty-box">暂无 Agent 维度数据</div>
        </div>
      </article>

      <article class="situation-panel min-w-0">
        <div class="panel-title">
          <el-icon><Odometer /></el-icon>
          异常响应
        </div>
        <div class="mt-4 space-y-2">
          <div v-for="trace in errorRuns" :key="trace.trace_id" class="incident-row">
            <span class="run-status error" />
            <div class="min-w-0">
              <strong class="truncate" :title="trace.name">{{ trace.name || trace.trace_id }}</strong>
              <p class="truncate font-mono">{{ trace.trace_id }}</p>
            </div>
            <span>{{ trace.error_count ?? 0 }} errors</span>
          </div>
          <div v-if="!errorRuns.length && !loading" class="empty-box ok">最近样本未发现异常运行</div>
        </div>
      </article>
    </section>

    <el-alert v-if="apiError" class="mt-3" type="error" :title="apiError" show-icon />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, type Component } from "vue"
import { Cpu, DataBoard, Histogram, Odometer, Refresh, TrendCharts, WarningFilled } from "@element-plus/icons-vue"
import { useTracingApi } from "../composables/useApi"
import type { TraceItem } from "../types"

type TimeScope = "24h" | "7d" | "30d"

const { loading, error, listTraces } = useTracingApi()
const traces = ref<TraceItem[]>([])
const totalCount = ref(0)
const timeScope = ref<TimeScope>("24h")

const apiError = computed(() => error.value)
const sampleSize = computed(() => traces.value.length)
const errorRunCount = computed(() => traces.value.filter((trace) => hasError(trace)).length)
const okRunCount = computed(() => traces.value.filter((trace) => trace.status === "OK" && !hasError(trace)).length)
const totalSpans = computed(() => traces.value.reduce((sum, trace) => sum + Number(trace.total_spans || 0), 0))
const avgDuration = computed(() => {
  if (!traces.value.length) return 0
  return traces.value.reduce((sum, trace) => sum + Number(trace.duration_ms || 0), 0) / traces.value.length
})
const successRate = computed(() => {
  if (!sampleSize.value) return "0%"
  return `${Math.round((okRunCount.value / sampleSize.value) * 100)}%`
})

const topMetrics = computed<Array<{ label: string; value: string | number; hint: string; icon: Component }>>(() => [
  { label: "运行样本", value: totalCount.value, hint: `当前样本 ${sampleSize.value} 条`, icon: TrendCharts },
  { label: "响应成功率", value: successRate.value, hint: "按最近样本计算", icon: DataBoard },
  { label: "异常运行", value: errorRunCount.value, hint: "状态 ERROR 或含错误 Span", icon: WarningFilled },
  { label: "平均耗时", value: formatDuration(avgDuration.value), hint: `${totalSpans.value} spans observed`, icon: Odometer },
])

const recentRuns = computed(() => traces.value.slice(0, 12))
const errorRuns = computed(() => traces.value.filter((trace) => hasError(trace)).slice(0, 8))
const maxDuration = computed(() => Math.max(...traces.value.map((trace) => Number(trace.duration_ms || 0)), 1))

const statusBars = computed(() => {
  const total = Math.max(sampleSize.value, 1)
  const items = [
    { label: "OK", count: okRunCount.value, className: "ok" },
    { label: "ERROR", count: errorRunCount.value, className: "error" },
    { label: "UNSET / OTHER", count: Math.max(sampleSize.value - okRunCount.value - errorRunCount.value, 0), className: "other" },
  ]
  return items.map((item) => ({
    ...item,
    width: `${Math.max((item.count / total) * 100, item.count ? 6 : 0)}%`,
  }))
})

const agentRows = computed(() => {
  const buckets = new Map<string, { id: string; runs: number; errors: number; duration: number }>()
  for (const trace of traces.value) {
    const id = trace.agent_id || trace.team_id || trace.workflow_id || "default-agent"
    const item = buckets.get(id) || { id, runs: 0, errors: 0, duration: 0 }
    item.runs += 1
    item.errors += hasError(trace) ? 1 : 0
    item.duration += Number(trace.duration_ms || 0)
    buckets.set(id, item)
  }
  return [...buckets.values()]
    .map((item) => ({ ...item, avgDuration: item.runs ? item.duration / item.runs : 0 }))
    .sort((a, b) => b.runs - a.runs)
    .slice(0, 8)
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

const loadSituation = async () => {
  const response = await listTraces({
    page: 1,
    limit: 60,
    start_time: rangeStart(),
  })
  traces.value = response.items || []
  totalCount.value = response.total_count || 0
}

const hasError = (trace: TraceItem) => {
  return trace.status === "ERROR" || Number(trace.error_count || 0) > 0
}

const statusClass = (status: string, errorCount?: number) => {
  if (status === "ERROR" || Number(errorCount || 0) > 0) return "error"
  if (status === "OK") return "ok"
  return "other"
}

const durationWidth = (durationMs: number) => {
  const pct = (Number(durationMs || 0) / maxDuration.value) * 100
  return `${Math.max(6, Math.min(100, pct))}%`
}

const shortId = (id: string) => {
  if (!id) return "-"
  return id.length > 14 ? `${id.slice(0, 6)}...${id.slice(-6)}` : id
}

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
  loadSituation()
})
</script>

<style>
.situation-page {
  font-family: "Fira Sans", "Microsoft YaHei", sans-serif;
}

.situation-header,
.situation-metric,
.situation-panel,
.run-row,
.agent-load-row,
.incident-row {
  border: 1px solid #d8e0e7;
  border-radius: 8px;
  background: #ffffff;
}

.situation-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
}

.situation-core {
  display: grid;
  width: 40px;
  height: 40px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid rgba(47, 143, 237, 0.35);
  border-radius: 8px;
  background: #eaf5ff;
  color: #0969da;
}

.situation-core.warning {
  border-color: rgba(240, 106, 106, 0.45);
  background: #fff1f1;
  color: #d93030;
}

.situation-metric,
.situation-panel {
  padding: 14px;
}

.situation-metric span,
.situation-metric em {
  display: block;
  color: #6b7c8a;
  font-size: 11px;
  font-style: normal;
}

.situation-metric strong {
  display: block;
  margin-top: 10px;
  color: #15202b;
  font-size: 22px;
  font-weight: 700;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #15202b;
  font-size: 13px;
  font-weight: 700;
}

.run-row,
.agent-load-row,
.incident-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
}

.run-status {
  width: 9px;
  height: 9px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: #91a0ad;
}

.run-status.ok {
  background: #54d38a;
}

.run-status.error {
  background: #f06a6a;
}

.run-status.other {
  background: #f6c343;
}

.run-row strong,
.agent-load-row strong,
.incident-row strong {
  color: #15202b;
  font-size: 12px;
}

.duration-track,
.status-track {
  display: block;
  overflow: hidden;
  border-radius: 999px;
  background: #e6edf3;
}

.duration-track {
  height: 8px;
  flex: 1;
}

.status-track {
  height: 10px;
}

.duration-bar,
.status-bar {
  display: block;
  height: 100%;
  min-width: 4px;
  border-radius: inherit;
  background: linear-gradient(90deg, #2f8fed, #54d38a);
}

.duration-bar.error,
.status-bar.error {
  background: linear-gradient(90deg, #f06a6a, #f6c343);
}

.record-chip {
  display: inline-flex;
  align-items: center;
  border: 1px solid #d8e0e7;
  border-radius: 999px;
  padding: 2px 7px;
  color: #526170;
  font-size: 10px;
}

.record-chip.mono {
  font-family: "Fira Code", monospace;
}

.status-bar.ok {
  background: #54d38a;
}

.status-bar.other {
  background: #f6c343;
}

.agent-load-row {
  justify-content: space-between;
}

.agent-load-row span,
.incident-row p {
  display: block;
  margin-top: 4px;
  color: #6b7c8a;
  font-size: 11px;
}

.agent-load-row em,
.incident-row > span {
  flex: 0 0 auto;
  color: #526170;
  font-family: "Fira Code", monospace;
  font-size: 11px;
  font-style: normal;
}

.incident-row {
  justify-content: space-between;
}

.empty-box {
  border: 1px dashed #d8e0e7;
  border-radius: 8px;
  padding: 28px;
  color: #6b7c8a;
  font-size: 12px;
  text-align: center;
}

.empty-box.ok {
  color: #14824a;
}

html.dark .situation-header,
html.dark .situation-metric,
html.dark .situation-panel,
html.dark .run-row,
html.dark .agent-load-row,
html.dark .incident-row {
  border-color: #22313a;
  background: #0f1b22;
}

html.dark .situation-core {
  border-color: rgba(139, 217, 255, 0.28);
  background: #102638;
  color: #8bd9ff;
}

html.dark .situation-core.warning {
  border-color: rgba(240, 106, 106, 0.45);
  background: #2b1518;
  color: #ff9a9a;
}

html.dark .situation-metric span,
html.dark .situation-metric em,
html.dark .agent-load-row span,
html.dark .incident-row p {
  color: #758998;
}

html.dark .situation-metric strong,
html.dark .panel-title,
html.dark .run-row strong,
html.dark .agent-load-row strong,
html.dark .incident-row strong {
  color: #dce7ef;
}

html.dark .duration-track,
html.dark .status-track {
  background: #22313a;
}

html.dark .record-chip {
  border-color: #22313a;
  color: #91a4b3;
}

html.dark .agent-load-row em,
html.dark .incident-row > span {
  color: #91a4b3;
}

html.dark .empty-box {
  border-color: #22313a;
  color: #758998;
}
</style>
