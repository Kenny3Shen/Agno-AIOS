<template>
  <main class="grid grid-rows-[auto_minmax(0,1fr)_auto]">
    <header class="ag-panel-header flex items-start justify-between gap-3 border-b border-[var(--ag-border)] bg-[color-mix(in_srgb,var(--ag-panel)_92%,transparent)] p-3.5">
      <div class="min-w-0">
        <span class="font-mono text-[10px] font-800 uppercase text-[var(--ag-blue)]">{{ t("workflow.canvas.kicker") }}</span>
        <h3 class="mt-1 min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-base font-760 text-[var(--ag-heading)]">
          {{ workflowName || t("workflow.canvas.title") }}
        </h3>
        <p class="mt-1 line-clamp-2 text-xs leading-snug text-[var(--ag-muted)]">
          {{ workflowDescription || t("workflow.canvas.description") }}
        </p>
      </div>
      <div class="flex shrink-0 flex-wrap items-center justify-end gap-2">
        <StatusChip tone="green">
          <el-icon><Connection /></el-icon>
          {{ t("workflow.canvas.runtime") }}
        </StatusChip>
        <el-button size="small" type="primary" @click="emit('runPreview')">
          <el-icon><VideoPlay /></el-icon>
          {{ t("workflow.actions.runPreview") }}
        </el-button>
      </div>
    </header>

    <section
      class="grid min-h-0 content-start gap-3 overflow-auto bg-[linear-gradient(90deg,color-mix(in_srgb,var(--ag-border)_26%,transparent)_1px,transparent_1px),linear-gradient(180deg,color-mix(in_srgb,var(--ag-border)_20%,transparent)_1px,transparent_1px)] bg-[length:28px_28px] p-4.5"
      :aria-label="t('workflow.canvas.flowAriaLabel')"
    >
      <WorkflowStepCard
        v-for="(step, index) in steps"
        :key="step.id"
        :step="step"
        :index="index"
        :selected="selectedStepId === step.id"
        :is-last="index === steps.length - 1"
        :step-types="stepTypes"
        :executor-types="executorTypes"
        @select="emit('selectStep', $event)"
        @move="(index, direction) => emit('moveStep', index, direction)"
        @remove="emit('removeStep', $event)"
      />
    </section>

    <section class="grid grid-cols-4 gap-2.5 border-t border-[var(--ag-border)] bg-[color-mix(in_srgb,var(--ag-panel)_90%,transparent)] p-3.5 max-md:grid-cols-2" :aria-label="t('workflow.canvas.outputsAriaLabel')">
      <DataChip
        v-for="output in outputItems"
        :key="output.label"
        :label="output.label"
        :value="output.value"
        :title="`${output.label}: ${output.value}`"
      />
      <DataChip :label="t('workflow.outputs.stepResults')" :value="stepCount" tone="blue" class="sr-only" />
    </section>
  </main>
</template>

<script setup lang="ts">
import { Connection, VideoPlay } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import DataChip from "../common/DataChip.vue"
import StatusChip from "../common/StatusChip.vue"
import WorkflowStepCard from "./WorkflowStepCard.vue"
import type { WorkflowExecutorType, WorkflowStepDraft, WorkflowStepKind } from "../../modules/workflowBuilder"

type Tone = "blue" | "green" | "yellow" | "red" | "purple"

interface WorkflowStep extends WorkflowStepDraft {
  tone: Tone
}

interface WorkflowOption<TType extends string> {
  type: TType
  label: string
  badge?: string
  description?: string
}

defineProps<{
  workflowName: string
  workflowDescription: string
  steps: WorkflowStep[]
  selectedStepId: string
  outputItems: Array<{ label: string; value: string }>
  stepCount: number
  stepTypes: WorkflowOption<WorkflowStepKind>[]
  executorTypes: WorkflowOption<WorkflowExecutorType>[]
}>()

const emit = defineEmits<{
  runPreview: []
  selectStep: [id: string]
  moveStep: [index: number, direction: -1 | 1]
  removeStep: [id: string]
}>()

const { t } = useI18n()
</script>
