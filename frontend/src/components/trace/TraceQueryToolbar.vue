<template>
  <div class="trace-query-toolbar ag-content-panel grid flex-none grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-[10px]">
    <div class="trace-query-primary flex min-w-0 flex-wrap items-center gap-2">
      <el-input
        v-model="sessionFilters.sessionId"
        size="small"
        clearable
        :placeholder="t('trace.filters.searchSessionId')"
        class="trace-filter-input wide"
        @keyup.enter="emit('refresh')"
      />
      <el-input
        v-model="runFilters.runId"
        size="small"
        clearable
        :placeholder="t('trace.filters.searchRunId')"
        class="trace-filter-input wide"
        @keyup.enter="emit('refreshAll')"
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
      <el-button size="small" plain class="cursor-pointer" @click="emit('update:advancedFiltersOpen', !advancedFiltersOpen)">
        {{ t('trace.filters.advanced') }}
      </el-button>
    </div>
    <div class="trace-filter-actions">
      <el-button size="small" plain class="cursor-pointer" :disabled="loading || loadingSessions" @click="emit('resetAllFilters')">
        {{ t('trace.actions.reset') }}
      </el-button>
      <el-button
        size="small"
        type="primary"
        :loading="loading || loadingSessions"
        class="cursor-pointer"
        :aria-label="t('trace.actions.refreshAll')"
        @click="emit('refresh')"
      >
        <el-icon><Refresh /></el-icon>
      </el-button>
    </div>
    <div v-if="advancedFiltersOpen" class="trace-advanced-filters col-span-full flex min-w-0 flex-wrap items-center gap-2">
      <el-input v-model="sessionFilters.userId" size="small" clearable :placeholder="t('trace.filters.userId')" class="trace-filter-input" @keyup.enter="emit('refreshAll')" />
      <el-input v-model="sessionFilters.keyword" size="small" clearable :placeholder="t('trace.filters.keyword')" class="trace-filter-input" @keyup.enter="emit('refreshAll')" />
      <el-select v-model="sessionFilters.status" size="small" :placeholder="t('trace.filters.sessionStatus')" class="trace-filter-select">
        <el-option :label="t('trace.filters.activeSessions')" value="active" />
        <el-option :label="t('trace.filters.archivedSessions')" value="archived" />
        <el-option :label="t('trace.filters.allSessions')" value="all" />
      </el-select>
      <el-input v-model="runFilters.agentId" size="small" clearable :placeholder="t('trace.filters.agentId')" class="trace-filter-input" @keyup.enter="emit('refreshAll')" />
      <el-input v-model="runFilters.teamId" size="small" clearable :placeholder="t('trace.filters.teamId')" class="trace-filter-input" @keyup.enter="emit('refreshAll')" />
      <el-input v-model="runFilters.workflowId" size="small" clearable :placeholder="t('trace.filters.workflowId')" class="trace-filter-input" @keyup.enter="emit('refreshAll')" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { Refresh } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import type { TraceRunFilters, TraceSessionFilters } from "../../modules/traceWorkbench"

defineProps<{
  sessionFilters: TraceSessionFilters
  runFilters: TraceRunFilters
  advancedFiltersOpen: boolean
  loading: boolean
  loadingSessions: boolean
}>()

const emit = defineEmits<{
  "update:advancedFiltersOpen": [value: boolean]
  refresh: []
  refreshAll: []
  resetAllFilters: []
}>()

const { t } = useI18n()
</script>
