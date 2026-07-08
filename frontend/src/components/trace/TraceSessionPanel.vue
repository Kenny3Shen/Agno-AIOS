<template>
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
      <el-skeleton v-if="loadingSessions && !sessions.length" :rows="sessionPageSize" animated />
      <template v-else>
        <button
          v-for="session in pagedSessions"
          :key="session.session_id"
          type="button"
          class="trace-session-card"
          :class="{ active: selectedSessionId === session.session_id }"
          @click="emit('selectSession', session)"
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
        v-if="filteredSessions.length > sessionPageSize"
        :current-page="sessionPage"
        class="trace-session-pagination"
        :page-size="sessionPageSize"
        :pager-count="5"
        :total="filteredSessions.length"
        layout="prev, pager, next"
        small
        @update:current-page="emit('update:sessionPage', $event)"
      />

      <div v-if="!filteredSessions.length && !loadingSessions" class="empty-observe trace-session-empty">
        <el-icon><Connection /></el-icon>
        <strong>{{ t('trace.empty.noSessionsTitle') }}</strong>
        <span>{{ t('trace.empty.noSessionsDescription') }}</span>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { Connection } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import {
  compactTraceId,
  formatTraceSessionTime,
} from "../../modules/traceWorkbench"
import type { ChatSession } from "../../types"

defineProps<{
  sessions: ChatSession[]
  filteredSessions: ChatSession[]
  pagedSessions: ChatSession[]
  selectedSessionId: string | null
  sessionPage: number
  sessionPageSize: number
  loadingSessions: boolean
}>()

const emit = defineEmits<{
  "update:sessionPage": [value: number]
  selectSession: [session: ChatSession]
}>()

const { t } = useI18n()
const compactId = compactTraceId
const formatSessionTime = formatTraceSessionTime
</script>
