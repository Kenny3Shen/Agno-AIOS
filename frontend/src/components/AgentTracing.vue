<template>
  <div class="trace-console flex h-full min-h-0 flex-col overflow-hidden bg-[#F5F7FA] text-[#15202B] dark:bg-[#071014] dark:text-[#DCE7EF]">
    <header class="trace-hero border-b border-[#D8E0E7] bg-white/90 px-4 py-4 backdrop-blur dark:border-[#22313A] dark:bg-[#0A151B]/90">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div class="flex items-center gap-3">
          <div class="trace-core" :class="{ 'has-error': traceHealth.errors > 0 }">
            <el-icon><DataAnalysis /></el-icon>
          </div>
          <div>
            <h3 class="text-sm font-semibold text-[#15202B] dark:text-white">Agent 观测中心</h3>
            <p class="mt-1 text-xs text-[#6B7C8A] dark:text-[#91A4B3]">
              会话记录、Trace 队列、Span 瀑布与错误上下文统一查看
            </p>
          </div>
        </div>

        <div class="trace-filter-bar">
          <el-input
            v-model="filters.session_id"
            size="small"
            clearable
            placeholder="session_id"
            class="trace-filter-input"
          />
          <el-select v-model="filters.status" size="small" clearable placeholder="状态" class="trace-filter-select">
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
          <el-button size="small" plain class="cursor-pointer" :disabled="loading" @click="resetFilters">
            重置
          </el-button>
          <el-tooltip content="刷新 Trace 队列" placement="bottom">
            <el-button size="small" type="primary" :loading="loading" @click="refresh" class="cursor-pointer">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </el-tooltip>
        </div>
      </div>
    </header>

    <section class="trace-summary-grid border-b border-[#D8E0E7] bg-[#EFF5F9] px-4 py-3 dark:border-[#22313A] dark:bg-[#081319]">
      <article v-for="metric in traceMetrics" :key="metric.label" class="trace-metric">
        <div class="flex items-center justify-between gap-2">
          <span>{{ metric.label }}</span>
          <span class="trace-metric-dot" />
        </div>
        <strong>{{ metric.value }}</strong>
        <em>{{ metric.hint }}</em>
      </article>
    </section>

    <div class="grid min-h-0 flex-1 grid-cols-1 grid-rows-[280px_minmax(0,1fr)] lg:grid-cols-[380px_minmax(0,1fr)] lg:grid-rows-1">
      <aside class="flex min-h-0 flex-col border-r border-[#D8E0E7] bg-white/90 dark:border-[#22313A] dark:bg-[#0A151B]">
        <div class="flex items-center justify-between gap-3 border-b border-[#D8E0E7] px-4 py-3 dark:border-[#22313A]">
          <div class="min-w-0">
            <div class="text-xs font-semibold uppercase tracking-wide text-[#6B7C8A] dark:text-[#758998]">Trace Queue</div>
            <div class="mt-0.5 text-[11px] text-[#91A0AD]">
              共 {{ totalCount }} 条 · page {{ page }} · {{ traceItems.length }} visible
            </div>
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

        <div class="min-h-0 flex-1 overflow-y-auto p-2.5">
          <button
            v-for="trace in traceItems"
            :key="trace.trace_id"
            type="button"
            class="trace-card trace-list-item"
            :class="{ active: selectedTrace?.trace_id === trace.trace_id, error: hasError(trace) }"
            @click="onTraceSelect(trace)"
          >
            <span class="trace-status-dot" :class="statusClass(trace.status)" />
            <span class="min-w-0 flex-1">
              <span class="flex items-center justify-between gap-2">
                <strong class="truncate" :title="trace.name">{{ trace.name }}</strong>
                <el-tag :type="tagType(trace.status)" effect="light" size="small">{{ trace.status }}</el-tag>
              </span>

              <span class="mt-1 grid gap-1">
                <span class="flex flex-wrap gap-1.5">
                  <span class="trace-chip mono" :title="trace.session_id || '未提供 session_id'">
                    会话 {{ compactId(trace.session_id) }}
                  </span>
                  <span class="trace-chip mono" :title="trace.run_id || '未提供 run_id'">
                    运行 {{ compactId(trace.run_id) }}
                  </span>
                </span>
                <span class="flex flex-wrap gap-1.5">
                  <span class="trace-chip muted">{{ formatTimestamp(trace.start_time) }}</span>
                  <span class="trace-chip muted">Agent {{ compactId(trace.agent_id || trace.team_id || trace.workflow_id) }}</span>
                </span>
              </span>

              <span class="mt-2 grid grid-cols-[88px_minmax(0,1fr)] items-center gap-2 text-[11px]">
                <span class="font-mono text-[#526170] dark:text-[#91A4B3]">{{ formatDuration(trace.duration_ms) }}</span>
                <span class="trace-mini-track">
                  <span class="trace-mini-bar" :class="{ error: hasError(trace) }" :style="{ width: durationWidth(trace.duration_ms) }" />
                </span>
                <span class="text-[#8A99A6] dark:text-[#758998]">Spans {{ trace.total_spans ?? 0 }}</span>
                <span class="text-[#8A99A6] dark:text-[#758998]">Errors {{ trace.error_count ?? 0 }}</span>
              </span>
            </span>
          </button>

          <div v-if="!traceItems.length && !loading" class="empty-observe">
            <el-icon><Aim /></el-icon>
            <strong>当前筛选条件下暂无 Trace</strong>
            <span>放宽 session、状态或时间范围后重新查询。</span>
          </div>
        </div>
      </aside>

      <main class="min-h-0 overflow-hidden">
        <div v-if="!selectedTrace" class="grid h-full place-items-center p-6">
          <div class="empty-observe">
            <el-icon><Aim /></el-icon>
            <strong>选择一次 Agent Run</strong>
            <span>从左侧队列进入 Trace，可查看 Span 瀑布、树状关系和属性详情。</span>
          </div>
        </div>

        <div v-else class="grid h-full min-h-0 grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px]">
          <section class="flex min-h-0 flex-col overflow-hidden">
            <div class="border-b border-[#D8E0E7] bg-white/80 px-4 py-4 dark:border-[#22313A] dark:bg-[#0A151B]/80">
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
                  <el-button size="small" plain class="cursor-pointer" @click="copySelectedTraceId" :disabled="!selectedTrace">
                    trace_id
                  </el-button>
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

              <div class="trace-fact-grid mt-4">
                <button
                  v-for="fact in selectedTraceFacts"
                  :key="fact.label"
                  type="button"
                  class="trace-fact-card"
                  @click="copyText(fact.value)"
                >
                  <span>{{ fact.label }}</span>
                  <strong class="truncate" :title="fact.value">{{ fact.value }}</strong>
                </button>
              </div>
            </div>

            <div class="min-h-0 flex-1 overflow-y-auto p-4">
              <div class="space-y-4">
                <section class="trace-panel">
                  <div class="flex items-center justify-between gap-3">
                    <div>
                      <div class="text-xs font-semibold uppercase tracking-wide text-[#6B7C8A] dark:text-[#758998]">Span Waterfall</div>
                      <p class="mt-1 text-[11px] text-[#91A0AD]">按 Trace 时间线定位调用层级和耗时分布</p>
                    </div>
                    <div class="font-mono text-[11px] text-[#91A0AD]">{{ spans.length }} spans</div>
                  </div>

                  <div v-if="spans.length" class="mt-4 space-y-2">
                    <button
                      v-for="span in spans"
                      :key="span.span_id"
                      type="button"
                      class="span-row trace-span-row"
                      :class="{ active: selectedSpan?.span_id === span.span_id, error: span.status_code === 'ERROR' }"
                      @click="selectedSpan = span"
                    >
                      <span class="span-meta">
                        <span class="trace-status-dot" :class="statusClass(span.status_code)" />
                        <strong class="truncate" :title="span.name">{{ span.name }}</strong>
                        <em>{{ span.kind || 'span' }}</em>
                      </span>
                      <span class="trace-timeline">
                        <span class="trace-timeline-track">
                          <span class="trace-timeline-bar" :class="{ error: span.status_code === 'ERROR' }" :style="spanTimelineStyle(span)" />
                        </span>
                      </span>
                      <span class="span-duration">
                        <span>{{ formatDuration(span.duration_ms) }}</span>
                        <small>{{ spanOffset(span) }}</small>
                      </span>
                    </button>
                  </div>

                  <div v-else class="empty-observe mt-4">
                    <el-icon><Connection /></el-icon>
                    <strong>暂无 spans</strong>
                    <span>该 Trace 可能尚未写入 Span 数据，或当前查询未命中明细。</span>
                  </div>
                </section>

                <section class="trace-panel">
                  <div class="mb-3 flex items-center justify-between gap-3">
                    <div>
                      <div class="text-xs font-semibold uppercase tracking-wide text-[#6B7C8A] dark:text-[#758998]">Span Tree</div>
                      <p class="mt-1 text-[11px] text-[#91A0AD]">点击节点定位属性详情</p>
                    </div>
                  </div>

                  <el-tree
                    v-if="tree.length"
                    :data="tree"
                    node-key="span.span_id"
                    :expand-on-click-node="false"
                    default-expand-all
                    class="trace-tree"
                    @node-click="onSpanNodeClick"
                  >
                    <template #default="{ data }">
                      <div class="flex min-w-0 items-center gap-2">
                        <span class="trace-status-dot" :class="statusClass(data.span.status_code)" />
                        <span class="truncate text-xs text-[#15202B] dark:text-[#DCE7EF]" :title="data.span.name">{{ data.span.name }}</span>
                        <span class="font-mono text-[10px] text-[#7D8D9A] dark:text-[#91A4B3]">{{ formatDuration(data.span.duration_ms) }}</span>
                      </div>
                    </template>
                  </el-tree>
                </section>
              </div>
            </div>
          </section>

          <aside class="min-h-0 overflow-y-auto border-l border-[#D8E0E7] bg-white/90 p-4 dark:border-[#22313A] dark:bg-[#0A151B]">
            <div class="trace-panel">
              <div class="trace-panel-title">
                <el-icon><Cpu /></el-icon>
                Span 诊断
              </div>

              <div v-if="!selectedSpan" class="empty-observe mt-4">
                <el-icon><Aim /></el-icon>
                <strong>点击 Span 查看详情</strong>
                <span>这里会展示状态、时序和 attributes。</span>
              </div>

              <div v-else class="mt-4 space-y-4">
                <div>
                  <div class="flex items-center justify-between gap-2">
                    <div class="min-w-0">
                      <div class="text-[11px] text-[#6B7C8A] dark:text-[#758998]">名称</div>
                      <div class="mt-1 break-words text-sm font-semibold text-[#15202B] dark:text-white">{{ selectedSpan.name }}</div>
                    </div>
                    <el-tag :type="tagType(selectedSpan.status_code)" effect="light" size="small">{{ selectedSpan.status_code }}</el-tag>
                  </div>
                  <p class="mt-1 text-[11px] text-[#91A0AD]">{{ selectedSpan.kind || 'span' }}</p>
                </div>

                <div class="trace-detail-grid">
                  <div class="trace-detail-metric">
                    <span>耗时</span>
                    <strong>{{ formatDuration(selectedSpan.duration_ms) }}</strong>
                  </div>
                  <div class="trace-detail-metric">
                    <span>开始偏移</span>
                    <strong>{{ spanOffset(selectedSpan) }}</strong>
                  </div>
                  <div class="trace-detail-metric">
                    <span>Parent</span>
                    <strong class="truncate">{{ selectedSpan.parent_span_id || "-" }}</strong>
                  </div>
                  <div class="trace-detail-metric">
                    <span>Events</span>
                    <strong>{{ selectedSpan.events?.length ?? 0 }}</strong>
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

            <el-alert v-if="apiError" class="mt-4" type="error" :title="apiError" show-icon />
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
  Connection,
  Cpu,
  DataAnalysis,
  Refresh,
} from "@element-plus/icons-vue"
import { useTracingApi } from "../composables/useApi"
import type { SpanItem, SpanTreeNode, TraceItem, TraceStatus } from "../types"

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
  { label: "Errors", value: traceHealth.value.errors, hint: "错误 Span" },
  { label: "Avg Latency", value: formatDuration(traceHealth.value.avgDuration), hint: "本页平均耗时" },
])

const selectedTraceFacts = computed(() => {
  const trace = selectedTrace.value
  if (!trace) return []
  return [
    { label: "Session", value: trace.session_id || "-" },
    { label: "Run", value: trace.run_id || "-" },
    { label: "Agent", value: trace.agent_id || trace.team_id || "-" },
    { label: "Workflow", value: trace.workflow_id || "-" },
  ]
})

const selectedTraceStartMs = computed(() => toMs(selectedTrace.value?.start_time))
const selectedTraceDurationMs = computed(() => Math.max(Number(selectedTrace.value?.duration_ms || 0), 1))
const maxListDuration = computed(() => Math.max(...traceItems.value.map((trace) => Number(trace.duration_ms || 0)), 1))

const fmt = (iso: string) => {
  if (!iso) return ""
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })
}

const formatTimestamp = (iso?: string | null) => {
  if (!iso) return "-"
  return fmt(iso)
}

const compactId = (value?: string | null) => {
  const text = (value || "").trim()
  if (!text) return "-"
  if (text.length <= 18) return text
  return `${text.slice(0, 8)}...${text.slice(-4)}`
}

const toMs = (value?: string | null) => {
  if (!value) return null
  const ms = new Date(value).getTime()
  return Number.isNaN(ms) ? null : ms
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

const durationWidth = (durationMs: number | string | null | undefined) => {
  const width = Math.max((Number(durationMs || 0) / maxListDuration.value) * 100, 6)
  return `${Math.min(width, 100)}%`
}

const spanTimelineStyle = (span: SpanItem) => {
  const traceStart = selectedTraceStartMs.value
  const traceDuration = selectedTraceDurationMs.value
  if (traceStart == null || !traceDuration) {
    return { left: "0%", width: "8%" }
  }

  const start = toMs(span.start_time)
  const end = toMs(span.end_time) ?? start
  if (start == null || end == null) {
    return { left: "0%", width: "8%" }
  }

  const offset = Math.max(0, ((start - traceStart) / traceDuration) * 100)
  const width = Math.max(2, ((end - start) / traceDuration) * 100)
  const clampedLeft = Math.min(offset, 96)
  const clampedWidth = Math.min(width, 100 - clampedLeft)
  return {
    left: `${clampedLeft}%`,
    width: `${Math.max(clampedWidth, 4)}%`,
  }
}

const spanOffset = (span: SpanItem) => {
  const traceStart = selectedTraceStartMs.value
  const start = toMs(span.start_time)
  if (traceStart == null || start == null) return "-"
  const diff = Math.max(0, start - traceStart)
  return `+${formatDuration(diff)}`
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

const resetFilters = async () => {
  filters.session_id = ""
  filters.status = ""
  filters.timeRange = null
  page.value = 1
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

const hasError = (trace: TraceItem) => {
  return trace.status === "ERROR" || Number(trace.error_count || 0) > 0
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
    ElMessage.error(e instanceof Error ? e.message : "加载 traces 失败")
  }
})
</script>

<style>
.trace-console {
  font-family: "Fira Sans", "Microsoft YaHei", sans-serif;
}

.trace-hero {
  position: relative;
}

.trace-filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.trace-filter-input,
.trace-filter-select {
  width: 180px;
}

.trace-summary-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.trace-metric-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: linear-gradient(135deg, #0891b2, #22d3ee);
}

.trace-list-item {
  margin-bottom: 8px;
  align-items: flex-start;
}

.trace-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  border: 1px solid #d8e0e7;
  border-radius: 999px;
  padding: 2px 8px;
  background: #f8fafc;
  color: #334155;
  font-size: 10px;
}

.trace-chip.muted {
  color: #526170;
}

.trace-chip.mono {
  font-family: "Fira Code", monospace;
}

.trace-fact-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.trace-fact-card {
  border: 1px solid #d8e0e7;
  border-radius: 10px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbfd 100%);
  padding: 10px;
  text-align: left;
  transition: border-color 0.2s ease, transform 0.2s ease, background-color 0.2s ease;
  cursor: pointer;
}

.trace-fact-card:hover {
  border-color: rgba(8, 145, 178, 0.35);
  transform: translateY(-1px);
}

.trace-fact-card span {
  display: block;
  color: #6b7c8a;
  font-size: 11px;
}

.trace-fact-card strong {
  display: block;
  margin-top: 4px;
  color: #15202b;
  font-size: 12px;
  font-weight: 700;
}

.trace-panel {
  border: 1px solid #d8e0e7;
  border-radius: 14px;
  background: #ffffff;
  padding: 14px;
}

.trace-panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #15202b;
  font-size: 13px;
  font-weight: 700;
}

.trace-span-row {
  grid-template-columns: minmax(170px, 260px) minmax(0, 1fr) 92px;
  align-items: center;
}

.trace-timeline {
  min-width: 0;
}

.trace-timeline-track,
.trace-mini-track {
  display: block;
  position: relative;
  height: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: #e6edf3;
}

.trace-timeline-bar,
.trace-mini-bar {
  display: block;
  position: absolute;
  inset: 0 auto 0 0;
  height: 100%;
  min-width: 6px;
  border-radius: inherit;
  background: linear-gradient(90deg, #0891b2, #22d3ee);
}

.trace-timeline-bar.error,
.trace-mini-bar.error {
  background: linear-gradient(90deg, #f06a6a, #f6c343);
}

.trace-span-row .span-duration {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  color: #526170;
  font-family: "Fira Code", monospace;
  font-size: 11px;
  text-align: right;
}

.trace-span-row .span-duration small {
  color: #91a0ad;
  font-size: 10px;
}

.trace-detail-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.trace-detail-metric {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
  border: 1px solid #d8e0e7;
  border-radius: 10px;
  background: #f8fbfd;
  padding: 10px 12px;
}

.trace-detail-metric span {
  color: #6b7c8a;
  font-size: 11px;
  line-height: 1.2;
}

.trace-detail-metric strong {
  min-width: 0;
  color: #15202b;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.35;
}

.trace-span-row .span-meta {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 6px;
}

.trace-span-row .span-meta strong {
  min-width: 0;
}

.trace-json {
  max-height: 340px;
  overflow: auto;
  margin: 0;
  border: 1px solid #d8e0e7;
  border-radius: 10px;
  background: #f8fbfd;
  padding: 12px;
  color: #15202b;
  font-family: "Fira Code", monospace;
  font-size: 11px;
  line-height: 1.65;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.trace-tree {
  background: transparent;
}

.empty-observe {
  display: grid;
  width: min(360px, 100%);
  place-items: center;
  border: 1px dashed #d8e0e7;
  border-radius: 14px;
  background: #ffffff;
  padding: 28px;
  text-align: center;
}

.empty-observe .el-icon {
  color: #0891b2;
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

html.dark .trace-chip {
  border-color: #22313a;
  background: #0f1b22;
  color: #dce7ef;
}

html.dark .trace-fact-card,
html.dark .trace-panel,
html.dark .empty-observe {
  border-color: #22313a;
  background: #0f1b22;
}

html.dark .trace-detail-metric {
  border-color: #22313a;
  background: #0b151c;
}

html.dark .trace-detail-metric span {
  color: #758998;
}

html.dark .trace-detail-metric strong {
  color: #dce7ef;
}

html.dark .trace-json {
  border-color: #22313a;
  background: #0b151c;
  color: #dce7ef;
}

html.dark .trace-fact-card span,
html.dark .empty-observe span,
html.dark .trace-metric em,
html.dark .trace-chip.muted,
html.dark .trace-span-row .span-duration small {
  color: #758998;
}

html.dark .trace-fact-card strong,
html.dark .trace-panel-title,
html.dark .empty-observe strong,
html.dark .trace-span-row .span-meta strong,
html.dark .trace-span-row .span-duration {
  color: #dce7ef;
}

html.dark .trace-timeline-track,
html.dark .trace-mini-track {
  background: #22313a;
}

html.dark .trace-fact-card:hover {
  border-color: rgba(139, 217, 255, 0.35);
  background: #102638;
}

@media (max-width: 768px) {
  .trace-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .trace-fact-grid {
    grid-template-columns: 1fr;
  }

  .trace-span-row {
    grid-template-columns: 1fr;
  }

  .trace-span-row .span-duration {
    align-items: flex-start;
    text-align: left;
  }
}
</style>
