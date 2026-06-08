<template>
  <div class="trace-console flex h-full min-h-0 flex-col overflow-hidden bg-[#F5F7FA] text-[#15202B] dark:bg-[#071014] dark:text-[#DCE7EF]">
    <header class="border-b border-[#D8E0E7] bg-white/90 p-3 dark:border-[#22313A] dark:bg-[#0A151B]">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-3">
          <div class="trace-core" :class="{ 'has-error': traceHealth.errors > 0 }">
            <el-icon><DataAnalysis /></el-icon>
          </div>
          <div>
            <h3 class="text-sm font-semibold text-[#15202B] dark:text-white">Agent 运行观测</h3>
            <p class="mt-1 text-xs text-[#6B7C8A] dark:text-[#91A4B3]">
              Trace 队列、Span 瀑布与工具调用诊断
            </p>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <el-input
            v-model="filters.session_id"
            size="small"
            clearable
            placeholder="session_id"
            class="w-full sm:w-[220px]"
          />
          <el-select v-model="filters.status" size="small" clearable placeholder="状态" class="w-[112px]">
            <el-option label="OK" value="OK" />
            <el-option label="ERROR" value="ERROR" />
            <el-option label="UNSET" value="UNSET" />
          </el-select>
          <el-date-picker
            v-model="filters.timeRange"
            type="datetimerange"
            size="small"
            unlink-panels
            start-placeholder="开始"
            end-placeholder="结束"
            value-format="YYYY-MM-DDTHH:mm:ssXXX"
            class="trace-date-picker"
          />
          <el-tooltip content="刷新 Trace 队列" placement="bottom">
            <el-button size="small" type="primary" :loading="loading" @click="refresh" class="cursor-pointer">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="复制 Trace ID" placement="bottom">
            <el-button size="small" :disabled="!selectedTrace" @click="copySelectedTraceId" class="cursor-pointer">
              <el-icon><CopyDocument /></el-icon>
            </el-button>
          </el-tooltip>
        </div>
      </div>

      <div class="mt-3 grid gap-2 sm:grid-cols-4">
        <div v-for="metric in traceMetrics" :key="metric.label" class="trace-metric">
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}</strong>
          <em>{{ metric.hint }}</em>
        </div>
      </div>
    </header>

    <div class="grid min-h-0 flex-1 grid-cols-1 grid-rows-[280px_minmax(0,1fr)] lg:grid-cols-[360px_minmax(0,1fr)] lg:grid-rows-1">
      <aside class="flex min-h-0 flex-col border-r border-[#D8E0E7] bg-white/85 dark:border-[#22313A] dark:bg-[#0A151B]">
        <div class="flex items-center justify-between border-b border-[#D8E0E7] px-3 py-2 dark:border-[#22313A]">
          <div>
            <div class="text-xs font-semibold uppercase tracking-wide text-[#6B7C8A] dark:text-[#758998]">Trace Queue</div>
            <div class="mt-0.5 text-[11px] text-[#91A0AD]">共 {{ totalCount }} 条 · page {{ page }}</div>
          </div>
          <el-pagination
            size="small"
            background
            layout="prev, next"
            :total="totalCount"
            :page-size="limit"
            :current-page="page"
            @current-change="onPageChange"
          />
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto p-2">
          <button
            v-for="trace in traceItems"
            :key="trace.trace_id"
            type="button"
            class="trace-card"
            :class="{ active: selectedTrace?.trace_id === trace.trace_id, error: (trace.error_count ?? 0) > 0 || trace.status === 'ERROR' }"
            @click="onTraceSelect(trace)"
          >
            <span class="trace-status-dot" :class="statusClass(trace.status)" />
            <span class="min-w-0 flex-1">
              <span class="flex items-center justify-between gap-2">
                <strong class="truncate" :title="trace.name">{{ trace.name }}</strong>
                <el-tag :type="tagType(trace.status)" effect="light" size="small">{{ trace.status }}</el-tag>
              </span>
              <span class="mt-1 block truncate font-mono text-[10px] text-[#7D8D9A]" :title="trace.trace_id">
                {{ trace.trace_id }}
              </span>
              <span class="mt-2 grid grid-cols-3 gap-1 text-[11px]">
                <em><el-icon><Clock /></el-icon>{{ formatDuration(trace.duration_ms) }}</em>
                <em><el-icon><Connection /></el-icon>{{ trace.total_spans ?? 0 }}</em>
                <em><el-icon><WarningFilled /></el-icon>{{ trace.error_count ?? 0 }}</em>
              </span>
            </span>
          </button>

          <div v-if="!traceItems.length && !loading" class="rounded-lg border border-dashed border-[#D8E0E7] p-8 text-center text-xs text-[#6B7C8A] dark:border-[#22313A] dark:text-[#758998]">
            当前筛选条件下暂无 Trace
          </div>
        </div>
      </aside>

      <main class="min-h-0 overflow-hidden">
        <div v-if="!selectedTrace" class="grid h-full place-items-center p-6">
          <div class="empty-observe">
            <el-icon><Aim /></el-icon>
            <strong>选择一次 Agent Run</strong>
            <span>从左侧队列进入 Trace，可查看 Span 瀑布、错误原因和 attributes。</span>
          </div>
        </div>

        <div v-else class="grid h-full min-h-0 grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px]">
          <section class="flex min-h-0 flex-col overflow-hidden">
            <div class="border-b border-[#D8E0E7] bg-white/75 p-3 dark:border-[#22313A] dark:bg-[#0A151B]/75">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="trace-status-dot large" :class="statusClass(selectedTrace.status)" />
                    <h4 class="truncate text-sm font-semibold text-[#15202B] dark:text-white" :title="selectedTrace.name">
                      {{ selectedTrace.name }}
                    </h4>
                    <el-tag :type="tagType(selectedTrace.status)" effect="light" size="small">{{ selectedTrace.status }}</el-tag>
                  </div>
                  <p class="mt-1 break-all font-mono text-[11px] text-[#6B7C8A] dark:text-[#91A4B3]">{{ selectedTrace.trace_id }}</p>
                </div>
                <div class="flex flex-wrap gap-2">
                  <el-button size="small" plain class="cursor-pointer" @click="copyText(selectedTrace.session_id || '')" :disabled="!selectedTrace.session_id">
                    session_id
                  </el-button>
                  <el-button size="small" plain class="cursor-pointer" @click="copyText(selectedTrace.run_id || '')" :disabled="!selectedTrace.run_id">
                    run_id
                  </el-button>
                  <el-button size="small" plain class="cursor-pointer" @click="refreshSelectedTrace" :loading="loadingDetail">
                    重新拉取
                  </el-button>
                </div>
              </div>

              <div class="mt-3 grid gap-2 sm:grid-cols-4">
                <div v-for="metric in selectedTraceMetrics" :key="metric.label" class="trace-detail-metric">
                  <span>{{ metric.label }}</span>
                  <strong>{{ metric.value }}</strong>
                </div>
              </div>
            </div>

            <div class="min-h-0 flex-1 overflow-y-auto p-3">
              <div class="mb-3 flex items-center justify-between">
                <div class="text-xs font-semibold uppercase tracking-wide text-[#6B7C8A] dark:text-[#758998]">Span Waterfall</div>
                <div class="font-mono text-[11px] text-[#91A0AD]">{{ spans.length }} spans</div>
              </div>

              <div v-if="spans.length" class="space-y-2">
                <button
                  v-for="span in spans"
                  :key="span.span_id"
                  type="button"
                  class="span-row"
                  :class="{ active: selectedSpan?.span_id === span.span_id, error: span.status_code === 'ERROR' }"
                  @click="selectedSpan = span"
                >
                  <span class="span-meta">
                    <span class="trace-status-dot" :class="statusClass(span.status_code)" />
                    <strong class="truncate" :title="span.name">{{ span.name }}</strong>
                    <em>{{ span.kind || 'span' }}</em>
                  </span>
                  <span class="span-bar-track">
                    <span class="span-bar" :class="{ error: span.status_code === 'ERROR' }" :style="spanBarStyle(span)" />
                  </span>
                  <span class="span-duration">{{ formatDuration(span.duration_ms) }}</span>
                </button>
              </div>

              <div v-else class="rounded-lg border border-dashed border-[#D8E0E7] p-10 text-center text-xs text-[#6B7C8A] dark:border-[#22313A] dark:text-[#758998]">
                暂无 spans
              </div>

              <div class="mt-4 rounded-lg border border-[#D8E0E7] bg-white p-3 dark:border-[#22313A] dark:bg-[#0A151B]">
                <div class="mb-2 flex items-center justify-between">
                  <div class="text-xs font-semibold uppercase tracking-wide text-[#6B7C8A] dark:text-[#758998]">Span Tree</div>
                  <span class="text-[11px] text-[#91A0AD]">点击节点定位详情</span>
                </div>
                <el-tree
                  v-if="tree.length"
                  :data="tree"
                  node-key="span.span_id"
                  :expand-on-click-node="false"
                  default-expand-all
                  class="bg-transparent"
                  @node-click="onSpanNodeClick"
                >
                  <template #default="{ data }">
                    <div class="flex min-w-0 items-center gap-2">
                      <span class="trace-status-dot" :class="statusClass(data.span.status_code)" />
                      <span class="truncate text-xs text-[#15202B] dark:text-[#DCE7EF]" :title="data.span.name">{{ data.span.name }}</span>
                      <span class="font-mono text-[10px] text-[#7D8D9A]">{{ formatDuration(data.span.duration_ms) }}</span>
                    </div>
                  </template>
                </el-tree>
              </div>
            </div>
          </section>

          <aside class="min-h-0 overflow-y-auto border-l border-[#D8E0E7] bg-white/85 p-3 dark:border-[#22313A] dark:bg-[#0A151B]">
            <div class="diagnostic-card">
              <div class="diagnostic-title">
                <el-icon><Cpu /></el-icon>
                Span 诊断
              </div>

              <div v-if="!selectedSpan" class="py-10 text-center text-xs text-[#6B7C8A] dark:text-[#758998]">
                点击 Span 瀑布或树节点查看 attributes
              </div>

              <div v-else class="mt-3 space-y-3">
                <div>
                  <div class="text-[11px] text-[#6B7C8A] dark:text-[#758998]">名称</div>
                  <div class="mt-1 break-words text-sm font-semibold text-[#15202B] dark:text-white">{{ selectedSpan.name }}</div>
                </div>

                <div class="grid grid-cols-2 gap-2">
                  <div class="trace-detail-metric">
                    <span>状态</span>
                    <strong>{{ selectedSpan.status_code }}</strong>
                  </div>
                  <div class="trace-detail-metric">
                    <span>耗时</span>
                    <strong>{{ formatDuration(selectedSpan.duration_ms) }}</strong>
                  </div>
                </div>

                <div v-if="selectedSpan.status_message" class="rounded-lg border border-red-200 bg-red-50 p-3 dark:border-red-800/50 dark:bg-red-950/20">
                  <div class="text-[11px] font-semibold text-red-700 dark:text-red-300">错误信息</div>
                  <div class="mt-1 break-words text-xs text-red-700 dark:text-red-300">{{ selectedSpan.status_message }}</div>
                </div>

                <div>
                  <div class="mb-2 flex items-center justify-between">
                    <span class="text-[11px] font-semibold uppercase tracking-wide text-[#6B7C8A] dark:text-[#758998]">Attributes</span>
                    <el-button size="small" plain class="cursor-pointer" :disabled="!selectedSpan" @click="copySpanJson">
                      复制 JSON
                    </el-button>
                  </div>
                  <pre class="trace-json">{{ prettyJson(selectedSpan.attributes) }}</pre>
                </div>
              </div>
            </div>

            <div v-if="apiError" class="mt-3">
              <el-alert type="error" :title="apiError" show-icon />
            </div>
          </aside>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import { ElMessage } from "element-plus"
import {
  Aim,
  Clock,
  Connection,
  CopyDocument,
  Cpu,
  DataAnalysis,
  Refresh,
  WarningFilled,
} from "@element-plus/icons-vue"
import { useTracingApi } from "../composables/useApi"
import type { TraceItem, SpanItem, SpanTreeNode, TraceStatus } from "../types"

const { loading, error, listTraces, getTrace } = useTracingApi()

const page = ref(1)
const limit = ref(20)
const totalCount = ref(0)

const traceItems = ref<TraceItem[]>([])

const filters = reactive<{ session_id: string; status: TraceStatus | ""; timeRange: [string, string] | null }>(
  {
    session_id: "",
    status: "",
    timeRange: null,
  }
)

const selectedTrace = ref<TraceItem | null>(null)
const spans = ref<SpanItem[]>([])
const tree = ref<SpanTreeNode[]>([])
const selectedSpan = ref<SpanItem | null>(null)

const loadingDetail = ref(false)
const apiError = computed(() => error.value)

const traceHealth = computed(() => {
  const errors = traceItems.value.reduce((sum, item) => sum + (item.error_count ?? 0), 0)
  const ok = traceItems.value.filter((item) => item.status === "OK").length
  const avgDuration = traceItems.value.length
    ? traceItems.value.reduce((sum, item) => sum + Number(item.duration_ms || 0), 0) / traceItems.value.length
    : 0

  return { errors, ok, avgDuration }
})

const traceMetrics = computed(() => [
  { label: "Trace", value: totalCount.value, hint: "当前查询总量" },
  { label: "OK", value: traceHealth.value.ok, hint: "本页成功运行" },
  { label: "Errors", value: traceHealth.value.errors, hint: "本页错误 Span" },
  { label: "Avg Latency", value: formatDuration(traceHealth.value.avgDuration), hint: "本页平均耗时" },
])

const selectedTraceMetrics = computed(() => {
  const trace = selectedTrace.value
  if (!trace) return []
  return [
    { label: "开始", value: fmt(trace.start_time) },
    { label: "结束", value: fmt(trace.end_time) },
    { label: "耗时", value: formatDuration(trace.duration_ms) },
    { label: "Spans", value: String(trace.total_spans ?? spans.value.length) },
  ]
})

const fmt = (iso: string) => {
  if (!iso) return ""
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

const tagType = (status: string) => {
  if (status === "OK") return "success"
  if (status === "ERROR") return "danger"
  if (status === "UNSET") return "info"
  return "warning"
}

const statusClass = (status: string) => {
  if (status === "OK") return "ok"
  if (status === "ERROR") return "error"
  if (status === "UNSET") return "unset"
  return "other"
}

const formatDuration = (durationMs: number | string | null | undefined): string => {
  const n = Number(durationMs)
  if (!Number.isFinite(n) || n < 0) return "-"

  if (n < 1000) {
    if (n < 10) return `${n.toFixed(2)} ms`
    if (n < 100) return `${n.toFixed(1)} ms`
    return `${Math.round(n)} ms`
  }

  const sec = n / 1000
  if (sec < 60) {
    return sec < 10 ? `${sec.toFixed(2)} s` : `${sec.toFixed(1)} s`
  }

  const min = Math.floor(sec / 60)
  const remSec = sec % 60
  if (min < 60) return `${min}m ${remSec.toFixed(1)}s`

  const hour = Math.floor(min / 60)
  const remMin = min % 60
  return `${hour}h ${remMin}m ${Math.round(remSec)}s`
}

const prettyJson = (obj: unknown) => {
  try {
    if (!obj) return "{}"
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

const spanBarStyle = (span: SpanItem) => {
  const maxDuration = Math.max(...spans.value.map((item) => Number(item.duration_ms || 0)), 1)
  const width = Math.max(4, Math.round((Number(span.duration_ms || 0) / maxDuration) * 100))
  return { width: `${width}%` }
}

const refresh = async () => {
  selectedTrace.value = null
  selectedSpan.value = null
  spans.value = []
  tree.value = []

  const [start_time, end_time] = filters.timeRange || ["", ""]
  const resp = await listTraces({
    page: page.value,
    limit: limit.value,
    status: filters.status || "",
    session_id: filters.session_id.trim() || undefined,
    start_time: start_time || undefined,
    end_time: end_time || undefined,
  })

  traceItems.value = resp.items || []
  totalCount.value = resp.total_count || 0
}

const refreshSelectedTrace = async () => {
  if (!selectedTrace.value) return
  loadingDetail.value = true
  try {
    const resp = await getTrace(selectedTrace.value.trace_id)
    selectedTrace.value = resp.trace
    spans.value = resp.spans || []
    tree.value = resp.tree || []
    selectedSpan.value = null
  } finally {
    loadingDetail.value = false
  }
}

const onTraceSelect = async (row: TraceItem | null) => {
  if (!row) return
  selectedTrace.value = row
  selectedSpan.value = null
  spans.value = []
  tree.value = []
  await refreshSelectedTrace()
}

const onSpanNodeClick = (node: SpanTreeNode) => {
  selectedSpan.value = node.span
}

const onPageChange = async (p: number) => {
  page.value = p
  await refresh()
}

const copyText = async (text: string) => {
  const t = (text || "").trim()
  if (!t) return
  try {
    await navigator.clipboard.writeText(t)
    ElMessage.success("已复制")
  } catch {
    ElMessage.warning("复制失败（请检查浏览器权限）")
  }
}

const copySelectedTraceId = async () => {
  if (!selectedTrace.value) return
  await copyText(selectedTrace.value.trace_id)
}

const copySpanJson = async () => {
  if (!selectedSpan.value) return
  await copyText(JSON.stringify(selectedSpan.value, null, 2))
}

watch(
  () => [filters.session_id, filters.status, filters.timeRange],
  () => {
    page.value = 1
  }
)

onMounted(async () => {
  try {
    await refresh()
  } catch (e: unknown) {
    // prefer showing API error message
    ElMessage.error(e instanceof Error ? e.message : "加载 traces 失败")
  }
})
</script>

<style>
.trace-console {
  font-family: "Fira Sans", "Microsoft YaHei", sans-serif;
}

.trace-core {
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

.trace-core.has-error {
  border-color: rgba(240, 106, 106, 0.45);
  background: #fff1f1;
  color: #d93030;
}

.trace-metric,
.trace-detail-metric {
  border: 1px solid #d8e0e7;
  border-radius: 8px;
  background: #f8fafc;
  padding: 10px;
}

.trace-metric span,
.trace-detail-metric span {
  display: block;
  color: #6b7c8a;
  font-size: 11px;
}

.trace-metric strong,
.trace-detail-metric strong {
  display: block;
  margin-top: 3px;
  color: #15202b;
  font-size: 15px;
  font-weight: 700;
}

.trace-metric em {
  display: block;
  margin-top: 2px;
  color: #91a0ad;
  font-size: 10px;
  font-style: normal;
}

.trace-card {
  display: flex;
  width: 100%;
  gap: 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 10px;
  text-align: left;
  transition: border-color 0.2s ease, background-color 0.2s ease;
  cursor: pointer;
}

.trace-card:hover,
.trace-card.active {
  border-color: rgba(47, 143, 237, 0.45);
  background: #eaf5ff;
}

.trace-card.error {
  border-left-color: #f06a6a;
}

.trace-card strong {
  color: #15202b;
  font-size: 12px;
}

.trace-card em {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  overflow: hidden;
  color: #6b7c8a;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  margin-top: 5px;
  border-radius: 999px;
  background: #91a0ad;
}

.trace-status-dot.large {
  width: 10px;
  height: 10px;
  margin-top: 0;
}

.trace-status-dot.ok {
  background: #54d38a;
}

.trace-status-dot.error {
  background: #f06a6a;
}

.trace-status-dot.unset {
  background: #f6c343;
}

.empty-observe {
  display: grid;
  width: min(360px, 100%);
  place-items: center;
  border: 1px dashed #d8e0e7;
  border-radius: 8px;
  background: #ffffff;
  padding: 32px;
  text-align: center;
}

.empty-observe .el-icon {
  color: #0969da;
  font-size: 28px;
}

.empty-observe strong {
  margin-top: 12px;
  color: #15202b;
  font-size: 14px;
}

.empty-observe span {
  margin-top: 6px;
  color: #6b7c8a;
  font-size: 12px;
  line-height: 1.6;
}

.span-row {
  display: grid;
  width: 100%;
  grid-template-columns: minmax(160px, 260px) minmax(120px, 1fr) 86px;
  align-items: center;
  gap: 10px;
  border: 1px solid #d8e0e7;
  border-radius: 8px;
  background: #ffffff;
  padding: 9px;
  text-align: left;
  transition: border-color 0.2s ease, background-color 0.2s ease;
  cursor: pointer;
}

.span-row:hover,
.span-row.active {
  border-color: rgba(47, 143, 237, 0.5);
  background: #eaf5ff;
}

.span-row.error {
  border-color: rgba(240, 106, 106, 0.45);
}

.span-meta {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.span-meta strong {
  min-width: 0;
  color: #15202b;
  font-size: 12px;
}

.span-meta em {
  flex: 0 0 auto;
  border: 1px solid #d8e0e7;
  border-radius: 999px;
  padding: 1px 6px;
  color: #6b7c8a;
  font-size: 10px;
  font-style: normal;
}

.span-bar-track {
  height: 9px;
  overflow: hidden;
  border-radius: 999px;
  background: #e6edf3;
}

.span-bar {
  display: block;
  height: 100%;
  min-width: 6px;
  border-radius: inherit;
  background: linear-gradient(90deg, #2f8fed, #54d38a);
}

.span-bar.error {
  background: linear-gradient(90deg, #f06a6a, #f6c343);
}

.span-duration {
  color: #526170;
  font-family: "Fira Code", monospace;
  font-size: 11px;
  text-align: right;
}

.diagnostic-card {
  border: 1px solid #d8e0e7;
  border-radius: 8px;
  background: #f8fafc;
  padding: 12px;
}

.diagnostic-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #15202b;
  font-size: 13px;
  font-weight: 700;
}

.trace-json {
  max-height: 420px;
  overflow: auto;
  border: 1px solid #d8e0e7;
  border-radius: 8px;
  background: #ffffff;
  padding: 10px;
  color: #15202b;
  font-family: "Fira Code", monospace;
  font-size: 11px;
  line-height: 1.55;
}

.trace-console .el-tree {
  background: transparent;
}

.trace-console .el-tree-node__content {
  height: 30px;
}

html.dark .trace-core {
  border-color: rgba(139, 217, 255, 0.28);
  background: #102638;
  color: #8bd9ff;
}

html.dark .trace-core.has-error {
  border-color: rgba(240, 106, 106, 0.45);
  background: #2b1518;
  color: #ff9a9a;
}

html.dark .trace-metric,
html.dark .trace-detail-metric,
html.dark .empty-observe,
html.dark .span-row,
html.dark .diagnostic-card,
html.dark .trace-json {
  border-color: #22313a;
  background: #0f1b22;
}

html.dark .trace-metric span,
html.dark .trace-detail-metric span,
html.dark .trace-metric em,
html.dark .trace-card em,
html.dark .empty-observe span {
  color: #758998;
}

html.dark .trace-metric strong,
html.dark .trace-detail-metric strong,
html.dark .trace-card strong,
html.dark .empty-observe strong,
html.dark .span-meta strong,
html.dark .diagnostic-title,
html.dark .trace-json {
  color: #dce7ef;
}

html.dark .trace-card:hover,
html.dark .trace-card.active,
html.dark .span-row:hover,
html.dark .span-row.active {
  border-color: rgba(139, 217, 255, 0.35);
  background: #102638;
}

html.dark .span-meta em {
  border-color: #22313a;
  color: #91a4b3;
}

html.dark .span-bar-track {
  background: #22313a;
}

html.dark .span-duration {
  color: #91a4b3;
}

@media (max-width: 768px) {
  .span-row {
    grid-template-columns: 1fr;
  }

  .span-duration {
    text-align: left;
  }
}
</style>
