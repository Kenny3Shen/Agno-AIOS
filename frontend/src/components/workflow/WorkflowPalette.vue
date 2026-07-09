<template>
  <aside :aria-label="t('workflow.palette.title')">
    <section class="grid gap-2.5">
      <SectionHeader :title="t('workflow.config.title')" :subtitle="t('workflow.config.description')" />
      <el-input v-model="workflowNameModel" size="small" :placeholder="t('workflow.config.namePlaceholder')" />
      <el-input v-model="workflowDescriptionModel" size="small" type="textarea" :rows="3" :placeholder="t('workflow.config.descriptionPlaceholder')" />
      <el-input v-model="runInputModel" size="small" type="textarea" :rows="4" :placeholder="t('workflow.config.inputPlaceholder')" />
      <el-input v-model="sessionIdModel" size="small" :placeholder="t('workflow.config.sessionPlaceholder')" />
    </section>

    <section class="mt-4.5 grid gap-2.5">
      <SectionHeader :title="t('workflow.palette.stepTypesTitle')" :subtitle="t('workflow.palette.stepTypesDescription')" />
      <button
        v-for="stepType in stepTypes"
        :key="stepType.type"
        type="button"
        class="soc-focus grid w-full grid-cols-[34px_minmax(0,1fr)_18px] items-start gap-2.5 rounded-2 border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] p-2.5 text-left text-inherit transition duration-180 hover:-translate-y-0.25 hover:border-[color-mix(in_srgb,var(--ag-green)_42%,var(--ag-border))] hover:bg-[var(--ag-green-soft)]"
        @click="emit('addStep', stepType.type)"
      >
        <span class="grid h-7.5 w-7.5 place-items-center rounded-2 border border-[var(--ag-border)] bg-[var(--ag-panel)] font-mono text-[10px] font-800 text-[var(--ag-blue)]">
          {{ stepType.badge }}
        </span>
        <span class="grid min-w-0 gap-1">
          <strong class="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[13px] leading-snug text-[var(--ag-heading)]">{{ stepType.label }}</strong>
          <em class="line-clamp-2 text-xs not-italic leading-snug text-[var(--ag-muted)]">{{ stepType.description }}</em>
        </span>
        <el-icon class="mt-1 text-[var(--ag-muted)]"><Plus /></el-icon>
      </button>
    </section>

    <section class="mt-4.5 grid gap-2.5">
      <SectionHeader :title="t('workflow.palette.executorsTitle')" :subtitle="t('workflow.palette.executorsDescription')" />
      <button
        v-for="executor in executorTypes"
        :key="executor.type"
        type="button"
        class="soc-focus grid w-full grid-cols-[34px_minmax(0,1fr)] items-start gap-2.5 rounded-2 border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] p-2.5 text-left text-inherit transition duration-180 hover:-translate-y-0.25 hover:border-[color-mix(in_srgb,var(--ag-blue)_42%,var(--ag-border))] hover:bg-[var(--ag-blue-soft)]"
        @click="emit('applyExecutor', executor.type)"
      >
        <span class="grid h-7.5 w-7.5 place-items-center rounded-2 border border-[var(--ag-border)] bg-[var(--ag-panel)] font-mono text-[10px] font-800 text-[var(--ag-blue)]">
          {{ executor.badge }}
        </span>
        <span class="grid min-w-0 gap-1">
          <strong class="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[13px] leading-snug text-[var(--ag-heading)]">{{ executor.label }}</strong>
          <em class="line-clamp-2 text-xs not-italic leading-snug text-[var(--ag-muted)]">{{ executor.description }}</em>
        </span>
      </button>
    </section>
  </aside>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { Plus } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import SectionHeader from "../common/SectionHeader.vue"
import type { WorkflowExecutorType, WorkflowStepKind } from "../../modules/workflowBuilder"

interface WorkflowOption<TType extends string> {
  type: TType
  badge: string
  label: string
  description: string
}

const props = defineProps<{
  workflowName: string
  workflowDescription: string
  runInput: string
  sessionId: string
  stepTypes: WorkflowOption<WorkflowStepKind>[]
  executorTypes: WorkflowOption<WorkflowExecutorType>[]
}>()

const emit = defineEmits<{
  "update:workflowName": [value: string]
  "update:workflowDescription": [value: string]
  "update:runInput": [value: string]
  "update:sessionId": [value: string]
  addStep: [kind: WorkflowStepKind]
  applyExecutor: [executor: WorkflowExecutorType]
}>()

const { t } = useI18n()

const workflowNameModel = computed({
  get: () => props.workflowName,
  set: (value) => emit("update:workflowName", value),
})
const workflowDescriptionModel = computed({
  get: () => props.workflowDescription,
  set: (value) => emit("update:workflowDescription", value),
})
const runInputModel = computed({
  get: () => props.runInput,
  set: (value) => emit("update:runInput", value),
})
const sessionIdModel = computed({
  get: () => props.sessionId,
  set: (value) => emit("update:sessionId", value),
})
</script>
