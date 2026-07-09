<template>
  <article
    class="soc-focus relative grid w-[min(820px,100%)] cursor-pointer grid-cols-[36px_minmax(0,1fr)_auto] gap-3 rounded-2 border bg-[color-mix(in_srgb,var(--ag-panel)_92%,transparent)] p-3.5 shadow-[var(--ag-shadow-panel)]"
    :class="[toneClasses[step.tone], selected ? selectedToneClasses[step.tone] : '']"
    tabindex="0"
    @click="emit('select', step.id)"
    @keydown.enter="emit('select', step.id)"
  >
    <span v-if="index > 0" class="absolute -top-3.25 left-7.75 h-3 w-px bg-[var(--ag-border-strong)]" aria-hidden="true" />
    <span class="grid h-7.5 w-7.5 place-items-center rounded-2 border border-[var(--ag-border)] bg-[var(--ag-panel)] font-mono text-[10px] font-800" :class="toneTextClasses[step.tone]">
      {{ index + 1 }}
    </span>
    <div class="min-w-0">
      <StatusDot :label="stepLabel(step.kind)" :tone="dotTone(step.tone)">
        {{ stepLabel(step.kind) }}
      </StatusDot>
      <strong class="mt-1 block min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[13px] leading-snug text-[var(--ag-heading)]">
        {{ step.name || t("workflow.editor.untitled") }}
      </strong>
      <p class="mt-1 line-clamp-2 text-xs leading-snug text-[var(--ag-muted)]">
        {{ step.description || t("workflow.editor.emptyDescription") }}
      </p>
      <div class="mt-2.5 flex min-w-0 flex-wrap gap-1.5">
        <DataChip :label="t('workflow.editor.executor')" :value="executorLabel(step.executor)" />
        <DataChip :label="stepLabel(step.kind)" :value="stepMeta" />
        <DataChip v-if="step.branches > 1" :label="t('workflow.editor.branches')" :value="t('workflow.editor.branchesValue', { count: step.branches })" />
      </div>
      <div v-if="branchNames.length" class="mt-2.5 grid grid-cols-[repeat(auto-fit,minmax(86px,1fr))] gap-1.5 border-t border-[var(--ag-border)] pt-2.5" :aria-label="t('workflow.editor.branches')">
        <span
          v-for="branch in branchNames"
          :key="branch"
          class="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap rounded-2 border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] px-2 py-1.25 font-mono text-[10px] font-800 text-[var(--ag-muted-strong)]"
        >
          {{ branch }}
        </span>
      </div>
    </div>
    <div class="flex flex-col gap-0.5">
      <el-button :aria-label="t('workflow.actions.moveUp')" size="small" text :disabled="index === 0" @click.stop="emit('move', index, -1)">
        <el-icon><ArrowUp /></el-icon>
      </el-button>
      <el-button :aria-label="t('workflow.actions.moveDown')" size="small" text :disabled="isLast" @click.stop="emit('move', index, 1)">
        <el-icon><ArrowDown /></el-icon>
      </el-button>
      <el-button :aria-label="t('workflow.actions.remove')" size="small" text @click.stop="emit('remove', step.id)">
        <el-icon><Delete /></el-icon>
      </el-button>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { ArrowDown, ArrowUp, Delete } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import DataChip from "../common/DataChip.vue"
import StatusDot from "../common/StatusDot.vue"
import {
  constructorName,
  workflowStepSymbol,
  type WorkflowExecutorType,
  type WorkflowStepDraft,
  type WorkflowStepKind,
} from "../../modules/workflowBuilder"

type Tone = "blue" | "green" | "yellow" | "red" | "purple"
type DotTone = "blue" | "green" | "yellow" | "red" | "muted"

interface WorkflowStep extends WorkflowStepDraft {
  tone: Tone
}

interface WorkflowOption<TType extends string> {
  type: TType
  label: string
}

const props = defineProps<{
  step: WorkflowStep
  index: number
  selected: boolean
  isLast: boolean
  stepTypes: WorkflowOption<WorkflowStepKind>[]
  executorTypes: WorkflowOption<WorkflowExecutorType>[]
}>()

const emit = defineEmits<{
  select: [id: string]
  move: [index: number, direction: -1 | 1]
  remove: [id: string]
}>()

const { t } = useI18n()

const toneClasses: Record<Tone, string> = {
  blue: "border-[color-mix(in_srgb,var(--ag-blue)_32%,var(--ag-border))]",
  green: "border-[color-mix(in_srgb,var(--ag-green)_32%,var(--ag-border))]",
  yellow: "border-[color-mix(in_srgb,var(--ag-yellow)_38%,var(--ag-border))]",
  red: "border-[color-mix(in_srgb,var(--ag-red)_32%,var(--ag-border))]",
  purple: "border-[color-mix(in_srgb,var(--ag-purple)_34%,var(--ag-border))]",
}

const selectedToneClasses: Record<Tone, string> = {
  blue: "border-[var(--ag-blue)] bg-[color-mix(in_srgb,var(--ag-blue)_10%,var(--ag-panel))]",
  green: "border-[var(--ag-green)] bg-[color-mix(in_srgb,var(--ag-green)_10%,var(--ag-panel))]",
  yellow: "border-[var(--ag-yellow)] bg-[color-mix(in_srgb,var(--ag-yellow)_10%,var(--ag-panel))]",
  red: "border-[var(--ag-red)] bg-[color-mix(in_srgb,var(--ag-red)_10%,var(--ag-panel))]",
  purple: "border-[var(--ag-purple)] bg-[color-mix(in_srgb,var(--ag-purple)_10%,var(--ag-panel))]",
}

const toneTextClasses: Record<Tone, string> = {
  blue: "text-[var(--ag-blue)]",
  green: "text-[var(--ag-green)]",
  yellow: "text-[var(--ag-yellow)]",
  red: "text-[var(--ag-red)]",
  purple: "text-[var(--ag-purple)]",
}

const stepLabel = (kind: WorkflowStepKind) => props.stepTypes.find((stepType) => stepType.type === kind)?.label || kind
const executorLabel = (executor: WorkflowExecutorType) => props.executorTypes.find((executorType) => executorType.type === executor)?.label || executor
const dotTone = (tone: Tone): DotTone => tone === "purple" ? "blue" : tone

const stepMeta = computed(() => {
  if (props.step.kind === "loop") return t("workflow.editor.iterationsValue", { count: props.step.maxIterations })
  if (props.step.kind === "router" || props.step.kind === "condition") return props.step.expression || t("workflow.editor.needsExpression")
  if (props.step.kind === "parallel") return t("workflow.editor.parallelValue", { count: props.step.branches })
  if (props.step.kind === "steps") return t("workflow.editor.sequenceValue", { count: props.step.branches })
  return workflowStepSymbol(props.step)
})

const branchNames = computed(() => {
  if (props.step.kind !== "parallel" && props.step.kind !== "router" && props.step.kind !== "condition" && props.step.kind !== "steps") return []
  return Array.from({ length: props.step.branches }, (_, index) => `${constructorName(props.step.kind)} ${index + 1}`)
})
</script>
