<template>
  <div class="grid min-w-0 gap-3">
    <SectionHeader :title="t('agentEvals.panels.failures')" :count="failures.length">
      <template #actions>
        <el-button size="small" type="primary" :disabled="!canRun || !selectedFailureReplayId" @click="$emit('replay')">
          <el-icon><RefreshRight /></el-icon>
          {{ t("agentEvals.actions.replay") }}
        </el-button>
      </template>
    </SectionHeader>

    <div v-if="failures.length" class="grid min-w-0 gap-2">
      <button
        v-for="failure in failures"
        :key="failure.id"
        type="button"
        class="ag-surface-row grid w-full cursor-pointer items-center gap-2 text-left md:grid-cols-[120px_minmax(0,1fr)_minmax(100px,0.45fr)_122px]"
        :class="{ 'border-[color-mix(in_srgb,var(--ag-blue)_58%,var(--ag-border))] bg-[var(--ag-blue-soft)]': selectedFailureId === failure.id }"
        @click="$emit('select-failure', failure.id)"
      >
        <StatusChip tone="red">{{ evalTypeLabel(failure.eval_type) }}</StatusChip>
        <strong class="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[13px] text-[var(--ag-heading)]" :title="failure.name || failure.run_id">
          {{ failure.name || failure.run_id }}
        </strong>
        <small class="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-xs text-[var(--ag-muted)]">
          {{ failure.agent_id || "-" }}
        </small>
        <small class="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-xs text-[var(--ag-muted)]">
          {{ formatTime(failure.created_at) }}
        </small>
      </button>
    </div>

    <div v-else-if="!loading" class="ag-empty-state">
      <strong class="text-[13px] text-[var(--ag-green)]">{{ t("agentEvals.empty.failuresTitle") }}</strong>
      <span class="max-w-[360px]">{{ t("agentEvals.empty.failuresDescription") }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { RefreshRight } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import SectionHeader from "../common/SectionHeader.vue"
import StatusChip from "../common/StatusChip.vue"
import type { AgentEvalAgnoRun } from "../../types"

defineProps<{
  failures: AgentEvalAgnoRun[]
  selectedFailureId: string | null
  selectedFailureReplayId: string
  loading: boolean
  canRun: boolean
  evalTypeLabel: (type: string) => string
  formatTime: (value?: string | number | null) => string
}>()

defineEmits<{
  "select-failure": [id: string]
  replay: []
}>()

const { t } = useI18n()
</script>
