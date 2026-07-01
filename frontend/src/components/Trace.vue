<template>
  <div class="trace-console">
    <header class="trace-hero">
      <div class="trace-hero-main">
        <div class="trace-hero-title">
          <div class="trace-core" :class="{ 'has-error': selectedTrace && hasError(selectedTrace) }">
            <el-icon><DataAnalysis /></el-icon>
          </div>
          <div class="trace-hero-copy">
            <h3>Trace</h3>
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

        <div v-else class="trace-detail-shell trace-inspector-shell">
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
            </div>

            <div class="trace-copy-actions">
              <el-button size="small" plain class="cursor-pointer" @click="refreshSelectedTrace" :loading="loadingDetail">
                重新拉取
              </el-button>
            </div>

            <div class="trace-evidence-strip" aria-label="Trace metadata">
              <button
                v-for="item in selectedTraceEvidence"
                :key="item.label"
                type="button"
                class="trace-evidence-chip"
                :disabled="!item.copyable"
                @click="copyText(item.value)"
              >
                <span>{{ item.label }}:</span>
                <strong :title="item.value">{{ item.displayValue }}</strong>
                <el-icon v-if="item.copyable"><CopyDocument /></el-icon>
              </button>
            </div>
          </div>

          <div class="trace-content-layout">
            <aside class="trace-span-hierarchy">
              <div class="trace-panel-header">
                <div>
                  <p>Trace Hierarchy</p>
                  <span>按父子关系查看 Agent、LLM、Tool 与 Hook</span>
                </div>
                <strong>{{ spans.length }} spans</strong>
              </div>

              <el-tree
                v-if="tree.length"
                :data="tree"
                node-key="span.span_id"
                :expand-on-click-node="false"
                default-expand-all
                class="trace-tree trace-hierarchy-tree"
                @node-click="onSpanNodeClick"
              >
                <template #default="{ data }">
                  <button
                    type="button"
                    class="trace-tree-node trace-hierarchy-node"
                    :class="{ active: selectedSpan?.span_id === data.span.span_id, error: data.span.status_code === 'ERROR' }"
                    @click.stop="selectSpan(data.span)"
                  >
                    <span class="trace-status-dot" :class="statusClass(data.span.status_code)" />
                    <span class="trace-hierarchy-node-copy">
                      <strong :title="data.span.name">{{ data.span.name }}</strong>
                      <small>{{ data.span.kind || 'span' }} · {{ formatDuration(data.span.duration_ms) }}</small>
                    </span>
                  </button>
                </template>
              </el-tree>

              <div v-else-if="spans.length" class="trace-hierarchy-fallback">
                <button
                  v-for="span in spans"
                  :key="span.span_id"
                  type="button"
                  class="trace-tree-node trace-hierarchy-node"
                  :class="{ active: selectedSpan?.span_id === span.span_id, error: span.status_code === 'ERROR' }"
                  @click="selectSpan(span)"
                >
                  <span class="trace-status-dot" :class="statusClass(span.status_code)" />
                  <span class="trace-hierarchy-node-copy">
                    <strong :title="span.name">{{ span.name }}</strong>
                    <small>{{ span.kind || 'span' }} · {{ formatDuration(span.duration_ms) }}</small>
                  </span>
                </button>
              </div>

              <div v-else class="empty-observe">
                <el-icon><Connection /></el-icon>
                <strong>暂无 spans</strong>
                <span>该 Trace 可能尚未写入 Span 数据，或当前查询未命中明细。</span>
              </div>
            </aside>

            <section class="trace-content-detail">
              <div v-if="!selectedSpan" class="empty-observe">
                <el-icon><Aim /></el-icon>
                <strong>点击 Span 查看详情</strong>
                <span>这里会展示输入、输出、元数据与原始 attributes。</span>
              </div>

              <template v-else>
                <div class="trace-content-titlebar">
                  <div class="trace-selected-span">
                    <div class="trace-content-glyph" :class="{ error: selectedSpan.status_code === 'ERROR' }">
                      <el-icon><Cpu /></el-icon>
                    </div>
                    <div>
                      <strong>{{ selectedSpan.name }}</strong>
                      <em>{{ selectedSpan.kind || 'span' }}</em>
                    </div>
                  </div>
                  <div class="trace-content-badges">
                    <span>LATENCY {{ formatDuration(selectedSpan.duration_ms) }}</span>
                    <el-tag :type="tagType(selectedSpan.status_code)" effect="light" size="small">{{ selectedSpan.status_code }}</el-tag>
                  </div>
                </div>

                <div class="trace-content-tabs" role="tablist" aria-label="Span detail sections">
                  <button
                    type="button"
                    role="tab"
                    :aria-selected="activeDetailTab === 'info'"
                    :class="{ active: activeDetailTab === 'info' }"
                    @click="activeDetailTab = 'info'"
                  >
                    Info
                  </button>
                  <button
                    type="button"
                    role="tab"
                    :aria-selected="activeDetailTab === 'metadata'"
                    :class="{ active: activeDetailTab === 'metadata' }"
                    @click="activeDetailTab = 'metadata'"
                  >
                    Metadata
                  </button>
                </div>

                <div v-if="selectedSpan.status_message" class="trace-error-box">
                  <span>错误信息</span>
                  <strong>{{ selectedSpan.status_message }}</strong>
                </div>

                <template v-if="activeDetailTab === 'info'">
                  <section class="trace-io-section">
                    <div class="trace-io-head">
                      <span>Input</span>
                      <div>
                        <span class="trace-mode-chip" :class="{ active: parsedSpan.input.format === 'json' }">JSON</span>
                        <span class="trace-mode-chip" :class="{ active: parsedSpan.input.format === 'markdown' }">MARKDOWN</span>
                        <span class="trace-mode-chip" :class="{ active: parsedSpan.input.format === 'text' }">TEXT</span>
                      </div>
                    </div>
                    <pre
                      v-if="isJsonPayload(parsedSpan.input)"
                      class="trace-io-block trace-json-payload"
                      :class="{ empty: !parsedSpan.input.text }"
                    >{{ formatPayloadText(parsedSpan.input, "No input captured") }}</pre>
                    <div
                      v-else
                      class="trace-markdown-render trace-io-block"
                      :class="{ empty: !parsedSpan.input.text }"
                      v-html="renderPayloadMarkup(parsedSpan.input, 'No input captured')"
                    />
                  </section>

                  <section class="trace-io-section">
                    <div class="trace-io-head">
                      <span>Output</span>
                      <div>
                        <span class="trace-mode-chip" :class="{ active: parsedSpan.output.format === 'json' }">JSON</span>
                        <span class="trace-mode-chip" :class="{ active: parsedSpan.output.format === 'markdown' }">MARKDOWN</span>
                        <span class="trace-mode-chip" :class="{ active: parsedSpan.output.format === 'text' }">TEXT</span>
                      </div>
                    </div>
                    <pre
                      v-if="isJsonPayload(parsedSpan.output)"
                      class="trace-io-block trace-json-payload"
                      :class="{ empty: !parsedSpan.output.text }"
                    >{{ formatPayloadText(parsedSpan.output, "No output captured") }}</pre>
                    <div
                      v-else
                      class="trace-markdown-render trace-io-block"
                      :class="{ empty: !parsedSpan.output.text }"
                      v-html="renderPayloadMarkup(parsedSpan.output, 'No output captured')"
                    />
                  </section>
                </template>

                <template v-else>
                  <section class="trace-metadata-panel trace-metadata-ledger">
                    <div class="trace-json-head">
                      <span>Metadata</span>
                    </div>
                    <div class="trace-metadata-grid">
                      <div v-for="item in spanMetadataItems" :key="item.label" class="trace-metadata-item">
                        <span>{{ item.label }}</span>
                        <strong :title="item.value">{{ item.displayValue }}</strong>
                      </div>
                    </div>
                  </section>

                  <section v-if="parsedSpan.events.length" class="trace-events-panel">
                    <div class="trace-json-head">
                      <span>Events</span>
                    </div>
                    <article v-for="event in parsedSpan.events" :key="`${event.name}:${event.message}`" class="trace-event-row">
                      <strong>{{ event.name }}</strong>
                      <span>{{ event.message }}</span>
                    </article>
                  </section>

                  <div>
                    <div class="trace-json-head">
                      <span>Attributes</span>
                      <el-button size="small" plain class="cursor-pointer" :disabled="!selectedSpan" @click="copySpanJson">
                        复制 JSON
                      </el-button>
                    </div>
                    <pre class="trace-json">{{ prettyJson(selectedSpan.attributes) }}</pre>
                  </div>
                </template>
              </template>

              <el-alert v-if="apiError" class="trace-alert" type="error" :title="apiError" show-icon />
            </section>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue"
import { ElMessage } from "element-plus"
import MarkdownIt from "markdown-it"
import {
  Aim,
  Connection,
  CopyDocument,
  Cpu,
  DataAnalysis,
  Refresh,
} from "@element-plus/icons-vue"
import { useTracingApi } from "../composables/useApi"
import { copyToClipboard } from "../lib/clipboard"
import type { ParsedSpanPayload, SpanItem, SpanTreeNode, TraceItem, TraceStatus } from "../types"

const { loading, error, listTraces, getTrace } = useTracingApi()
const markdownRenderer = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})
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
const activeDetailTab = ref<"info" | "metadata">("info")

const loadingDetail = ref(false)
const apiError = computed(() => error.value)

const selectedTraceEvidence = computed(() => {
  const trace = selectedTrace.value
  if (!trace) return []
  const rows = [
    { label: "Created At", value: trace.created_at || trace.start_time || "-", displayValue: formatDateTime(trace.created_at || trace.start_time) },
    { label: "Trace ID", value: trace.trace_id || "-", displayValue: compactId(trace.trace_id) },
    { label: "Run ID", value: trace.run_id || "-", displayValue: compactId(trace.run_id) },
    { label: "Session ID", value: trace.session_id || "-", displayValue: compactId(trace.session_id) },
    { label: "Agent", value: trace.agent_id || trace.team_id || "-", displayValue: compactId(trace.agent_id || trace.team_id) },
    { label: "Workflow", value: trace.workflow_id || "-", displayValue: compactId(trace.workflow_id) },
  ]
  if (trace.user_id) {
    rows.push({ label: "User ID", value: trace.user_id, displayValue: compactId(trace.user_id) })
  }
  return rows.map((item) => ({ ...item, copyable: item.value !== "-" }))
})

const selectedTraceStartMs = computed(() => toMs(selectedTrace.value?.start_time))
const emptyParsedSpan = {
  input: { format: "empty", text: "", data: null },
  output: { format: "empty", text: "", data: null },
  metadata: {
    model: null,
    provider: null,
    tool: null,
    operation: null,
    tokens: {
      prompt: null,
      completion: null,
      total: null,
    },
  },
  events: [],
}
const parsedSpan = computed(() => selectedSpan.value?.parsed || emptyParsedSpan)
const parsedMetadata = computed(() => {
  const metadata = parsedSpan.value.metadata || emptyParsedSpan.metadata
  const tokens = metadata.tokens || {}
  return [
    { label: "Model", value: valueOrDash(metadata.model), displayValue: valueOrDash(metadata.model) },
    { label: "Provider", value: valueOrDash(metadata.provider), displayValue: valueOrDash(metadata.provider) },
    { label: "Tool", value: valueOrDash(metadata.tool), displayValue: valueOrDash(metadata.tool) },
    { label: "Operation", value: valueOrDash(metadata.operation), displayValue: valueOrDash(metadata.operation) },
    { label: "Prompt tokens", value: valueOrDash(tokens.prompt), displayValue: valueOrDash(tokens.prompt) },
    { label: "Completion tokens", value: valueOrDash(tokens.completion), displayValue: valueOrDash(tokens.completion) },
    { label: "Total tokens", value: valueOrDash(tokens.total), displayValue: valueOrDash(tokens.total) },
  ]
})

const spanMetadataItems = computed(() => {
  const span = selectedSpan.value
  if (!span) return []
  const eventCount = Math.max(parsedSpan.value.events?.length || 0, span.events?.length || 0)
  return [
    { label: "开始偏移", value: spanOffset(span), displayValue: spanOffset(span) },
    { label: "Parent", value: valueOrDash(span.parent_span_id), displayValue: compactId(span.parent_span_id) },
    { label: "Events", value: String(eventCount), displayValue: String(eventCount) },
    { label: "Span ID", value: valueOrDash(span.span_id), displayValue: compactId(span.span_id) },
    { label: "Kind", value: valueOrDash(span.kind), displayValue: valueOrDash(span.kind) },
    { label: "Status", value: valueOrDash(span.status_code), displayValue: valueOrDash(span.status_code) },
    { label: "Duration", value: formatDuration(span.duration_ms), displayValue: formatDuration(span.duration_ms) },
    { label: "Start Time", value: valueOrDash(span.start_time), displayValue: formatDateTime(span.start_time) },
    { label: "End Time", value: valueOrDash(span.end_time), displayValue: formatDateTime(span.end_time) },
    ...parsedMetadata.value,
  ]
})
const valueOrDash = (value: unknown) => {
  if (value === null || value === undefined || value === "") return "-"
  return String(value)
}
const renderMarkdown = (value: string) => {
  return markdownRenderer.render(value || "")
}

const isJsonPayload = (payload: ParsedSpanPayload) => {
  if (payload.format === "json" || payload.data !== null && payload.data !== undefined) return true
  const text = payload.text?.trim()
  if (!text || !["{", "["].includes(text[0])) return false
  try {
    JSON.parse(text)
    return true
  } catch {
    return false
  }
}

const formatPayloadText = (payload: ParsedSpanPayload, fallback: string) => {
  if (!payload.text) return fallback
  if (payload.data !== null && payload.data !== undefined) return prettyJson(payload.data)
  try {
    return JSON.stringify(JSON.parse(payload.text), null, 2)
  } catch {
    return payload.text
  }
}

const renderPayloadMarkup = (payload: ParsedSpanPayload, fallback: string) => {
  return renderMarkdown(payload.text || fallback)
}

const compactId = (value?: string | null) => {
  const text = (value || "").trim()
  if (!text) return "-"
  if (text.length <= 18) return text
  return `${text.slice(0, 8)}...${text.slice(-4)}`
}

const formatDateTime = (value?: string | null) => {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
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
    selectedSpan.value = firstAvailableSpan()
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
    selectedSpan.value = firstAvailableSpan()
    scrollDetailIntoView()
  } finally {
    loadingDetail.value = false
  }
}

const firstAvailableSpan = () => {
  return tree.value[0]?.span || spans.value[0] || null
}

const selectSpan = (span: SpanItem) => {
  selectedSpan.value = span
  activeDetailTab.value = "info"
}

const onSpanNodeClick = (node: SpanTreeNode) => {
  selectSpan(node.span)
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
  if (await copyToClipboard(t)) {
    ElMessage.success("已复制")
  } else {
    ElMessage.warning("复制失败")
  }
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
  --trace-bg: var(--ag-frame);
  --trace-panel: var(--ag-panel);
  --trace-panel-soft: var(--ag-panel-soft);
  --trace-border: var(--ag-border);
  --trace-border-strong: var(--ag-border-strong);
  --trace-text: var(--ag-text);
  --trace-muted: var(--ag-muted);
  --trace-muted-soft: var(--ag-muted);
  --trace-blue: var(--ag-blue);
  --trace-blue-soft: var(--ag-blue-soft);
  --trace-purple: #8a63ff;
  --trace-red: var(--ag-red);
  --trace-yellow: var(--ag-yellow);
  --trace-code-bg: #f3f6fa;
  --trace-code-text: #182230;
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
  background: linear-gradient(180deg, var(--trace-panel), var(--trace-bg));
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
  border: 1px solid rgba(161, 116, 255, 0.36);
  border-radius: 8px;
  background: rgba(161, 116, 255, 0.12);
  color: var(--trace-purple);
}

.trace-core.has-error {
  border-color: rgba(211, 74, 66, 0.36);
  background: var(--ag-red-soft);
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
.trace-canvas,
.trace-content-layout,
.trace-span-hierarchy,
.trace-content-detail {
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
  background: #252b34;
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
  background: linear-gradient(90deg, var(--trace-purple), var(--trace-blue));
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
  height: 100%;
  background: var(--trace-bg);
}

.trace-empty-stage {
  display: grid;
  height: 100%;
  place-items: center;
  padding: 24px;
}

.trace-detail-shell {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
}

.trace-detail-main {
  display: flex;
  min-height: 0;
  flex-direction: column;
}

.trace-run-header {
  flex: 0 0 auto;
  border-bottom: 1px solid var(--trace-border);
  background: var(--trace-panel);
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

.trace-evidence-strip {
  display: flex;
  flex: 1 0 100%;
  width: 100%;
  flex-wrap: wrap;
  gap: 8px;
}

.trace-evidence-chip {
  display: inline-flex;
  max-width: min(100%, 320px);
  align-items: center;
  gap: 6px;
  border: 1px solid var(--trace-border);
  border-radius: 999px;
  background: color-mix(in srgb, var(--trace-panel-soft) 72%, var(--trace-panel));
  padding: 4px 8px;
  text-align: left;
  transition: border-color 0.2s ease, background 0.2s ease;
}

.trace-evidence-chip:enabled:hover {
  border-color: color-mix(in srgb, var(--trace-purple) 54%, var(--trace-border));
  background: color-mix(in srgb, var(--trace-blue-soft) 52%, var(--trace-panel));
}

.trace-evidence-chip span {
  flex: 0 0 auto;
  color: var(--trace-muted);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.trace-evidence-chip strong {
  overflow: hidden;
  color: var(--trace-text);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-evidence-chip .el-icon {
  flex: 0 0 auto;
  color: var(--trace-muted);
  font-size: 12px;
}

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
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.trace-content-layout {
  display: grid;
  flex: 1 1 auto;
  grid-template-columns: minmax(260px, 360px) minmax(0, 1fr);
  overflow: hidden;
}

.trace-span-hierarchy {
  overflow: auto;
  border-right: 1px solid var(--trace-border);
  background: var(--trace-panel-soft);
  padding: 14px;
}

.trace-content-detail {
  display: grid;
  align-content: start;
  gap: 14px;
  overflow: auto;
  background: var(--trace-panel);
  padding: 14px;
}

.trace-content-detail > .empty-observe {
  align-self: center;
}

.trace-content-titlebar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid var(--trace-border);
  padding-bottom: 12px;
}

.trace-content-glyph {
  display: grid;
  flex: 0 0 auto;
  width: 30px;
  height: 30px;
  place-items: center;
  border: 1px solid rgba(161, 116, 255, 0.42);
  border-radius: 8px;
  background: rgba(161, 116, 255, 0.15);
  color: var(--trace-purple);
}

.trace-content-glyph.error {
  border-color: rgba(240, 93, 94, 0.45);
  background: rgba(240, 93, 94, 0.14);
  color: var(--trace-red);
}

.trace-content-badges {
  display: inline-flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.trace-content-badges > span {
  color: var(--trace-muted);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
}

.trace-content-tabs {
  display: flex;
  gap: 22px;
  border-bottom: 1px solid var(--trace-border);
}

.trace-content-tabs button {
  position: relative;
  padding: 0 0 10px;
  color: var(--trace-muted);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}

.trace-content-tabs button.active {
  color: var(--trace-text);
}

.trace-content-tabs button.active::after {
  position: absolute;
  right: 0;
  bottom: -1px;
  left: 0;
  height: 2px;
  border-radius: 999px;
  background: var(--trace-purple);
  content: "";
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
  background: linear-gradient(90deg, transparent, rgba(161, 116, 255, 0.42), transparent);
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
  border-color: rgba(161, 116, 255, 0.55);
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

.trace-hierarchy-tree {
  color: var(--trace-text);
}

.trace-hierarchy-tree .el-tree-node__content {
  height: auto;
  min-height: 0;
  padding: 0 !important;
  background: transparent !important;
}

.trace-hierarchy-tree .el-tree-node__children {
  position: relative;
  margin-left: 10px;
  padding-left: 10px;
}

.trace-hierarchy-tree .el-tree-node__children::before {
  position: absolute;
  inset: 0 auto 8px 0;
  width: 1px;
  background: var(--trace-border-strong);
  content: "";
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

.trace-hierarchy-fallback {
  display: grid;
  gap: 8px;
}

.trace-hierarchy-node {
  grid-template-columns: 12px minmax(0, 1fr);
  margin-bottom: 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  padding: 9px;
  text-align: left;
  transition: border-color 0.2s ease, background 0.2s ease;
}

.trace-hierarchy-node:hover,
.trace-hierarchy-node.active {
  border-color: rgba(161, 116, 255, 0.48);
  background: rgba(161, 116, 255, 0.12);
}

.trace-hierarchy-node.error {
  border-color: rgba(240, 93, 94, 0.3);
}

.trace-hierarchy-node-copy {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.trace-hierarchy-node-copy strong {
  display: block;
  overflow: hidden;
  color: var(--trace-text);
  font-size: 12px;
  font-weight: 800;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-hierarchy-node-copy small {
  color: var(--trace-muted);
  font-family: "JetBrains Mono", "Fira Code", monospace;
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
  background: rgba(240, 93, 94, 0.12);
  padding: 10px;
}

.trace-error-box span,
.trace-error-box strong {
  color: var(--trace-red);
}

.trace-json-head {
  margin-bottom: 8px;
}

.trace-io-section,
.trace-metadata-panel,
.trace-events-panel {
  border: 1px solid var(--trace-border);
  border-radius: 8px;
  background: var(--trace-panel);
  padding: 10px;
}

.trace-io-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.trace-io-head span {
  color: var(--trace-muted);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}

.trace-io-head > div {
  display: inline-flex;
  gap: 4px;
}

.trace-mode-chip {
  border: 1px solid var(--trace-border);
  border-radius: 6px;
  background: var(--trace-panel-soft);
  padding: 3px 7px;
  color: var(--trace-muted);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 9px;
  font-weight: 800;
}

.trace-mode-chip.active {
  border-color: rgba(161, 116, 255, 0.5);
  background: rgba(161, 116, 255, 0.16);
  color: var(--trace-text);
}

.trace-io-block {
  max-height: 260px;
  min-height: 84px;
  overflow: auto;
  margin: 0;
  border: 1px solid var(--trace-border);
  border-radius: 8px;
  background: var(--trace-code-bg);
  padding: 12px;
  color: var(--trace-code-text);
  font-family: "Inter", "Microsoft YaHei", ui-sans-serif, system-ui, sans-serif;
  font-size: 12px;
  line-height: 1.62;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.trace-json-payload {
  font-family: "JetBrains Mono", "Fira Code", monospace;
}

.trace-markdown-render {
  white-space: normal;
}

.trace-markdown-render :where(p, ul, ol, pre, blockquote) {
  margin: 0;
}

.trace-markdown-render :where(p + p, p + ul, p + ol, ul + p, ol + p, pre + p) {
  margin-top: 10px;
}

.trace-markdown-render :where(ul, ol) {
  padding-left: 22px;
}

.trace-markdown-render li + li {
  margin-top: 5px;
}

.trace-markdown-render :where(strong, b) {
  color: var(--trace-text);
  font-weight: 800;
}

.trace-markdown-render a {
  color: var(--trace-blue);
  font-weight: 750;
  text-decoration: none;
}

.trace-markdown-render code {
  border: 1px solid var(--trace-border);
  border-radius: 5px;
  background: color-mix(in srgb, var(--trace-code-bg) 82%, var(--trace-panel));
  padding: 1px 5px;
  color: var(--trace-blue);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 0.94em;
}

.trace-markdown-render pre {
  overflow: auto;
  border: 1px solid var(--trace-border);
  border-radius: 8px;
  background: var(--trace-code-bg);
  padding: 10px;
}

.trace-markdown-render pre code {
  border: 0;
  background: transparent;
  padding: 0;
}

.trace-io-block.empty {
  color: var(--trace-muted-soft);
  font-style: italic;
}

.trace-metadata-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.trace-metadata-item {
  min-width: 0;
  border: 1px solid var(--trace-border);
  border-radius: 8px;
  background: var(--trace-panel-soft);
  padding: 8px;
}

.trace-metadata-item span {
  display: block;
  color: var(--trace-muted);
  font-size: 10px;
  font-weight: 750;
}

.trace-metadata-item strong {
  display: block;
  margin-top: 4px;
  overflow: hidden;
  color: var(--trace-text);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-event-row {
  display: grid;
  gap: 4px;
  border: 1px solid var(--trace-border);
  border-radius: 8px;
  background: var(--trace-panel-soft);
  padding: 8px;
}

.trace-event-row + .trace-event-row {
  margin-top: 6px;
}

.trace-event-row strong {
  color: var(--trace-yellow);
  font-size: 11px;
}

.trace-event-row span {
  color: var(--trace-muted);
  font-size: 11px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.trace-json {
  max-height: 340px;
  overflow: auto;
  margin: 0;
  border: 1px solid var(--trace-border);
  border-radius: 8px;
  background: var(--trace-code-bg);
  padding: 12px;
  color: var(--trace-code-text);
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
  --trace-bg: var(--ag-frame);
  --trace-panel: var(--ag-panel);
  --trace-panel-soft: var(--ag-panel-soft);
  --trace-border: var(--ag-border);
  --trace-border-strong: var(--ag-border-strong);
  --trace-text: var(--ag-text);
  --trace-muted: var(--ag-muted);
  --trace-muted-soft: #777982;
  --trace-blue: var(--ag-blue);
  --trace-blue-soft: var(--ag-blue-soft);
  --trace-purple: #a174ff;
  --trace-red: var(--ag-red);
  --trace-yellow: var(--ag-yellow);
  --trace-code-bg: #101115;
  --trace-code-text: #e7e7e4;
}

html.dark .trace-core.has-error,
html.dark .trace-error-box {
  background: rgba(255, 111, 99, 0.12);
}

html.dark .trace-timeline-track {
  background: #2a2c33;
}

html.dark .trace-json,
html.dark .trace-json-payload {
  background: #101115;
  color: #e7e7e4;
}

html.dark .trace-waterfall-row:hover,
html.dark .trace-waterfall-row.active {
  background: #202127;
}

@media (max-width: 1480px) {
  .trace-content-layout {
    grid-template-columns: minmax(240px, 320px) minmax(0, 1fr);
  }
}

@media (max-width: 1180px) {
  .trace-content-layout {
    grid-template-columns: minmax(230px, 290px) minmax(0, 1fr);
  }

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

  .trace-detail-shell {
    height: auto;
    overflow: visible;
  }

  .trace-content-layout {
    grid-template-columns: minmax(0, 1fr);
    overflow: visible;
  }

  .trace-span-hierarchy {
    max-height: 360px;
    overflow: auto;
    border-right: 0;
    border-bottom: 1px solid var(--trace-border);
  }

  .trace-content-detail {
    overflow: visible;
  }
}

@media (max-width: 768px) {
  .trace-hero,
  .trace-run-header,
  .trace-span-hierarchy,
  .trace-content-detail {
    padding: 12px;
  }

  .trace-detail-grid,
  .trace-metadata-grid {
    grid-template-columns: 1fr;
  }

  .trace-evidence-chip {
    max-width: 100%;
  }

  .trace-content-titlebar {
    flex-direction: column;
  }

  .trace-content-badges {
    justify-content: flex-start;
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
