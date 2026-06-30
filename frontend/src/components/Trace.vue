<template>
  <div class="trace-console">
    <header class="trace-hero">
      <div class="trace-hero-main">
        <div class="trace-hero-title">
          <div class="trace-core" :class="{ 'has-error': selectedTrace && hasError(selectedTrace) }">
            <el-icon><DataAnalysis /></el-icon>
          </div>
          <div class="trace-hero-copy">
            <p>TRACE CONSOLE</p>
            <h3>Agent 观测中心</h3>
            <span>会话记录、Trace 队列、Span 瀑布与错误上下文统一查看</span>
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

    <div class="trace-workbench">
      <main class="trace-canvas">
        <div v-if="!selectedTrace" class="trace-empty-stage">
          <div class="empty-observe">
            <el-icon><Aim /></el-icon>
            <strong>选择一次 Agent Run</strong>
            <span>从左侧队列进入 Trace，可查看 Span 瀑布、树状关系和属性详情。</span>
          </div>
        </div>

        <div v-else class="trace-detail-shell">
          <section class="trace-detail-main">
            <div class="trace-run-header">
              <div class="trace-run-title">
                <div class="trace-run-heading">
                  <span class="trace-status-dot large" :class="statusClass(selectedTrace.status)" />
                  <div>
                    <h4 :title="selectedTrace.name">
                      {{ selectedTrace.name }}
                    </h4>
                  </div>
                  <el-tag :type="tagType(selectedTrace.status)" effect="light" size="small">{{ selectedTrace.status }}</el-tag>
                </div>
                <p class="trace-id-line">{{ selectedTrace.trace_id }}</p>
              </div>

              <div class="trace-copy-actions">
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

              <div class="trace-fact-grid">
                <button
                  v-for="fact in selectedTraceFacts"
                  :key="fact.label"
                  type="button"
                  class="trace-fact-card"
                  @click="copyText(fact.value)"
                >
                  <span>{{ fact.label }}</span>
                  <strong class="trace-fact-value" :title="fact.value">{{ fact.displayValue }}</strong>
                </button>
              </div>
            </div>

            <div class="trace-panel-scroll">
              <section class="trace-panel trace-waterfall-panel">
                <div class="trace-panel-header">
                  <div>
                    <p>Span Waterfall</p>
                    <span>按 Trace 时间线定位调用层级和耗时分布</span>
                  </div>
                  <strong>{{ spans.length }} spans</strong>
                </div>

                <div v-if="spans.length" class="trace-waterfall-list">
                  <button
                    v-for="span in spans"
                    :key="span.span_id"
                    type="button"
                    class="trace-waterfall-row"
                    :class="{ active: selectedSpan?.span_id === span.span_id, error: span.status_code === 'ERROR' }"
                    @click="selectedSpan = span"
                  >
                    <div class="trace-span-name">
                      <div>
                        <span class="trace-status-dot" :class="statusClass(span.status_code)" />
                        <strong :title="span.name">{{ span.name }}</strong>
                      </div>
                      <span>{{ span.kind || 'span' }} · {{ compactId(span.span_id) }}</span>
                    </div>
                    <div class="trace-timeline">
                      <div class="trace-timeline-track">
                        <span class="trace-timeline-bar" :class="{ error: span.status_code === 'ERROR' }" :style="spanTimelineStyle(span)" />
                      </div>
                    </div>
                    <div class="span-duration">
                      <strong>{{ formatDuration(span.duration_ms) }}</strong>
                      <small>{{ spanOffset(span) }}</small>
                    </div>
                  </button>
                </div>

                <div v-else class="empty-observe">
                  <el-icon><Connection /></el-icon>
                  <strong>暂无 spans</strong>
                  <span>该 Trace 可能尚未写入 Span 数据，或当前查询未命中明细。</span>
                </div>
              </section>

              <section class="trace-panel">
                <div class="trace-panel-header">
                  <div>
                    <p>Span Tree</p>
                    <span>点击节点定位属性详情</span>
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
                    <div class="trace-tree-node">
                      <span class="trace-status-dot" :class="statusClass(data.span.status_code)" />
                      <strong :title="data.span.name">{{ data.span.name }}</strong>
                      <small>{{ formatDuration(data.span.duration_ms) }}</small>
                    </div>
                  </template>
                </el-tree>

                <div v-else class="empty-observe">
                  <el-icon><Connection /></el-icon>
                  <strong>暂无树状关系</strong>
                  <span>该 Trace 没有可展示的父子 Span 关系。</span>
                </div>
              </section>
            </div>
          </section>

          <aside class="trace-diagnostics">
            <div class="trace-panel">
              <div class="trace-panel-title">
                <el-icon><Cpu /></el-icon>
                <span>Span 诊断</span>
              </div>

              <div v-if="!selectedSpan" class="empty-observe">
                <el-icon><Aim /></el-icon>
                <strong>点击 Span 查看详情</strong>
                <span>这里会展示状态、时序和 attributes。</span>
              </div>

              <div v-else class="trace-diagnostic-body">
                <div class="trace-selected-span">
                  <div>
                    <span>名称</span>
                    <strong>{{ selectedSpan.name }}</strong>
                    <em>{{ selectedSpan.kind || 'span' }}</em>
                  </div>
                  <el-tag :type="tagType(selectedSpan.status_code)" effect="light" size="small">{{ selectedSpan.status_code }}</el-tag>
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
                    <strong :title="selectedSpan.parent_span_id || '-'">{{ compactId(selectedSpan.parent_span_id) }}</strong>
                  </div>
                  <div class="trace-detail-metric">
                    <span>Events</span>
                    <strong>{{ selectedSpan.events?.length ?? 0 }}</strong>
                  </div>
                </div>

                <div v-if="selectedSpan.status_message" class="trace-error-box">
                  <span>错误信息</span>
                  <strong>{{ selectedSpan.status_message }}</strong>
                </div>

                <div>
                  <div class="trace-json-head">
                    <span>Attributes</span>
                    <el-button size="small" plain class="cursor-pointer" :disabled="!selectedSpan" @click="copySpanJson">
                      复制 JSON
                    </el-button>
                  </div>
                  <pre class="trace-json">{{ prettyJson(selectedSpan.attributes) }}</pre>
                </div>
              </div>
            </div>

            <el-alert v-if="apiError" class="trace-alert" type="error" :title="apiError" show-icon />
          </aside>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue"
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
const props = defineProps<{
  selectedTraceId?: string | null
}>()

const limit = ref(20)
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

const selectedTraceFacts = computed(() => {
  const trace = selectedTrace.value
  if (!trace) return []
  return [
    { label: "Session", value: trace.session_id || "-", displayValue: compactId(trace.session_id) },
    { label: "Run", value: trace.run_id || "-", displayValue: compactId(trace.run_id) },
    { label: "Agent", value: trace.agent_id || trace.team_id || "-", displayValue: compactId(trace.agent_id || trace.team_id) },
    { label: "Workflow", value: trace.workflow_id || "-", displayValue: compactId(trace.workflow_id) },
  ]
})

const selectedTraceStartMs = computed(() => toMs(selectedTrace.value?.start_time))
const selectedTraceDurationMs = computed(() => Math.max(Number(selectedTrace.value?.duration_ms || 0), 1))
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

const scrollDetailIntoView = () => {
  if (!window.matchMedia("(max-width: 980px)").matches) return
  requestAnimationFrame(() => {
    document.querySelector<HTMLElement>(".trace-canvas")?.scrollIntoView({ block: "start", behavior: "smooth" })
  })
}

const refresh = async () => {
  selectedTrace.value = null
  selectedSpan.value = null
  spans.value = []
  tree.value = []

  const [start_time, end_time] = filters.timeRange || ["", ""]
  const resp = await listTraces({
    page: 1,
    limit: limit.value,
    status: filters.status || "",
    session_id: filters.session_id.trim() || undefined,
    start_time: start_time || undefined,
    end_time: end_time || undefined,
  })

  traceItems.value = resp.items || []
  if (props.selectedTraceId) {
    await selectTraceById(props.selectedTraceId)
  }
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

const selectTraceById = async (traceId: string | null | undefined) => {
  const id = (traceId || "").trim()
  if (!id || selectedTrace.value?.trace_id === id) return
  loadingDetail.value = true
  try {
    const resp = await getTrace(id)
    selectedTrace.value = resp.trace
    spans.value = resp.spans || []
    tree.value = resp.tree || []
    selectedSpan.value = null
    scrollDetailIntoView()
  } finally {
    loadingDetail.value = false
  }
}

const onSpanNodeClick = (node: SpanTreeNode) => {
  selectedSpan.value = node.span
}

const resetFilters = async () => {
  filters.session_id = ""
  filters.status = ""
  filters.timeRange = null
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
  }
)

watch(
  () => props.selectedTraceId,
  (traceId) => {
    void selectTraceById(traceId)
  }
)

const handleExternalTraceSelect = (event: Event) => {
  const detail = (event as CustomEvent<{ traceId?: string }>).detail
  void selectTraceById(detail?.traceId)
}

onMounted(async () => {
  window.addEventListener("agno-aios-trace-select", handleExternalTraceSelect)
  try {
    await refresh()
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : "加载 traces 失败")
  }
})

onUnmounted(() => {
  window.removeEventListener("agno-aios-trace-select", handleExternalTraceSelect)
})
</script>

<style>
.trace-console {
  --trace-bg: #eef3f7;
  --trace-panel: #ffffff;
  --trace-panel-soft: #f7fafc;
  --trace-border: #cfd9e3;
  --trace-border-strong: #9fb0bf;
  --trace-text: #14202a;
  --trace-muted: #637484;
  --trace-muted-soft: #8b9ba8;
  --trace-blue: #147fa2;
  --trace-blue-soft: #e5f5fb;
  --trace-red: #d34a42;
  --trace-yellow: #c78624;
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  background: var(--trace-bg);
  color: var(--trace-text);
  font-family: "Inter", "Fira Sans", "Microsoft YaHei", ui-sans-serif, system-ui, sans-serif;
}

.trace-console :where(button, div, section, aside, main, p, strong, span, small, pre) {
  min-width: 0;
}

.trace-hero {
  border-bottom: 1px solid var(--trace-border);
  background: color-mix(in srgb, var(--trace-panel) 92%, transparent);
  padding: 16px;
}

.trace-hero-main,
.trace-run-header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.trace-hero-title,
.trace-run-heading,
.trace-panel-title,
.trace-selected-span {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.trace-core {
  display: grid;
  flex: 0 0 auto;
  width: 38px;
  height: 38px;
  place-items: center;
  border: 1px solid rgba(20, 127, 162, 0.3);
  border-radius: 8px;
  background: var(--trace-blue-soft);
  color: var(--trace-blue);
}

.trace-core.has-error {
  border-color: rgba(211, 74, 66, 0.36);
  background: #fff0ed;
  color: var(--trace-red);
}

.trace-hero-copy p,
.trace-panel-header p {
  margin: 0;
  color: var(--trace-muted);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
}

.trace-hero-copy h3,
.trace-run-heading h4 {
  margin: 2px 0 0;
  color: var(--trace-text);
  font-size: 15px;
  font-weight: 800;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.trace-hero-copy span,
.trace-panel-header span {
  display: block;
  margin-top: 4px;
  color: var(--trace-muted);
  font-size: 12px;
  line-height: 1.45;
}

.trace-filter-bar {
  display: flex;
  flex: 1 1 520px;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.trace-filter-input,
.trace-filter-select {
  width: min(180px, 100%);
}

.trace-date-picker {
  width: min(360px, 100%) !important;
}

.trace-workbench {
  display: block;
  min-height: 0;
  flex: 1;
  overflow: hidden;
}

.trace-detail-main,
.trace-diagnostics,
.trace-canvas {
  min-height: 0;
  overflow: hidden;
}

.trace-diagnostic-body {
  display: grid;
  gap: 10px;
}

.trace-copy-actions,
.trace-json-head,
.trace-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.trace-id-line,
.span-duration,
.trace-tree-node small {
  font-family: "JetBrains Mono", "Fira Code", monospace;
}

.trace-timeline-track {
  position: relative;
  height: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: #dfe8ef;
}

.trace-timeline-track {
  height: 14px;
  box-shadow: inset 0 0 0 1px rgba(99, 116, 132, 0.08);
}

.trace-timeline-bar {
  position: absolute;
  inset: 0 auto 0 0;
  min-width: 6px;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--trace-blue), #51c7de);
}

.trace-timeline-bar.error {
  background: linear-gradient(90deg, var(--trace-red), var(--trace-yellow));
}

.trace-status-dot {
  display: inline-block;
  flex: 0 0 auto;
  width: 9px;
  height: 9px;
  margin-top: 4px;
  border-radius: 999px;
  background: var(--trace-muted-soft);
  box-shadow: 0 0 0 3px rgba(139, 155, 168, 0.12);
}

.trace-status-dot.large {
  width: 11px;
  height: 11px;
  margin-top: 5px;
}

.trace-status-dot.ok {
  background: #28a66f;
  box-shadow: 0 0 0 3px rgba(40, 166, 111, 0.14);
}

.trace-status-dot.error {
  background: var(--trace-red);
  box-shadow: 0 0 0 3px rgba(211, 74, 66, 0.16);
}

.trace-status-dot.unset {
  background: var(--trace-yellow);
  box-shadow: 0 0 0 3px rgba(199, 134, 36, 0.16);
}

.trace-canvas {
  background: var(--trace-bg);
}

.trace-empty-stage {
  display: grid;
  height: 100%;
  place-items: center;
  padding: 24px;
}

.trace-detail-shell {
  display: grid;
  height: 100%;
  min-height: 0;
  grid-template-columns: minmax(0, 1fr) 360px;
}

.trace-detail-main {
  display: flex;
  min-height: 0;
  flex-direction: column;
}

.trace-run-header {
  border-bottom: 1px solid var(--trace-border);
  background: color-mix(in srgb, var(--trace-panel) 88%, transparent);
  padding: 16px;
}

.trace-run-title {
  flex: 1 1 360px;
}

.trace-run-heading {
  align-items: center;
  flex-wrap: wrap;
}

.trace-run-heading h4 {
  display: -webkit-box;
  max-width: 100%;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.trace-run-heading > div {
  flex: 1 1 220px;
}

.trace-run-heading .el-tag {
  flex: 0 0 auto;
}

.trace-id-line {
  margin: 6px 0 0;
  color: var(--trace-muted);
  font-size: 11px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.trace-copy-actions {
  flex: 0 1 auto;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.trace-fact-grid {
  display: grid;
  flex: 1 0 100%;
  width: 100%;
  gap: 8px;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
}

.trace-fact-card {
  border: 1px solid var(--trace-border);
  border-radius: 8px;
  background: var(--trace-panel);
  padding: 10px;
  text-align: left;
  transition: border-color 0.2s ease, transform 0.2s ease;
}

.trace-fact-card:hover {
  border-color: rgba(20, 127, 162, 0.36);
  transform: translateY(-1px);
}

.trace-fact-card span,
.trace-detail-metric span,
.trace-selected-span span,
.trace-error-box span,
.trace-json-head span {
  display: block;
  color: var(--trace-muted);
  font-size: 11px;
  font-weight: 700;
  line-height: 1.3;
}

.trace-fact-value,
.trace-detail-metric strong {
  display: block;
  margin-top: 5px;
  overflow: hidden;
  color: var(--trace-text);
  font-size: 12px;
  font-weight: 800;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-selected-span strong,
.trace-error-box strong {
  display: block;
  margin-top: 5px;
  color: var(--trace-text);
  font-size: 12px;
  font-weight: 800;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.trace-panel-scroll {
  display: block;
  height: 0;
  min-height: 0;
  flex: 1 1 auto;
  overflow: auto;
  padding: 14px;
}

.trace-panel {
  border: 1px solid var(--trace-border);
  border-radius: 8px;
  background: var(--trace-panel);
  padding: 14px;
}

.trace-waterfall-panel {
  position: relative;
  overflow-x: auto;
  overflow-y: visible;
}

.trace-waterfall-panel::before {
  position: absolute;
  inset: 54px 14px auto;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(20, 127, 162, 0.36), transparent);
  content: "";
}

.trace-panel-header {
  position: relative;
  align-items: flex-start;
  margin-bottom: 12px;
}

.trace-panel-header strong {
  flex: 0 0 auto;
  color: var(--trace-muted);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
}

.trace-waterfall-list {
  display: grid;
  min-width: min(640px, 100%);
  gap: 8px;
}

.trace-waterfall-row {
  display: grid;
  width: 100%;
  grid-template-columns: minmax(190px, 260px) minmax(180px, 1fr) 92px;
  align-items: center;
  gap: 12px;
  border: 1px solid var(--trace-border);
  border-radius: 8px;
  background: var(--trace-panel-soft);
  padding: 10px;
  text-align: left;
}

.trace-waterfall-row:hover,
.trace-waterfall-row.active {
  border-color: rgba(20, 127, 162, 0.45);
  background: color-mix(in srgb, var(--trace-blue-soft) 44%, var(--trace-panel));
}

.trace-waterfall-row.error {
  border-color: rgba(211, 74, 66, 0.34);
}

.trace-span-name {
  display: grid;
  gap: 4px;
}

.trace-span-name > div {
  display: flex;
  align-items: flex-start;
  gap: 7px;
}

.trace-span-name strong,
.trace-tree-node strong {
  color: var(--trace-text);
  font-size: 12px;
  font-weight: 800;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-span-name > span {
  display: block;
  padding-left: 16px;
  color: var(--trace-muted);
  font-size: 10px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.trace-timeline {
  min-width: 0;
}

.span-duration {
  display: grid;
  justify-items: end;
  gap: 2px;
  color: var(--trace-muted);
  font-size: 11px;
  text-align: right;
}

.span-duration strong {
  color: var(--trace-text);
  font-size: 11px;
  line-height: 1.25;
}

.span-duration small {
  color: var(--trace-muted-soft);
  font-size: 10px;
}

.trace-tree {
  background: transparent;
}

.trace-tree-node {
  display: grid;
  width: 100%;
  grid-template-columns: 12px minmax(0, 1fr) auto;
  align-items: center;
  gap: 7px;
}

.trace-tree-node .trace-status-dot {
  margin-top: 0;
}

.trace-tree-node small {
  color: var(--trace-muted);
  font-size: 10px;
}

.trace-diagnostics {
  overflow-y: auto;
  border-left: 1px solid var(--trace-border);
  background: color-mix(in srgb, var(--trace-panel) 90%, transparent);
  padding: 14px;
}

.trace-diagnostics .trace-panel {
  display: grid;
  gap: 14px;
}

.trace-panel-title {
  align-items: center;
  color: var(--trace-text);
  font-size: 13px;
  font-weight: 800;
}

.trace-selected-span {
  justify-content: space-between;
}

.trace-selected-span strong {
  font-size: 13px;
}

.trace-selected-span em {
  display: block;
  margin-top: 3px;
  color: var(--trace-muted);
  font-size: 11px;
  font-style: normal;
}

.trace-detail-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.trace-detail-metric {
  border: 1px solid var(--trace-border);
  border-radius: 8px;
  background: var(--trace-panel-soft);
  padding: 10px;
}

.trace-error-box {
  border: 1px solid rgba(211, 74, 66, 0.28);
  border-radius: 8px;
  background: #fff0ed;
  padding: 10px;
}

.trace-error-box span,
.trace-error-box strong {
  color: var(--trace-red);
}

.trace-json-head {
  margin-bottom: 8px;
}

.trace-json {
  max-height: 340px;
  overflow: auto;
  margin: 0;
  border: 1px solid var(--trace-border);
  border-radius: 8px;
  background: #10151a;
  padding: 12px;
  color: #e9f5fb;
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.trace-alert {
  margin-top: 12px;
}

.empty-observe {
  display: grid;
  width: min(360px, 100%);
  place-items: center;
  justify-self: center;
  border: 1px dashed var(--trace-border);
  border-radius: 8px;
  background: var(--trace-panel);
  padding: 26px;
  text-align: center;
}

.trace-panel .empty-observe {
  margin-top: 12px;
}

.empty-observe .el-icon {
  color: var(--trace-blue);
  font-size: 26px;
}

.empty-observe strong {
  margin-top: 12px;
  color: var(--trace-text);
  font-size: 14px;
}

.empty-observe span {
  margin-top: 6px;
  color: var(--trace-muted);
  font-size: 12px;
  line-height: 1.55;
}

html.dark .trace-console {
  --trace-bg: #15161b;
  --trace-panel: #1c1d22;
  --trace-panel-soft: #17181d;
  --trace-border: #34363d;
  --trace-border-strong: #4c4e57;
  --trace-text: #f1f1ec;
  --trace-muted: #9a9ba3;
  --trace-muted-soft: #777982;
  --trace-blue: #6da8ff;
  --trace-blue-soft: rgba(109, 168, 255, 0.13);
  --trace-red: #ff6f63;
  --trace-yellow: #f0bd57;
}

html.dark .trace-core.has-error,
html.dark .trace-error-box {
  background: rgba(255, 111, 99, 0.12);
}

html.dark .trace-timeline-track {
  background: #2a2c33;
}

html.dark .trace-json {
  background: #101115;
  color: #e7e7e4;
}

html.dark .trace-waterfall-row:hover,
html.dark .trace-waterfall-row.active {
  background: #202127;
}

@media (max-width: 1480px) {
  .trace-detail-shell {
    display: block;
    overflow-y: auto;
  }

  .trace-detail-main {
    display: block;
    overflow: visible;
  }

  .trace-panel-scroll {
    overflow: visible;
  }

  .trace-diagnostics {
    overflow: visible;
    border-top: 1px solid var(--trace-border);
    border-left: 0;
  }
}

@media (max-width: 1180px) {
  .trace-waterfall-row {
    grid-template-columns: 1fr;
  }

  .span-duration {
    justify-items: start;
    text-align: left;
  }
}

@media (max-width: 980px) {
  .trace-console {
    overflow-y: auto;
  }

  .trace-workbench {
    display: block;
    overflow: visible;
  }

  .trace-canvas {
    overflow: visible;
  }
}

@media (max-width: 768px) {
  .trace-hero,
  .trace-run-header,
  .trace-panel-scroll,
  .trace-diagnostics {
    padding: 12px;
  }

  .trace-fact-grid,
  .trace-detail-grid {
    grid-template-columns: 1fr;
  }

  .trace-filter-bar,
  .trace-copy-actions {
    justify-content: flex-start;
  }

  .trace-filter-input,
  .trace-filter-select,
  .trace-date-picker {
    width: 100% !important;
  }

}
</style>
