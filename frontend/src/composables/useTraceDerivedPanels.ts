import { computed, type ComputedRef, type Ref } from "vue"
import {
  buildTraceLogItems,
  buildTraceMetadataItems,
  buildTraceOverviewItems,
  buildTraceRunRows,
  buildTraceToolCallItems,
  emptyTraceParsedSpan,
  filterTraceRunRows,
  findTraceRunRow,
  traceRunMetrics,
  type TraceOwnerLabels,
  type TraceRunFilters,
} from "../modules/traceWorkbench"
import type { ChatSession, SpanItem, TraceItem } from "../types"

interface UseTraceDerivedPanelsParams {
  sessionTraceItems: Ref<TraceItem[]>
  selectedSession: ComputedRef<ChatSession | null>
  selectedSessionId: Ref<string | null>
  runFilters: TraceRunFilters
  selectedTrace: Ref<TraceItem | null>
  selectedSpan: Ref<SpanItem | null>
  spans: Ref<SpanItem[]>
  formatAnyDateTime: (value?: unknown) => string
  labels: TraceOwnerLabels
}

export const useTraceDerivedPanels = ({
  sessionTraceItems,
  selectedSession,
  selectedSessionId,
  runFilters,
  selectedTrace,
  selectedSpan,
  spans,
  formatAnyDateTime,
  labels,
}: UseTraceDerivedPanelsParams) => {
  const runRows = computed(() => buildTraceRunRows({
    traces: sessionTraceItems.value,
    selectedSession: selectedSession.value,
    selectedSessionId: selectedSessionId.value,
    labels,
  }))

  const filteredRunRows = computed(() => filterTraceRunRows(runRows.value, runFilters))

  const selectedRunRow = computed(() => findTraceRunRow(filteredRunRows.value, selectedTrace.value?.trace_id))

  const selectedRunMetrics = computed<Record<string, unknown>>(() => traceRunMetrics(selectedRunRow.value))

  const parsedSpan = computed(() => selectedSpan.value?.parsed || emptyTraceParsedSpan)

  const overviewItems = computed(() => buildTraceOverviewItems({
    trace: selectedTrace.value,
    run: selectedRunRow.value?.run,
    span: selectedSpan.value,
    parsedSpan: parsedSpan.value,
    metrics: selectedRunMetrics.value,
  }))

  const traceMetadataItems = computed(() => buildTraceMetadataItems({
    trace: selectedTrace.value,
    run: selectedRunRow.value?.run,
    session: selectedSession.value,
    row: selectedRunRow.value,
    span: selectedSpan.value,
    formatAnyDateTime,
  }))

  const toolCallItems = computed(() => buildTraceToolCallItems(spans.value))

  const logItems = computed(() => buildTraceLogItems({
    parsedEvents: parsedSpan.value.events || [],
    rawEvents: selectedSpan.value?.events || [],
  }))

  return {
    runRows,
    filteredRunRows,
    selectedRunRow,
    selectedRunMetrics,
    parsedSpan,
    overviewItems,
    traceMetadataItems,
    toolCallItems,
    logItems,
  }
}
