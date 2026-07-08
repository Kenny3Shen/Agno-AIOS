<template>
  <div class="trace-console ag-page-flow">
    <div class="trace-workbench trace-session-workbench">
      <TraceQueryToolbar
        v-model:advanced-filters-open="traceAdvancedFiltersOpen"
        :session-filters="sessionFilters"
        :run-filters="runFilters"
        :loading="loading"
        :loading-sessions="loadingSessions"
        @refresh="refresh"
        @refresh-all="refreshAll"
        @reset-all-filters="resetAllFilters"
      />

      <div class="trace-body-grid ag-workspace-panel">
        <TraceSessionPanel
          v-model:session-page="sessionPage"
          :sessions="sessions"
          :filtered-sessions="filteredSessions"
          :paged-sessions="pagedSessions"
          :selected-session-id="selectedSessionId"
          :session-page-size="SESSION_PAGE_SIZE"
          :loading-sessions="loadingSessions"
          @select-session="selectSession"
        />

        <main class="trace-canvas">
          <TraceRunsPanel
            :filtered-run-rows="filteredRunRows"
            :selected-session="selectedSession"
            :selected-trace="selectedTrace"
            :loading="loading"
            :api-error="apiError"
            @open-trace-detail="openTraceDetail"
          />

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
                  <TraceSpanHierarchy
                    :tree="tree"
                    :spans="spans"
                    :selected-span="selectedSpan"
                    @select-span="selectSpan"
                    @node-click="onSpanNodeClick"
                  />
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
import { computed, reactive, ref } from "vue"
import { useI18n } from "vue-i18n"
import {
  Aim,
  CopyDocument,
  Cpu,
} from "@element-plus/icons-vue"
import TraceQueryToolbar from "./trace/TraceQueryToolbar.vue"
import TraceRunsPanel from "./trace/TraceRunsPanel.vue"
import TraceSessionPanel from "./trace/TraceSessionPanel.vue"
import TraceSpanHierarchy from "./trace/TraceSpanHierarchy.vue"
import { useChatHistory } from "../composables/useChatApi"
import { useTracingApi } from "../composables/useTraceApi"
import { useTraceDerivedPanels } from "../composables/useTraceDerivedPanels"
import { useTraceDetailViewport } from "../composables/useTraceDetailViewport"
import { useTraceExternalSelectionEvents } from "../composables/useTraceExternalSelectionEvents"
import { useTraceFilterRefreshScheduler } from "../composables/useTraceFilterRefreshScheduler"
import { useTraceFilterWatches } from "../composables/useTraceFilterWatches"
import { useTraceLifecycle } from "../composables/useTraceLifecycle"
import { useTracePayloadControls } from "../composables/useTracePayloadControls"
import { useTracePayloadRenderer } from "../composables/useTracePayloadRenderer"
import { useTraceSessionController } from "../composables/useTraceSessionController"
import { useTraceSessionList } from "../composables/useTraceSessionList"
import { useTraceSpanSelection } from "../composables/useTraceSpanSelection"
import {
  createTraceRunFilters,
  createTraceSessionFilters,
  formatTraceAnyDateTime,
  formatTraceDuration,
  traceDurationClass,
  traceStatusClass,
  traceStatusLabel,
  traceTagType,
  type TracePayloadViewMode,
  type TraceSummaryState,
} from "../modules/traceWorkbench"
import { useTraceStore } from "../stores/traces"
import type { ChatSession, SpanItem, SpanTreeNode, TraceItem } from "../types"

const { t } = useI18n()
const { loading, error, listTraces, getTrace } = useTracingApi()
const { loadingSessions, listSessions } = useChatHistory()

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
const traceAdvancedFiltersOpen = ref(false)
const sessionPage = ref(1)
const inputViewMode = ref<PayloadViewMode>("text")
const outputViewMode = ref<PayloadViewMode>("text")

const loadingDetail = ref(false)
const apiError = computed(() => error.value)

type PayloadViewMode = TracePayloadViewMode
const SESSION_PAGE_SIZE = 10
const durationClass = traceDurationClass
const formatDuration = formatTraceDuration
const statusClass = traceStatusClass
const statusLabel = traceStatusLabel
const tagType = traceTagType

const {
  filteredSessions,
  pagedSessions,
  selectedSession,
} = useTraceSessionList({
  sessions,
  sessionFilters,
  selectedSessionId,
  sessionPage,
  sessionPageSize: SESSION_PAGE_SIZE,
})

const formatAnyDateTime = formatTraceAnyDateTime

const {
  filteredRunRows,
  overviewItems,
  traceMetadataItems,
  toolCallItems,
  logItems,
  parsedSpan,
} = useTraceDerivedPanels({
  sessionTraceItems,
  selectedSession,
  selectedSessionId,
  runFilters,
  selectedTrace,
  selectedSpan,
  spans,
  formatAnyDateTime,
  labels: {
    agentId: t("trace.filters.agentId"),
    teamId: t("trace.filters.teamId"),
    workflowId: t("trace.filters.workflowId"),
  },
})

const {
  expandedPayloads,
  copyPayload,
  copyMetadataValue,
  togglePayloadExpanded,
} = useTracePayloadControls()

const {
  payloadTextForMode,
  renderPayloadMarkupForMode,
} = useTracePayloadRenderer()

const {
  activeDetailTab,
  selectSpan,
  onSpanNodeClick,
} = useTraceSpanSelection({ selectedSpan })

const { scrollDetailIntoView } = useTraceDetailViewport()

let refreshTraceView = async () => {}
let refreshTraceRuns = async () => {}

const {
  clearPendingFilterRefresh,
  scheduleSessionFilterRefresh,
  scheduleFilterRefresh,
} = useTraceFilterRefreshScheduler({
  selectedSession,
  refresh: () => refreshTraceView(),
  refreshRuns: () => refreshTraceRuns(),
})

const traceSessionController = useTraceSessionController({
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

refreshTraceView = traceSessionController.refresh
refreshTraceRuns = traceSessionController.refreshRuns

const {
  refresh,
  selectSession,
  selectSessionById,
  openTraceDetail,
  resetAllFilters,
  refreshAll,
} = traceSessionController

useTraceExternalSelectionEvents({
  openTraceDetail,
  selectSessionById,
})

useTraceFilterWatches({
  filteredSessions,
  sessionPage,
  sessionFilters,
  runFilters,
  sessionPageSize: SESSION_PAGE_SIZE,
  scheduleSessionFilterRefresh,
  scheduleFilterRefresh,
})

useTraceLifecycle({
  refresh,
  clearPendingFilterRefresh,
})
</script>

<style src="../styles/trace.css"></style>
