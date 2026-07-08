<template>
  <div class="trace-console ag-page-flow">
    <div class="trace-workbench trace-session-workbench">
      <div class="trace-query-toolbar ag-content-panel">
        <div class="trace-query-primary">
          <el-input
            v-model="sessionFilters.sessionId"
            size="small"
            clearable
            :placeholder="t('trace.filters.searchSessionId')"
            class="trace-filter-input wide"
            @keyup.enter="refresh"
          />
          <el-input
            v-model="runFilters.runId"
            size="small"
            clearable
            :placeholder="t('trace.filters.searchRunId')"
            class="trace-filter-input wide"
            @keyup.enter="refreshAll"
          />
          <el-select
            v-model="runFilters.status"
            size="small"
            clearable
            :placeholder="t('trace.filters.status')"
            class="trace-filter-select"
          >
            <el-option label="Success" value="OK" />
            <el-option label="Error" value="ERROR" />
            <el-option label="Running" value="UNSET" />
          </el-select>
          <el-button size="small" plain class="cursor-pointer" @click="traceAdvancedFiltersOpen = !traceAdvancedFiltersOpen">
            {{ t('trace.filters.advanced') }}
          </el-button>
        </div>
        <div class="trace-filter-actions">
          <el-button size="small" plain class="cursor-pointer" :disabled="loading || loadingSessions" @click="resetAllFilters">
            {{ t('trace.actions.reset') }}
          </el-button>
          <el-button
            size="small"
            type="primary"
            :loading="loading || loadingSessions"
            class="cursor-pointer"
            :aria-label="t('trace.actions.refreshAll')"
            @click="refresh"
          >
            <el-icon><Refresh /></el-icon>
          </el-button>
        </div>
        <div v-if="traceAdvancedFiltersOpen" class="trace-advanced-filters">
          <el-input v-model="sessionFilters.userId" size="small" clearable :placeholder="t('trace.filters.userId')" class="trace-filter-input" @keyup.enter="refreshAll" />
          <el-input v-model="sessionFilters.keyword" size="small" clearable :placeholder="t('trace.filters.keyword')" class="trace-filter-input" @keyup.enter="refreshAll" />
          <el-select v-model="sessionFilters.status" size="small" :placeholder="t('trace.filters.sessionStatus')" class="trace-filter-select">
            <el-option :label="t('trace.filters.activeSessions')" value="active" />
            <el-option :label="t('trace.filters.archivedSessions')" value="archived" />
            <el-option :label="t('trace.filters.allSessions')" value="all" />
          </el-select>
          <el-input v-model="runFilters.agentId" size="small" clearable :placeholder="t('trace.filters.agentId')" class="trace-filter-input" @keyup.enter="refreshAll" />
          <el-input v-model="runFilters.teamId" size="small" clearable :placeholder="t('trace.filters.teamId')" class="trace-filter-input" @keyup.enter="refreshAll" />
          <el-input v-model="runFilters.workflowId" size="small" clearable :placeholder="t('trace.filters.workflowId')" class="trace-filter-input" @keyup.enter="refreshAll" />
        </div>
      </div>

      <div class="trace-body-grid ag-workspace-panel">
        <aside class="trace-session-panel">
          <div class="trace-toolbar trace-session-toolbar">
            <div class="trace-panel-header">
              <div>
                <p>{{ t('trace.sessions.title') }}</p>
              </div>
              <strong>{{ filteredSessions.length }}</strong>
            </div>
          </div>

          <div class="trace-session-list">
            <el-skeleton v-if="loadingSessions && !sessions.length" :rows="SESSION_PAGE_SIZE" animated />
            <template v-else>
              <button
                v-for="session in pagedSessions"
                :key="session.session_id"
                type="button"
                class="trace-session-card"
                :class="{ active: selectedSessionId === session.session_id }"
                @click="selectSession(session)"
              >
                <span class="trace-session-card-head">
                  <strong :title="session.preview || session.session_id">
                    {{ session.preview || t('trace.sessions.untitled') }}
                  </strong>
                  <em>{{ formatSessionTime(session.updated_at || session.created_at) }}</em>
                </span>
                <span class="trace-session-id-line" :title="session.session_id">{{ compactId(session.session_id) }}</span>
              </button>
            </template>

            <el-pagination
              v-if="filteredSessions.length > SESSION_PAGE_SIZE"
              v-model:current-page="sessionPage"
              class="trace-session-pagination"
              :page-size="SESSION_PAGE_SIZE"
              :pager-count="5"
              :total="filteredSessions.length"
              layout="prev, pager, next"
              small
            />

            <div v-if="!filteredSessions.length && !loadingSessions" class="empty-observe trace-session-empty">
              <el-icon><Connection /></el-icon>
              <strong>{{ t('trace.empty.noSessionsTitle') }}</strong>
              <span>{{ t('trace.empty.noSessionsDescription') }}</span>
            </div>
          </div>
        </aside>

        <main class="trace-canvas">
          <section class="trace-runs-workbench">
            <div class="trace-runs-toolbar trace-toolbar">
              <div class="trace-panel-header">
                <div>
                  <p>{{ t('trace.runs.title') }}</p>
                  <span v-if="selectedSession">{{ compactId(selectedSession.session_id) }}</span>
                </div>
                <strong>{{ filteredRunRows.length }}</strong>
              </div>
            </div>

          <div v-if="!selectedSession" class="trace-empty-stage">
            <div class="empty-observe">
              <el-icon><Aim /></el-icon>
              <strong>{{ t('trace.empty.selectSessionTitle') }}</strong>
            </div>
          </div>

          <div v-else-if="!filteredRunRows.length && !loading" class="trace-empty-stage">
            <div class="empty-observe">
              <el-icon><Connection /></el-icon>
              <strong>{{ t('trace.empty.noSessionTracesTitle') }}</strong>
              <span>{{ t('trace.empty.noSessionTracesDescription') }}</span>
            </div>
          </div>

          <div v-else class="trace-runs-list">
            <button
              v-for="row in filteredRunRows"
              :key="row.key"
              type="button"
              class="trace-waterfall-row trace-run-row"
              :class="{ active: selectedTrace?.trace_id === row.trace.trace_id, error: row.trace.status === 'ERROR' }"
              @click="openTraceDetail(row.trace.trace_id)"
            >
              <span class="trace-span-name">
                <div>
                  <span class="trace-status-dot" :class="statusClass(row.trace.status)" />
                  <strong :title="row.title">{{ row.title }}</strong>
                </div>
                <span :title="row.runId">{{ compactId(row.runId) }}</span>
              </span>
              <span class="trace-run-meta">
                <el-tag :type="tagType(row.trace.status)" effect="light" size="small">{{ statusLabel(row.trace.status) }}</el-tag>
                <span :title="row.ownerId">{{ compactId(row.ownerId) }}</span>
              </span>
              <span class="span-duration" :class="durationClass(row.trace.duration_ms)">
                <strong>{{ formatDuration(row.trace.duration_ms) }}</strong>
                <small>{{ formatDateTime(row.trace.created_at || row.trace.start_time) }}</small>
              </span>
            </button>
          </div>

          <el-alert v-if="apiError" class="trace-alert" type="error" :title="apiError" show-icon />
        </section>

          <aside
            v-if="selectedTrace"
            class="trace-detail-panel ag-right-panel"
            aria-label="Selected run detail"
          >
              <div class="trace-detail-shell trace-inspector-shell">
                <div class="trace-run-header">
                  <div class="trace-run-title">
                  <div class="trace-run-heading">
                    <span class="trace-status-dot large" :class="statusClass(selectedTrace.status)" />
                    <div>
                      <h4 :title="selectedTrace.name">{{ selectedTrace.name }}</h4>
                      <span>{{ formatAnyDateTime(selectedTrace.created_at || selectedTrace.start_time) }}</span>
                    </div>
                    <el-tag :type="tagType(selectedTrace.status)" effect="light" size="small">{{ statusLabel(selectedTrace.status) }}</el-tag>
                    <span class="trace-header-duration" :class="durationClass(selectedTrace.duration_ms)">{{ formatDuration(selectedTrace.duration_ms) }}</span>
                  </div>
                </div>
              </div>

              <div class="trace-content-layout trace-inspector-grid">
                <aside class="trace-inspector-primary">
                    <div class="trace-span-hierarchy">
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
                            @click.stop="selectSpan(data.span, 'input')"
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
                          @click="selectSpan(span, 'input')"
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
                        <strong>{{ t('trace.empty.noSpansTitle') }}</strong>
                        <span>{{ t('trace.empty.noSpansDescription') }}</span>
                      </div>
                    </div>
                </aside>

                <section class="trace-content-detail trace-inspector-secondary" :data-active-detail-tab="activeDetailTab">
                  <div v-if="!selectedSpan" class="empty-observe">
                    <el-icon><Aim /></el-icon>
                    <strong>{{ t('trace.empty.selectSpanTitle') }}</strong>
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
                      <button
                        type="button"
                        role="tab"
                        :aria-selected="activeDetailTab === 'overview'"
                        :class="{ active: activeDetailTab === 'overview' }"
                        @click="activeDetailTab = 'overview'"
                      >
                        Overview
                      </button>
                    </div>

                    <div v-if="selectedSpan.status_message" class="trace-error-box">
                      <span>{{ t('trace.labels.errorMessage') }}</span>
                      <strong>{{ selectedSpan.status_message }}</strong>
                    </div>

                    <div v-if="activeDetailTab === 'info'" class="trace-tab-panel trace-info-tab" id="trace-detail-input">
                      <section class="trace-io-section">
                        <div class="trace-io-head">
                          <span>Input</span>
                          <div class="trace-io-actions">
                            <el-select v-model="inputViewMode" size="small" class="trace-mode-select">
                              <el-option label="Text" value="text" />
                              <el-option label="JSON" value="json" />
                              <el-option label="Markdown" value="markdown" />
                            </el-select>
                            <el-button size="small" plain class="cursor-pointer" @click="copyPayload(parsedSpan.input, inputViewMode)">{{ t('trace.actions.copy') }}</el-button>
                            <el-button size="small" plain class="cursor-pointer" @click="togglePayloadExpanded('input')">
                              {{ expandedPayloads.has('input') ? t('trace.actions.collapse') : t('trace.actions.expand') }}
                            </el-button>
                          </div>
                        </div>
                        <pre
                          v-if="inputViewMode === 'json'"
                          class="trace-io-block trace-json-payload"
                          :class="{ empty: !parsedSpan.input.text, expanded: expandedPayloads.has('input') }"
                        >{{ payloadTextForMode(parsedSpan.input, inputViewMode, "No input captured") }}</pre>
                        <div
                          v-else
                          class="trace-markdown-render trace-io-block"
                          :class="{ empty: !parsedSpan.input.text, expanded: expandedPayloads.has('input') }"
                          v-html="renderPayloadMarkupForMode(parsedSpan.input, inputViewMode, 'No input captured')"
                        />
                      </section>

                      <section id="trace-detail-output" class="trace-io-section">
                        <div class="trace-io-head">
                          <span>Output</span>
                          <div class="trace-io-actions">
                            <el-select v-model="outputViewMode" size="small" class="trace-mode-select">
                              <el-option label="Text" value="text" />
                              <el-option label="JSON" value="json" />
                              <el-option label="Markdown" value="markdown" />
                            </el-select>
                            <el-button size="small" plain class="cursor-pointer" @click="copyPayload(parsedSpan.output, outputViewMode)">{{ t('trace.actions.copy') }}</el-button>
                            <el-button size="small" plain class="cursor-pointer" @click="togglePayloadExpanded('output')">
                              {{ expandedPayloads.has('output') ? t('trace.actions.collapse') : t('trace.actions.expand') }}
                            </el-button>
                          </div>
                        </div>
                        <pre
                          v-if="outputViewMode === 'json'"
                          class="trace-io-block trace-json-payload"
                          :class="{ empty: !parsedSpan.output.text, expanded: expandedPayloads.has('output') }"
                        >{{ payloadTextForMode(parsedSpan.output, outputViewMode, "No output captured") }}</pre>
                        <div
                          v-else
                          class="trace-markdown-render trace-io-block"
                          :class="{ empty: !parsedSpan.output.text, expanded: expandedPayloads.has('output') }"
                          v-html="renderPayloadMarkupForMode(parsedSpan.output, outputViewMode, 'No output captured')"
                        />
                      </section>
                    </div>

                    <div v-else-if="activeDetailTab === 'metadata'" class="trace-tab-panel trace-metadata-tab" id="trace-detail-metadata">
                      <section class="trace-metadata-panel trace-metadata-ledger">
                        <div class="trace-json-head">
                          <span>Metadata</span>
                        </div>
                        <div class="trace-metadata-grid">
                          <div v-for="item in traceMetadataItems" :key="item.label" class="trace-metadata-item">
                            <span>{{ item.label }}</span>
                            <div class="trace-metadata-value">
                              <strong :title="item.value">{{ item.displayValue }}</strong>
                              <el-tooltip :content="t('trace.actions.copy')" placement="top">
                                <button
                                  type="button"
                                  class="trace-metadata-copy"
                                  :aria-label="`${t('trace.actions.copy')} ${item.label}`"
                                  @click="copyMetadataValue(item.value)"
                                >
                                  <el-icon><CopyDocument /></el-icon>
                                </button>
                              </el-tooltip>
                            </div>
                          </div>
                        </div>
                      </section>
                    </div>

                    <div v-else class="trace-tab-panel trace-overview-tab" id="trace-detail-overview">
                      <section class="trace-overview-panel">
                        <div class="trace-json-head">
                          <span>Overview</span>
                        </div>
                        <div class="trace-overview-grid">
                          <div v-for="item in overviewItems" :key="item.label" class="trace-detail-metric" :class="{ error: item.tone === 'error' }">
                            <span>{{ item.label }}</span>
                            <strong :title="item.value">{{ item.displayValue }}</strong>
                          </div>
                        </div>
                      </section>
                      <section id="trace-detail-tools" class="trace-tool-panel">
                        <div class="trace-json-head">
                          <span>Tool Calls</span>
                        </div>
                        <div v-if="toolCallItems.length" class="trace-tool-list">
                          <details v-for="tool in toolCallItems" :key="tool.id" class="trace-tool-call">
                            <summary>
                              <span class="trace-status-dot" :class="statusClass(tool.status)" />
                              <strong>{{ tool.name }}</strong>
                              <em :class="durationClass(tool.durationMs)">{{ formatDuration(tool.durationMs) }}</em>
                              <el-tag :type="tagType(tool.status)" effect="light" size="small">{{ statusLabel(tool.status) }}</el-tag>
                            </summary>
                            <div class="trace-tool-body">
                              <span>Arguments</span>
                              <pre>{{ tool.arguments }}</pre>
                              <span>Response</span>
                              <pre>{{ tool.response }}</pre>
                              <span>Metadata</span>
                              <pre>{{ tool.metadata }}</pre>
                            </div>
                          </details>
                        </div>
                        <div v-else class="trace-inline-empty">No tool calls captured</div>
                      </section>

                      <section id="trace-detail-logs" class="trace-events-panel">
                        <div class="trace-json-head">
                          <span>Logs</span>
                        </div>
                        <div v-if="logItems.length">
                          <article v-for="event in logItems" :key="`${event.name}:${event.message}`" class="trace-event-row">
                            <strong>{{ event.name }}</strong>
                            <span>{{ event.message }}</span>
                          </article>
                        </div>
                        <div v-else class="trace-inline-empty">No logs captured</div>
                      </section>
                    </div>
                  </template>

                  <el-alert v-if="apiError" class="trace-alert" type="error" :title="apiError" show-icon />
                </section>
              </div>
            </div>
          </aside>
          <aside v-else class="trace-detail-panel trace-detail-placeholder ag-right-panel">
            <div class="empty-observe">
              <el-icon><Aim /></el-icon>
              <strong>{{ t('trace.empty.selectTraceTitle') }}</strong>
            </div>
          </aside>
      </main>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "vue"
import { ElMessage } from "element-plus"
import MarkdownIt from "markdown-it"
import { useI18n } from "vue-i18n"
import {
  Aim,
  Connection,
  CopyDocument,
  Cpu,
  Refresh,
} from "@element-plus/icons-vue"
import { useChatHistory } from "../composables/useChatApi"
import { useTracingApi } from "../composables/useTraceApi"
import { useTracePayloadControls } from "../composables/useTracePayloadControls"
import { useTraceSessionController } from "../composables/useTraceSessionController"
import {
  buildTraceLogItems,
  buildTraceMetadataItems,
  buildTraceOverviewItems,
  buildTraceRunRows,
  buildTraceToolCallItems,
  clampTraceSessionPage,
  compactTraceId,
  createTraceRunFilters,
  createTraceSessionFilters,
  emptyTraceParsedSpan,
  filterTraceRunRows,
  filterTraceSessions,
  findTraceRunRow,
  findTraceSession,
  formatTraceAnyDateTime,
  formatTraceDateTime,
  formatTraceDuration,
  formatTraceSessionTime,
  pageTraceSessions,
  traceDurationClass,
  traceDetailTabForSection,
  tracePayloadTextForMode,
  traceRunMetrics,
  traceStatusClass,
  traceStatusLabel,
  traceTagType,
  type TraceDetailTab,
  type TracePayloadViewMode,
  type TraceSummaryState,
} from "../modules/traceWorkbench"
import { useTraceStore } from "../stores/traces"
import type { ChatSession, ParsedSpanPayload, SpanItem, SpanTreeNode, TraceItem } from "../types"

const { t } = useI18n()
const { loading, error, listTraces, getTrace } = useTracingApi()
const { loadingSessions, listSessions } = useChatHistory()
const markdownRenderer = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

const traceStore = useTraceStore()
const sessions = ref<ChatSession[]>([])
const sessionTraceItems = ref<TraceItem[]>([])
const traceSummary = ref<TraceSummaryState>({
  totalTraces: 0,
  totalSpans: 0,
  errors: 0,
  avgLatencyMs: 0,
  sampleSize: 0,
})
const selectedSessionId = ref<string | null>(null)
const sessionFilters = reactive(createTraceSessionFilters())
const runFilters = reactive(createTraceRunFilters())

const selectedTrace = ref<TraceItem | null>(null)
const spans = ref<SpanItem[]>([])
const tree = ref<SpanTreeNode[]>([])
const selectedSpan = ref<SpanItem | null>(null)
const activeDetailTab = ref<TraceDetailTab>("info")
const traceAdvancedFiltersOpen = ref(false)
const sessionPage = ref(1)
const inputViewMode = ref<PayloadViewMode>("text")
const outputViewMode = ref<PayloadViewMode>("text")

const loadingDetail = ref(false)
const apiError = computed(() => error.value)
let filterRefreshTimer: ReturnType<typeof window.setTimeout> | null = null

type PayloadViewMode = TracePayloadViewMode
const SESSION_PAGE_SIZE = 10
const compactId = compactTraceId
const durationClass = traceDurationClass
const formatDuration = formatTraceDuration
const payloadTextForMode = tracePayloadTextForMode
const statusClass = traceStatusClass
const statusLabel = traceStatusLabel
const tagType = traceTagType

const filteredSessions = computed(() => filterTraceSessions(sessions.value, sessionFilters))
const pagedSessions = computed(() => {
  return pageTraceSessions(filteredSessions.value, sessionPage.value, SESSION_PAGE_SIZE)
})

const selectedSession = computed(() => findTraceSession(sessions.value, selectedSessionId.value))

const runRows = computed(() => buildTraceRunRows({
  traces: sessionTraceItems.value,
  selectedSession: selectedSession.value,
  selectedSessionId: selectedSessionId.value,
  labels: {
    agentId: t("trace.filters.agentId"),
    teamId: t("trace.filters.teamId"),
    workflowId: t("trace.filters.workflowId"),
  },
}))

const filteredRunRows = computed(() => filterTraceRunRows(runRows.value, runFilters))

const selectedRunRow = computed(() => findTraceRunRow(filteredRunRows.value, selectedTrace.value?.trace_id))

const selectedRunMetrics = computed<Record<string, unknown>>(() => traceRunMetrics(selectedRunRow.value))

const overviewItems = computed(() => {
  return buildTraceOverviewItems({
    trace: selectedTrace.value,
    run: selectedRunRow.value?.run,
    span: selectedSpan.value,
    parsedSpan: parsedSpan.value,
    metrics: selectedRunMetrics.value,
  })
})

const traceMetadataItems = computed(() => {
  return buildTraceMetadataItems({
    trace: selectedTrace.value,
    run: selectedRunRow.value?.run,
    session: selectedSession.value,
    row: selectedRunRow.value,
    span: selectedSpan.value,
    formatAnyDateTime,
  })
})

const toolCallItems = computed(() => buildTraceToolCallItems(spans.value))

const logItems = computed(() => {
  return buildTraceLogItems({
    parsedEvents: parsedSpan.value.events || [],
    rawEvents: selectedSpan.value?.events || [],
  })
})

const parsedSpan = computed(() => selectedSpan.value?.parsed || emptyTraceParsedSpan)
const renderMarkdown = (value: string) => {
  return markdownRenderer.render(value || "")
}

const formatDateTime = formatTraceDateTime
const formatAnyDateTime = formatTraceAnyDateTime
const formatSessionTime = formatTraceSessionTime

const {
  expandedPayloads,
  copyPayload,
  copyMetadataValue,
  togglePayloadExpanded,
} = useTracePayloadControls()

const renderPayloadMarkupForMode = (payload: ParsedSpanPayload, mode: PayloadViewMode, fallback: string) => {
  const text = payloadTextForMode(payload, mode, fallback)
  if (mode === "markdown") return renderMarkdown(text)
  return renderMarkdown(markdownRenderer.utils.escapeHtml(text))
}

const scrollDetailIntoView = () => {
  if (!window.matchMedia("(max-width: 980px)").matches) return
  requestAnimationFrame(() => {
    document.querySelector<HTMLElement>(".trace-detail-panel")?.scrollIntoView({ block: "start", behavior: "smooth" })
  })
}

const clearPendingFilterRefresh = () => {
  if (filterRefreshTimer !== null) {
    window.clearTimeout(filterRefreshTimer)
    filterRefreshTimer = null
  }
}

const {
  refresh,
  selectSession,
  selectSessionById,
  openTraceDetail,
  resetAllFilters,
  refreshAll,
  refreshRuns,
} = useTraceSessionController({
  sessions,
  filteredSessions,
  selectedSession,
  selectedSessionId,
  sessionFilters,
  runFilters,
  sessionTraceItems,
  traceSummary,
  selectedTrace,
  spans,
  tree,
  selectedSpan,
  loadingDetail,
  traceStore,
  listSessions,
  listTraces,
  getTrace,
  clearPendingFilterRefresh,
  scrollDetailIntoView,
})

const scrollDetailSectionIntoView = async (section: "overview" | "input" | "output" | "tools" | "logs" | "metadata") => {
  await nextTick()
  const target = document.getElementById(`trace-detail-${section}`)
  target?.scrollIntoView({ block: "start", behavior: "smooth" })
}

const selectSpan = (span: SpanItem, section: "overview" | "input" | "output" | "tools" | "logs" | "metadata" = "input") => {
  selectedSpan.value = span
  activeDetailTab.value = traceDetailTabForSection(section)
  void scrollDetailSectionIntoView(section)
}

const onSpanNodeClick = (node: SpanTreeNode) => {
  selectSpan(node.span)
}

const scheduleSessionFilterRefresh = () => {
  if (filterRefreshTimer !== null) {
    window.clearTimeout(filterRefreshTimer)
  }
  filterRefreshTimer = window.setTimeout(() => {
    filterRefreshTimer = null
    void refresh()
  }, 250)
}

const scheduleRunFilterRefresh = () => {
  if (filterRefreshTimer !== null) {
    window.clearTimeout(filterRefreshTimer)
  }
  filterRefreshTimer = window.setTimeout(() => {
    filterRefreshTimer = null
    void refreshRuns()
  }, 250)
}

const scheduleFilterRefresh = () => {
  if (selectedSession.value) {
    scheduleRunFilterRefresh()
  } else {
    scheduleSessionFilterRefresh()
  }
}

watch(
  () => filteredSessions.value.length,
  (count) => {
    sessionPage.value = clampTraceSessionPage(sessionPage.value, count, SESSION_PAGE_SIZE)
  },
)

watch(
  () => [sessionFilters.sessionId, sessionFilters.userId, sessionFilters.keyword, sessionFilters.status],
  () => {
    sessionPage.value = 1
    scheduleSessionFilterRefresh()
  },
)

watch(
  () => [runFilters.runId, runFilters.agentId, runFilters.teamId, runFilters.workflowId, runFilters.status],
  () => {
    scheduleFilterRefresh()
  },
)

const handleExternalTraceSelect = (event: Event) => {
  const detail = (event as CustomEvent<{ traceId?: string }>).detail
  void openTraceDetail(detail?.traceId)
}

const handleExternalSessionSelect = (event: Event) => {
  const detail = (event as CustomEvent<{ sessionId?: string; userId?: string | null; runId?: string | null }>).detail
  if (detail?.sessionId) void selectSessionById(detail.sessionId, detail.userId, detail.runId)
}

onMounted(async () => {
  window.addEventListener("agno-aios-trace-select", handleExternalTraceSelect)
  window.addEventListener("agno-aios-trace-session-open", handleExternalSessionSelect)
  window.addEventListener("agno-aios-trace-session-select", handleExternalSessionSelect)
  try {
    await refresh()
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : t("trace.messages.loadFailed"))
  }
})

onUnmounted(() => {
  window.removeEventListener("agno-aios-trace-select", handleExternalTraceSelect)
  window.removeEventListener("agno-aios-trace-session-open", handleExternalSessionSelect)
  window.removeEventListener("agno-aios-trace-session-select", handleExternalSessionSelect)
  clearPendingFilterRefresh()
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
  --trace-purple: var(--ag-purple);
  --trace-red: var(--ag-red);
  --trace-yellow: var(--ag-yellow);
  --trace-code-bg: var(--ag-code-bg);
  --trace-code-text: var(--ag-code-text);
  color: var(--trace-text);
  font-family: "Inter", "Fira Sans", "Microsoft YaHei", ui-sans-serif, system-ui, sans-serif;
}

.trace-console :where(button, div, section, aside, main, p, strong, span, small, pre) {
  min-width: 0;
}

.trace-toolbar {
  border-bottom: 1px solid var(--trace-border);
  background: var(--trace-panel);
  padding: 12px 16px;
}

.trace-toolbar,
.trace-run-header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.trace-run-heading,
.trace-panel-title,
.trace-selected-span {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.trace-panel-header p,
.trace-io-head span {
  color: var(--trace-muted);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}

.trace-panel-header p {
  margin: 0;
  letter-spacing: 0;
}

.trace-run-heading h4 {
  margin: 2px 0 0;
  color: var(--trace-text);
  font-size: 15px;
  font-weight: 800;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.trace-panel-header span {
  display: block;
  margin-top: 4px;
  color: var(--trace-muted);
  font-size: 12px;
  line-height: 1.45;
}

.trace-filter-bar {
  display: flex;
  flex: 1 1 auto;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  width: 100%;
}

.trace-filter-input,
.trace-filter-select {
  width: min(180px, 100%);
}

.trace-date-picker {
  width: min(360px, 100%) !important;
}

.trace-workbench {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  gap: var(--ag-section-gap);
  overflow: visible;
}

.trace-session-workbench {
  display: grid;
  grid-template-columns: minmax(300px, 380px) minmax(0, 1fr);
}

.trace-session-panel {
  display: flex;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  border-right: 1px solid var(--trace-border);
  background: var(--trace-panel);
}

.trace-session-toolbar {
  display: grid;
  gap: 12px;
  border-bottom: 1px solid var(--trace-border);
}

.trace-filter-actions {
  display: flex;
  gap: 8px;
}

.trace-session-list {
  display: grid;
  align-content: start;
  gap: 10px;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}

.trace-session-pagination {
  justify-self: center;
  margin-top: 2px;
}

.trace-session-card {
  display: grid;
  gap: 10px;
  width: 100%;
  border: 1px solid var(--trace-border);
  border-radius: 8px;
  background: var(--trace-panel-soft);
  padding: 12px;
  text-align: left;
  transition: border-color 0.18s ease, background 0.18s ease, transform 0.18s ease;
}

.trace-session-card:hover {
  border-color: color-mix(in srgb, var(--trace-blue) 52%, var(--trace-border));
  background: color-mix(in srgb, var(--trace-blue-soft) 38%, var(--trace-panel));
  transform: translateY(-1px);
}

.trace-session-card.active {
  border-color: color-mix(in srgb, var(--trace-purple) 64%, var(--trace-border));
  background: color-mix(in srgb, var(--trace-blue-soft) 55%, var(--trace-panel));
  box-shadow: inset 3px 0 0 var(--trace-purple);
}

.trace-session-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.trace-session-card-head strong {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  color: var(--trace-text);
  font-size: 13px;
  font-weight: 800;
  line-height: 1.35;
}

.trace-session-card-head em {
  flex: 0 0 auto;
  color: var(--trace-muted);
  font-size: 11px;
  font-style: normal;
  white-space: nowrap;
}

.trace-session-id-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.trace-id-box {
  display: grid;
  gap: 3px;
  min-width: 0;
  border: 1px solid var(--trace-border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--trace-panel) 76%, transparent);
  padding: 7px 8px;
}

.trace-id-box small {
  color: var(--trace-muted);
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
}

.trace-id-box b {
  overflow: hidden;
  color: var(--trace-text);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-session-empty {
  margin-top: 24px;
}

.trace-session-trace-strip {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 12px;
  overflow: hidden;
  border-bottom: 1px solid var(--trace-border);
  background: var(--trace-panel);
  padding: 10px 12px;
}

.trace-selected-session {
  display: grid;
  flex: 0 0 auto;
  gap: 2px;
  max-width: 190px;
}

.trace-selected-session strong {
  overflow: hidden;
  color: var(--trace-text);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-selected-session span {
  color: var(--trace-muted);
  font-size: 11px;
}

.trace-session-trace-list {
  display: flex;
  min-width: 0;
  flex: 1 1 auto;
  gap: 8px;
  overflow: auto;
}

.trace-session-trace-chip {
  display: inline-flex;
  flex: 0 0 auto;
  max-width: 260px;
  align-items: center;
  gap: 7px;
  border: 1px solid var(--trace-border);
  border-radius: 999px;
  background: var(--trace-panel-soft);
  padding: 6px 10px;
  transition: border-color 0.18s ease, background 0.18s ease;
}

.trace-session-trace-chip:hover,
.trace-session-trace-chip.active {
  border-color: color-mix(in srgb, var(--trace-purple) 56%, var(--trace-border));
  background: color-mix(in srgb, var(--trace-blue-soft) 50%, var(--trace-panel));
}

.trace-session-trace-chip.error {
  border-color: color-mix(in srgb, var(--trace-red) 44%, var(--trace-border));
}

.trace-session-trace-chip strong {
  overflow: hidden;
  color: var(--trace-text);
  font-size: 11px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-session-trace-chip em {
  color: var(--trace-muted);
  font-size: 10px;
  font-style: normal;
  white-space: nowrap;
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
  background: var(--trace-panel-soft);
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
  background: var(--ag-green);
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
  display: contents;
  min-width: 0;
  min-height: 0;
}

.trace-empty-stage {
  display: grid;
  flex: 1 1 auto;
  height: 100%;
  min-height: 0;
  place-items: center;
  padding: 24px;
}

.trace-detail-shell {
  display: flex;
  flex: 1 1 auto;
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
  overflow: hidden;
  color: var(--trace-text);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-metadata-value {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 24px;
  align-items: center;
  gap: 6px;
  margin-top: 5px;
  border: 1px solid var(--trace-border-strong);
  border-radius: 8px;
  background: color-mix(in srgb, var(--trace-panel) 82%, var(--trace-panel-soft));
  padding: 4px 5px 4px 8px;
}

.trace-metadata-copy {
  display: inline-grid;
  width: 22px;
  height: 22px;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 6px;
  color: var(--trace-muted);
}

.trace-metadata-copy:hover,
.trace-metadata-copy:focus-visible {
  border-color: color-mix(in srgb, var(--trace-purple) 48%, var(--trace-border));
  background: color-mix(in srgb, var(--trace-purple) 13%, transparent);
  color: var(--trace-text);
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
  --trace-muted-soft: var(--ag-muted);
  --trace-blue: var(--ag-blue);
  --trace-blue-soft: var(--ag-blue-soft);
  --trace-purple: var(--ag-purple);
  --trace-red: var(--ag-red);
  --trace-yellow: var(--ag-yellow);
  --trace-code-bg: var(--ag-code-bg);
  --trace-code-text: var(--ag-code-text);
}

html.dark .trace-error-box {
  background: rgba(255, 111, 99, 0.12);
}

html.dark .trace-timeline-track {
  background: var(--trace-panel-soft);
}

html.dark .trace-json,
html.dark .trace-json-payload {
  background: var(--trace-code-bg);
  color: var(--trace-code-text);
}

html.dark .trace-waterfall-row:hover,
html.dark .trace-waterfall-row.active {
  background: var(--trace-panel-raised, var(--ag-panel-raised));
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
  .trace-toolbar,
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

.trace-runs-workbench {
  position: relative;
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  overflow: hidden;
}

.trace-runs-toolbar {
  display: grid;
  gap: 12px;
}

.trace-runs-list {
  display: grid;
  align-content: start;
  gap: 10px;
  min-height: 0;
  overflow: auto;
  padding: 14px;
}

.trace-run-row {
  grid-template-columns: minmax(240px, 1.3fr) minmax(220px, 1fr) 120px;
}

.trace-run-meta {
  display: grid;
  min-width: 0;
  gap: 5px;
  color: var(--trace-muted);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
}

.trace-run-meta span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-detail-panel {
  position: relative;
  z-index: 9;
  display: flex;
  width: 100%;
  min-width: 0;
  height: 100%;
  min-height: 0;
  border: 1px solid var(--ag-border);
  border-radius: 12px;
  background: var(--trace-panel);
  box-shadow: var(--ag-shadow-panel);
}

.trace-detail-panel .trace-inspector-shell {
  width: 100%;
}

.trace-detail-placeholder {
  display: grid;
  place-items: center;
  padding: 20px;
}

.trace-session-workbench {
  display: flex;
  min-height: 0;
  flex-direction: column;
}

.trace-query-toolbar {
  display: grid;
  flex: 0 0 auto;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px 12px;
}

.trace-query-primary,
.trace-advanced-filters {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.trace-advanced-filters {
  grid-column: 1 / -1;
  border-top: 1px solid var(--trace-border);
  padding-top: 10px;
}

.trace-filter-input.wide {
  width: min(240px, 100%);
}

.trace-body-grid {
  display: grid;
  min-height: 0;
  flex: 1 1 auto;
  grid-template-columns: minmax(0, 20%) minmax(0, 20%) minmax(0, 60%);
  overflow: hidden;
}

.trace-runs-workbench {
  grid-column: 2;
  grid-row: 1;
}

.trace-detail-panel {
  grid-column: 3;
  grid-row: 1;
}

.trace-session-toolbar,
.trace-runs-toolbar {
  padding: 12px 14px;
}

.trace-session-list {
  gap: 8px;
  padding: 10px;
}

.trace-session-card {
  gap: 7px;
  border-color: color-mix(in srgb, var(--trace-border) 82%, transparent);
  background: color-mix(in srgb, var(--trace-panel-soft) 74%, var(--trace-panel));
  padding: 9px 10px;
}

.trace-session-card:hover {
  border-color: color-mix(in srgb, var(--trace-purple) 46%, var(--trace-border));
  background: color-mix(in srgb, var(--trace-blue-soft) 30%, var(--trace-panel));
}

.trace-session-card.active {
  border-color: color-mix(in srgb, var(--trace-purple) 72%, var(--trace-border));
  background: color-mix(in srgb, var(--trace-purple) 12%, var(--trace-panel));
  box-shadow: inset 3px 0 0 var(--trace-purple);
}

.trace-session-card-head strong {
  -webkit-line-clamp: 1;
  font-size: 12px;
}

.trace-session-id-line {
  overflow: hidden;
  color: var(--trace-muted);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-run-row {
  grid-template-columns: minmax(0, 1fr);
  border-color: color-mix(in srgb, var(--trace-border) 82%, transparent);
  background: color-mix(in srgb, var(--trace-panel-soft) 72%, var(--trace-panel));
  padding: 11px 12px;
  transition: border-color 0.16s ease, background 0.16s ease, transform 0.16s ease;
}

.trace-run-row:hover {
  border-color: color-mix(in srgb, var(--trace-purple) 54%, var(--trace-border));
  background: color-mix(in srgb, var(--trace-blue-soft) 34%, var(--trace-panel));
  transform: translateY(-1px);
}

.trace-run-row.active {
  border-color: color-mix(in srgb, var(--trace-purple) 78%, var(--trace-border));
  background: color-mix(in srgb, var(--trace-purple) 13%, var(--trace-panel));
  box-shadow: inset 3px 0 0 var(--trace-purple);
}

.trace-run-meta {
  display: flex;
  align-items: flex-start;
  justify-content: flex-start;
  gap: 8px;
}

.span-duration.duration-fast strong,
.trace-header-duration.duration-fast,
.trace-tool-call em.duration-fast {
  color: var(--ag-green);
}

.span-duration.duration-medium strong,
.trace-header-duration.duration-medium,
.trace-tool-call em.duration-medium {
  color: var(--trace-yellow);
}

.span-duration.duration-slow strong,
.trace-header-duration.duration-slow,
.trace-tool-call em.duration-slow {
  color: #f59e0b;
}

.span-duration.duration-critical strong,
.trace-header-duration.duration-critical,
.trace-tool-call em.duration-critical {
  color: var(--trace-red);
}

.trace-header-duration {
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  font-weight: 800;
}

.trace-run-header {
  gap: 10px;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: center;
  padding: 10px 12px;
}

.trace-run-title {
  grid-column: 1;
  grid-row: 1;
}

.trace-copy-actions {
  grid-column: 1 / -1;
  grid-row: 2;
}

.trace-run-heading > div > span {
  color: var(--trace-muted);
  font-size: 11px;
}

.trace-copy-actions {
  gap: 6px;
}

.trace-content-layout.trace-inspector-grid {
  display: grid;
  flex: 1 1 auto;
  grid-template-columns: minmax(230px, 0.9fr) minmax(0, 1.1fr);
  gap: 0;
  overflow: hidden;
  background: color-mix(in srgb, var(--trace-panel) 96%, var(--trace-bg));
}

.trace-inspector-primary,
.trace-inspector-secondary {
  min-height: 0;
  overflow: auto;
}

.trace-inspector-primary {
  border-right: 1px solid var(--trace-border);
  padding: 12px;
}

.trace-inspector-secondary {
  display: grid;
  align-content: start;
  gap: 12px;
  height: 100%;
  background: transparent;
  padding: 12px;
}

.trace-overview-panel,
.trace-tool-panel {
  border: 1px solid var(--trace-border);
  border-radius: 8px;
  background: var(--trace-panel);
  padding: 10px;
}

.trace-overview-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.trace-detail-metric.error {
  border-color: rgba(240, 93, 94, 0.34);
  background: rgba(240, 93, 94, 0.1);
}

.trace-hierarchy-toggle {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--trace-text);
  font-size: 12px;
  font-weight: 800;
}

.trace-hierarchy-toggle strong {
  color: var(--trace-muted);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
}

.trace-tab-panel {
  display: grid;
  align-content: start;
  gap: 12px;
}

.trace-info-tab {
  grid-template-rows: auto auto;
}

.trace-metadata-tab {
  padding-bottom: 8px;
}

.trace-io-actions {
  display: inline-flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.trace-mode-select {
  width: 108px;
}

.trace-io-block.expanded {
  max-height: none;
}

.trace-tool-list {
  display: grid;
  gap: 8px;
}

.trace-tool-call {
  border: 1px solid var(--trace-border);
  border-radius: 8px;
  background: var(--trace-panel-soft);
}

.trace-tool-call summary {
  display: grid;
  grid-template-columns: 14px minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 8px;
  padding: 9px;
  cursor: pointer;
}

.trace-tool-call summary strong {
  overflow: hidden;
  color: var(--trace-text);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-tool-call summary em {
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
  font-style: normal;
  font-weight: 800;
}

.trace-tool-body {
  display: grid;
  gap: 6px;
  border-top: 1px solid var(--trace-border);
  padding: 9px;
}

.trace-tool-body span {
  color: var(--trace-muted);
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
}

.trace-tool-body pre,
.trace-json {
  max-height: 220px;
  overflow: auto;
  margin: 0;
  border: 1px solid var(--trace-border);
  border-radius: 8px;
  background: var(--trace-code-bg);
  padding: 10px;
  color: var(--trace-code-text);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.trace-inline-empty {
  border: 1px dashed var(--trace-border);
  border-radius: 8px;
  padding: 12px;
  color: var(--trace-muted);
  font-size: 12px;
  text-align: center;
}

@media (max-width: 980px) {
  .trace-body-grid {
    grid-template-columns: minmax(0, 1fr);
    overflow: visible;
  }

  .trace-runs-workbench,
  .trace-detail-panel {
    grid-column: 1;
    grid-row: auto;
  }

  .trace-content-layout.trace-inspector-grid {
    grid-template-columns: minmax(0, 1fr);
    overflow: auto;
  }

  .trace-inspector-primary {
    border-right: 0;
    border-bottom: 1px solid var(--trace-border);
  }

  .trace-run-row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
