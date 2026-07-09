<template>
  <div class="workflow-console ag-page-flow text-[var(--ag-text)]">
    <header class="workflow-header ag-content-panel grid items-center gap-4 xl:grid-cols-[minmax(0,1fr)_auto]">
      <div class="workflow-context flex min-w-0 flex-wrap gap-2" :aria-label="t('workflow.stats.ariaLabel')">
        <MetricChip v-for="stat in stats" :key="stat.label" :label="stat.label" :value="stat.value" />
        <StatusChip tone="green">
          <el-icon><Connection /></el-icon>
          {{ t("workflow.canvas.runtime") }}
        </StatusChip>
      </div>

      <div class="workflow-actions flex flex-wrap items-center gap-2 xl:justify-end">
        <el-button size="small" plain @click="validateWorkflow">
          <el-icon><Check /></el-icon>
          {{ t("workflow.actions.validate") }}
        </el-button>
        <el-button size="small" plain @click="copyCode">
          <el-icon><CopyDocument /></el-icon>
          {{ t("workflow.actions.copyCode") }}
        </el-button>
        <el-button size="small" type="primary" @click="saveDraft">
          <el-icon><DocumentChecked /></el-icon>
          {{ t("workflow.actions.saveDraft") }}
        </el-button>
      </div>
    </header>

    <div class="workflow-workbench ag-workspace-panel grid min-h-0 flex-1 overflow-hidden xl:grid-cols-[320px_minmax(0,1fr)_380px] lg:grid-cols-[280px_minmax(0,1fr)] max-lg:overflow-visible max-lg:grid-cols-1">
      <WorkflowPalette
        v-model:workflow-name="workflowName"
        v-model:workflow-description="workflowDescription"
        v-model:run-input="runInput"
        v-model:session-id="sessionId"
        class="workflow-palette workflow-panel hidden min-h-0 overflow-auto border-r border-[var(--ag-border)] bg-[var(--ag-panel)] p-3.5 lg:block"
        :step-types="stepTypes"
        :executor-types="executorTypes"
        @add-step="addStep"
        @apply-executor="applyExecutor"
      />

      <WorkflowCanvas
        class="workflow-canvas workflow-panel min-h-0 overflow-hidden border-r border-[var(--ag-border)] bg-[var(--ag-frame)]"
        :workflow-name="workflowName"
        :workflow-description="workflowDescription"
        :steps="workflowSteps"
        :selected-step-id="selectedStepId"
        :output-items="outputItems"
        :step-count="workflowSteps.length"
        :step-types="stepTypes"
        :executor-types="executorTypes"
        @run-preview="runPreview"
        @select-step="selectStep"
        @move-step="moveStep"
        @remove-step="removeStep"
      />

      <WorkflowInspector
        v-model:active-tab="activeInspectorTab"
        v-model:user-id="userId"
        v-model:num-history-runs="numHistoryRuns"
        v-model:stream-events="streamEvents"
        v-model:store-events="storeEvents"
        v-model:add-workflow-history-to-steps="addWorkflowHistoryToSteps"
        class="workflow-inspector workflow-panel ag-right-panel min-h-0 overflow-auto border-l border-[var(--ag-border)] bg-[var(--ag-panel)] p-3.5 lg:col-span-2 lg:mx-3 lg:mb-3 lg:border-l-0 xl:col-span-1 xl:my-3 xl:ml-0 xl:mr-3 xl:border-l"
        :selected-step="selectedStep"
        :step-types="stepTypes"
        :executor-types="executorTypes"
        :validation-title="validationTitle"
        :validation-items="validationItems"
        :session-items="sessionItems"
        :generated-code="generatedCode"
        @copy-code="copyCode"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue"
import {
  Check,
  Connection,
  CopyDocument,
  DocumentChecked,
} from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import MetricChip from "./common/MetricChip.vue"
import StatusChip from "./common/StatusChip.vue"
import WorkflowCanvas from "./workflow/WorkflowCanvas.vue"
import WorkflowInspector from "./workflow/WorkflowInspector.vue"
import WorkflowPalette from "./workflow/WorkflowPalette.vue"
import {
  buildWorkflowCode,
  workflowNameSymbol,
  workflowStepSymbol,
  type WorkflowCodeOptions,
  type WorkflowExecutorType,
  type WorkflowStepDraft,
  type WorkflowStepKind,
} from "../modules/workflowBuilder"

type Tone = "blue" | "green" | "yellow" | "red" | "purple"
type ValidationLevel = "ok" | "warning"

interface WorkflowStep extends WorkflowStepDraft {
  tone: Tone
}

const { t } = useI18n()

const workflowName = ref("security_research_workflow")
const workflowDescription = ref(t("workflow.canvas.description"))
const runInput = ref(t("workflow.config.defaultInput"))
const sessionId = ref("security-research-session")
const userId = ref("operator@example.com")
const selectedStepId = ref("intake")
const activeInspectorTab = ref("edit")
const lastRunId = ref("wf-run-preview")
const lastSavedAt = ref("")
const streamEvents = ref(true)
const storeEvents = ref(true)
const addWorkflowHistoryToSteps = ref(true)
const numHistoryRuns = ref(3)

const workflowSteps = ref<WorkflowStep[]>([
  {
    id: "intake",
    kind: "step",
    executor: "agent",
    name: t("workflow.sample.intake"),
    symbol: "intake",
    description: t("workflow.sample.intakeDescription"),
    expression: "",
    maxIterations: 1,
    branches: 1,
    tone: "blue",
  },
  {
    id: "research",
    kind: "parallel",
    executor: "team",
    name: t("workflow.sample.research"),
    symbol: "research",
    description: t("workflow.sample.researchDescription"),
    expression: "fanout=[cve_context, exposure_context, knowledge_context]",
    maxIterations: 1,
    branches: 3,
    tone: "green",
  },
  {
    id: "route",
    kind: "router",
    executor: "function",
    name: t("workflow.sample.route"),
    symbol: "route",
    description: t("workflow.sample.routeDescription"),
    expression: "last_step_content.contains('critical')",
    maxIterations: 1,
    branches: 2,
    tone: "yellow",
  },
  {
    id: "persist",
    kind: "step",
    executor: "function",
    name: t("workflow.sample.persist"),
    symbol: "persist",
    description: t("workflow.sample.persistDescription"),
    expression: "",
    maxIterations: 1,
    branches: 1,
    tone: "purple",
  },
])

const toneByKind: Record<WorkflowStepKind, Tone> = {
  step: "blue",
  steps: "purple",
  condition: "red",
  loop: "yellow",
  router: "yellow",
  parallel: "green",
}

const stats = computed(() => [
  { label: t("workflow.stats.executors"), value: String(new Set(workflowSteps.value.map((step) => step.executor)).size) },
  { label: t("workflow.stats.stepTypes"), value: String(new Set(workflowSteps.value.map((step) => step.kind)).size) },
  { label: t("workflow.stats.persistence"), value: lastSavedAt.value || t("workflow.stats.persisted") },
])

const executorTypes = computed<Array<{ type: WorkflowExecutorType; badge: string; label: string; description: string }>>(() => [
  { type: "agent", badge: "AG", label: t("workflow.executors.agent"), description: t("workflow.executors.agentDescription") },
  { type: "team", badge: "TM", label: t("workflow.executors.team"), description: t("workflow.executors.teamDescription") },
  { type: "function", badge: "FN", label: t("workflow.executors.function"), description: t("workflow.executors.functionDescription") },
  { type: "workflow", badge: "WF", label: t("workflow.executors.workflow"), description: t("workflow.executors.workflowDescription") },
])

const stepTypes = computed<Array<{ type: WorkflowStepKind; badge: string; label: string; description: string }>>(() => [
  { type: "step", badge: "ST", label: t("workflow.stepTypes.step"), description: t("workflow.stepTypes.stepDescription") },
  { type: "steps", badge: "SQ", label: t("workflow.stepTypes.steps"), description: t("workflow.stepTypes.stepsDescription") },
  { type: "condition", badge: "IF", label: t("workflow.stepTypes.condition"), description: t("workflow.stepTypes.conditionDescription") },
  { type: "loop", badge: "LP", label: t("workflow.stepTypes.loop"), description: t("workflow.stepTypes.loopDescription") },
  { type: "router", badge: "RT", label: t("workflow.stepTypes.router"), description: t("workflow.stepTypes.routerDescription") },
  { type: "parallel", badge: "||", label: t("workflow.stepTypes.parallel"), description: t("workflow.stepTypes.parallelDescription") },
])

const selectedStep = computed(() => workflowSteps.value.find((step) => step.id === selectedStepId.value))

const validationItems = computed<Array<{ level: ValidationLevel; message: string }>>(() => {
  const items: Array<{ level: ValidationLevel; message: string }> = []
  const names = workflowSteps.value.map((step) => step.name.trim().toLowerCase()).filter(Boolean)
  const symbols = workflowSteps.value.map((step) => workflowStepSymbol(step))
  const duplicateName = names.some((name, index) => names.indexOf(name) !== index)
  const duplicateSymbol = symbols.some((symbol, index) => symbols.indexOf(symbol) !== index)

  if (workflowName.value.trim()) items.push({ level: "ok", message: t("workflow.validation.named") })
  else items.push({ level: "warning", message: t("workflow.validation.nameMissing") })

  if (workflowSteps.value.length > 0) items.push({ level: "ok", message: t("workflow.validation.hasSteps", { count: workflowSteps.value.length }) })
  else items.push({ level: "warning", message: t("workflow.validation.noSteps") })

  if (!duplicateName) items.push({ level: "ok", message: t("workflow.validation.uniqueNames") })
  else items.push({ level: "warning", message: t("workflow.validation.duplicateNames") })

  if (!duplicateSymbol) items.push({ level: "ok", message: t("workflow.validation.uniqueSymbols") })
  else items.push({ level: "warning", message: t("workflow.validation.duplicateSymbols") })

  for (const step of workflowSteps.value) {
    if ((step.kind === "condition" || step.kind === "router" || step.kind === "loop") && !step.expression.trim()) {
      items.push({ level: "warning", message: t("workflow.validation.expressionMissing", { name: step.name }) })
    }
    if ((step.kind === "parallel" || step.kind === "router" || step.kind === "condition" || step.kind === "steps") && step.branches < 2) {
      items.push({ level: "warning", message: t("workflow.validation.branchesMissing", { name: step.name }) })
    }
  }

  if (items.every((item) => item.level === "ok")) {
    items.push({ level: "ok", message: t("workflow.validation.ready") })
  }

  return items
})

const validationTitle = computed(() => {
  const warnings = validationItems.value.filter((item) => item.level === "warning").length
  return warnings ? t("workflow.validation.warningTitle", { count: warnings }) : t("workflow.validation.readyTitle")
})

const outputItems = computed(() => [
  { label: t("workflow.outputs.input"), value: "workflow.print_response(..., session_id=...)" },
  { label: t("workflow.outputs.stepResults"), value: t("workflow.outputs.stepCount", { count: workflowSteps.value.length }) },
  { label: t("workflow.outputs.events"), value: streamEvents.value ? "stream_events=True" : "stream_events=False" },
  { label: t("workflow.outputs.finalOutput"), value: lastRunId.value },
])

const sessionItems = computed(() => [
  t("workflow.inspector.sessionRun"),
  t("workflow.inspector.sessionSteps"),
  t("workflow.inspector.sessionState"),
])

const generatedCode = computed(() => {
  const options: WorkflowCodeOptions = {
    name: workflowName.value || "security_research_workflow",
    description: workflowDescription.value || t("workflow.canvas.description"),
    input: runInput.value || t("workflow.config.defaultInput"),
    sessionId: sessionId.value,
    userId: userId.value,
    steps: workflowSteps.value,
    streamEvents: streamEvents.value,
    storeEvents: storeEvents.value,
    addWorkflowHistoryToSteps: addWorkflowHistoryToSteps.value,
    numHistoryRuns: numHistoryRuns.value,
  }
  return buildWorkflowCode(options)
})

function selectStep(id: string) {
  selectedStepId.value = id
  activeInspectorTab.value = "edit"
}

function addStep(kind: WorkflowStepKind) {
  const index = workflowSteps.value.length + 1
  const step: WorkflowStep = {
    id: `step-${Date.now()}`,
    kind,
    executor: kind === "step" ? "agent" : "function",
    name: t("workflow.editor.defaultStepName", { index }),
    symbol: `workflow_step_${index}`,
    description: stepLabel(kind),
    expression: defaultExpression(kind),
    maxIterations: kind === "loop" ? 3 : 1,
    branches: kind === "parallel" ? 3 : kind === "step" || kind === "loop" ? 1 : 2,
    tone: toneByKind[kind],
  }
  workflowSteps.value.push(step)
  selectedStepId.value = step.id
}

function applyExecutor(executor: WorkflowExecutorType) {
  if (!selectedStep.value) return
  selectedStep.value.executor = executor
}

function moveStep(index: number, direction: -1 | 1) {
  const nextIndex = index + direction
  if (nextIndex < 0 || nextIndex >= workflowSteps.value.length) return
  const steps = [...workflowSteps.value]
  const [step] = steps.splice(index, 1)
  steps.splice(nextIndex, 0, step)
  workflowSteps.value = steps
}

function removeStep(id: string) {
  workflowSteps.value = workflowSteps.value.filter((step) => step.id !== id)
  if (selectedStepId.value === id) {
    selectedStepId.value = workflowSteps.value[0]?.id || ""
  }
}

function validateWorkflow() {
  activeInspectorTab.value = "validate"
}

function runPreview() {
  const safeName = workflowNameSymbol(workflowName.value || "workflow")
  lastRunId.value = `${safeName}-${Date.now().toString().slice(-6)}`
}

async function copyCode() {
  activeInspectorTab.value = "preview"
  if (navigator?.clipboard) {
    await navigator.clipboard.writeText(generatedCode.value)
  }
}

function saveDraft() {
  lastSavedAt.value = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(new Date())
}

function stepLabel(kind: WorkflowStepKind) {
  return stepTypes.value.find((stepType) => stepType.type === kind)?.label || kind
}

function defaultExpression(kind: WorkflowStepKind) {
  if (kind === "condition") return "last_step_content.contains('critical')"
  if (kind === "loop") return "last_step_content.contains('APPROVED')"
  if (kind === "router") return "last_step_content.contains('critical')"
  if (kind === "parallel") return "fanout=[branch_a, branch_b]"
  if (kind === "steps") return "ordered_steps"
  return ""
}

</script>
