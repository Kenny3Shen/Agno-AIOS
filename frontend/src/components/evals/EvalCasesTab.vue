<template>
  <div class="grid min-w-0 gap-3">
    <SectionHeader :title="t('agentEvals.panels.cases')" :subtitle="`${filteredCases.length} / ${caseRows.length}`">
      <template #actions>
        <el-button size="small" type="primary" :disabled="!canRun || !selectedSuiteId" @click="$emit('run-suite')">
          <el-icon><VideoPlay /></el-icon>
          {{ t("agentEvals.actions.runSuite") }}
        </el-button>
      </template>
    </SectionHeader>

    <div v-if="filteredCases.length" class="grid min-w-0 gap-2">
      <article
        v-for="item in filteredCases"
        :key="item.id"
        class="ag-surface-row grid cursor-pointer gap-2 lg:grid-cols-[minmax(180px,1fr)_minmax(240px,1.4fr)_auto]"
        :class="{ 'border-[color-mix(in_srgb,var(--ag-blue)_58%,var(--ag-border))] bg-[var(--ag-blue-soft)]': selectedCaseId === item.id }"
        @click="$emit('select-case', item.id)"
      >
        <div class="min-w-0">
          <strong class="block min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[13px] text-[var(--ag-heading)]" :title="item.name">
            {{ item.name }}
          </strong>
          <span class="block min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-xs text-[var(--ag-muted)]" :title="item.description">
            {{ item.description || item.input }}
          </span>
        </div>
        <div class="flex min-w-0 flex-wrap items-center gap-1.5">
          <DataChip :label="t('agentEvals.fields.suite')" :value="item.suite_name" :title="item.suite_name" />
          <StatusChip v-for="type in item.eval_types" :key="`${item.id}-${type}`" tone="blue">
            {{ evalTypeLabel(type) }}
          </StatusChip>
          <StatusChip :tone="statusTone(item.latest_status)">
            {{ item.latest_status || "unknown" }}
          </StatusChip>
          <DataChip :label="t('agentEvals.fields.targetAgent')" :value="item.target_agent_id || '-'" :title="item.target_agent_id" />
        </div>
        <div class="flex shrink-0 items-center gap-2 lg:justify-end">
          <el-tooltip :content="t('agentEvals.actions.runCase')" placement="top">
            <el-button circle size="small" :disabled="!canRun" :aria-label="t('agentEvals.actions.runCase')" @click.stop="$emit('run-case', item.id)">
              <el-icon><VideoPlay /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip v-if="canWrite" :content="t('agentEvals.actions.edit')" placement="top">
            <el-button circle size="small" :aria-label="t('agentEvals.actions.edit')" @click.stop="$emit('permission-notice')">
              <el-icon><Edit /></el-icon>
            </el-button>
          </el-tooltip>
        </div>
      </article>
    </div>

    <div v-else-if="!loading" class="ag-empty-state">
      <strong class="text-[13px] text-[var(--ag-heading)]">{{ t("agentEvals.empty.casesTitle") }}</strong>
      <span class="max-w-[360px]">{{ t("agentEvals.empty.casesDescription") }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Edit, VideoPlay } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import DataChip from "../common/DataChip.vue"
import SectionHeader from "../common/SectionHeader.vue"
import StatusChip from "../common/StatusChip.vue"
import type { EvalCaseRow } from "../../composables/useAgentEvalsWorkbench"
import type { EvalTone } from "../../modules/agentEvalsWorkbench"

defineProps<{
  caseRows: EvalCaseRow[]
  filteredCases: EvalCaseRow[]
  selectedCaseId: string | null
  loading: boolean
  canRun: boolean
  canWrite: boolean
  selectedSuiteId: string
  evalTypeLabel: (type: string) => string
  statusTone: (status?: string | null) => EvalTone
}>()

defineEmits<{
  "select-case": [id: string]
  "run-suite": []
  "run-case": [id: string]
  "permission-notice": []
}>()

const { t } = useI18n()
</script>
