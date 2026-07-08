<template>
  <section class="trace-runs-workbench relative flex min-h-0 flex-1 flex-col overflow-hidden">
    <div class="trace-runs-toolbar trace-toolbar grid gap-3">
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

    <div v-else class="trace-runs-list grid min-h-0 content-start gap-[10px] overflow-auto p-[14px]">
      <button
        v-for="row in filteredRunRows"
        :key="row.key"
        type="button"
        class="trace-waterfall-row trace-run-row"
        :class="{ active: selectedTrace?.trace_id === row.trace.trace_id, error: row.trace.status === 'ERROR' }"
        @click="emit('openTraceDetail', row.trace.trace_id)"
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
</template>

<script setup lang="ts">
import { Aim, Connection } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import {
  compactTraceId,
  formatTraceDateTime,
  formatTraceDuration,
  traceDurationClass,
  traceStatusClass,
  traceStatusLabel,
  traceTagType,
  type TraceRunRow,
} from "../../modules/traceWorkbench"
import type { ChatSession, TraceItem } from "../../types"

defineProps<{
  filteredRunRows: TraceRunRow[]
  selectedSession: ChatSession | null
  selectedTrace: TraceItem | null
  loading: boolean
  apiError: string | null
}>()

const emit = defineEmits<{
  openTraceDetail: [traceId: string]
}>()

const { t } = useI18n()
const compactId = compactTraceId
const durationClass = traceDurationClass
const formatDateTime = formatTraceDateTime
const formatDuration = formatTraceDuration
const statusClass = traceStatusClass
const statusLabel = traceStatusLabel
const tagType = traceTagType
</script>
