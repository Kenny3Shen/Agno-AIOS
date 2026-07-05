<template>
  <div class="workflow-console">
    <header class="workflow-header">
      <div class="workflow-title">
        <span class="workflow-kicker">{{ t("workflow.kicker") }}</span>
        <h2>{{ t("workflow.title") }}</h2>
        <p>{{ t("workflow.description") }}</p>
      </div>

      <section class="workflow-stat-strip ag-stat-strip" :aria-label="t('workflow.stats.ariaLabel')">
        <article v-for="stat in stats" :key="stat.label" class="workflow-stat-chip ag-stat-chip">
          <span>{{ stat.label }}</span>
          <strong>{{ stat.value }}</strong>
        </article>
      </section>

      <div class="workflow-actions">
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

    <div class="workflow-workbench">
      <aside class="workflow-palette workflow-panel" :aria-label="t('workflow.palette.title')">
        <section class="workflow-config">
          <div class="workflow-section-head">
            <p>{{ t("workflow.config.title") }}</p>
            <span>{{ t("workflow.config.description") }}</span>
          </div>
          <el-input v-model="workflowName" size="small" :placeholder="t('workflow.config.namePlaceholder')" />
          <el-input v-model="workflowDescription" size="small" type="textarea" :rows="3" :placeholder="t('workflow.config.descriptionPlaceholder')" />
          <el-input v-model="runInput" size="small" type="textarea" :rows="4" :placeholder="t('workflow.config.inputPlaceholder')" />
          <el-input v-model="sessionId" size="small" :placeholder="t('workflow.config.sessionPlaceholder')" />
        </section>

        <section class="workflow-palette-section">
          <div class="workflow-section-head">
            <p>{{ t("workflow.palette.stepTypesTitle") }}</p>
            <span>{{ t("workflow.palette.stepTypesDescription") }}</span>
          </div>
          <button
            v-for="stepType in stepTypes"
            :key="stepType.type"
            type="button"
            class="workflow-library-item workflow-step-type soc-focus"
            @click="addStep(stepType.type)"
          >
            <span class="workflow-badge">{{ stepType.badge }}</span>
            <span class="workflow-library-copy">
              <strong>{{ stepType.label }}</strong>
              <em>{{ stepType.description }}</em>
            </span>
            <el-icon><Plus /></el-icon>
          </button>
        </section>

        <section class="workflow-palette-section">
          <div class="workflow-section-head">
            <p>{{ t("workflow.palette.executorsTitle") }}</p>
            <span>{{ t("workflow.palette.executorsDescription") }}</span>
          </div>
          <button
            v-for="executor in executorTypes"
            :key="executor.type"
            type="button"
            class="workflow-library-item soc-focus"
            @click="applyExecutor(executor.type)"
          >
            <span class="workflow-badge">{{ executor.badge }}</span>
            <span class="workflow-library-copy">
              <strong>{{ executor.label }}</strong>
              <em>{{ executor.description }}</em>
            </span>
          </button>
        </section>
      </aside>

      <main class="workflow-canvas workflow-panel">
        <div class="workflow-canvas-head">
          <div>
            <span class="workflow-kicker">{{ t("workflow.canvas.kicker") }}</span>
            <h3>{{ workflowName || t("workflow.canvas.title") }}</h3>
            <p>{{ workflowDescription || t("workflow.canvas.description") }}</p>
          </div>
          <div class="workflow-canvas-actions">
            <span class="workflow-runtime-chip">
              <el-icon><Connection /></el-icon>
              {{ t("workflow.canvas.runtime") }}
            </span>
            <el-button size="small" type="primary" @click="runPreview">
              <el-icon><VideoPlay /></el-icon>
              {{ t("workflow.actions.runPreview") }}
            </el-button>
          </div>
        </div>

        <section class="workflow-flow" :aria-label="t('workflow.canvas.flowAriaLabel')">
          <article
            v-for="(step, index) in workflowSteps"
            :key="step.id"
            class="workflow-board-step soc-focus"
            :class="[`tone-${step.tone}`, { 'is-selected': selectedStepId === step.id }]"
            tabindex="0"
            @click="selectStep(step.id)"
            @keydown.enter="selectStep(step.id)"
          >
            <span v-if="index > 0" class="workflow-connector" aria-hidden="true" />
            <div class="workflow-step-index">{{ index + 1 }}</div>
            <div class="workflow-step-copy">
              <span>{{ stepLabel(step.kind) }}</span>
              <strong>{{ step.name || t("workflow.editor.untitled") }}</strong>
              <p>{{ step.description || t("workflow.editor.emptyDescription") }}</p>
              <div class="workflow-step-meta">
                <em>{{ executorLabel(step.executor) }}</em>
                <em>{{ stepMeta(step) }}</em>
                <em v-if="step.branches > 1">{{ t("workflow.editor.branchesValue", { count: step.branches }) }}</em>
              </div>
              <div v-if="branchLabels(step).length" class="workflow-branch-rail" :aria-label="t('workflow.editor.branches')">
                <span v-for="branch in branchLabels(step)" :key="branch">{{ branch }}</span>
              </div>
            </div>
            <div class="workflow-step-actions">
              <el-button :aria-label="t('workflow.actions.moveUp')" size="small" text :disabled="index === 0" @click.stop="moveStep(index, -1)">
                <el-icon><ArrowUp /></el-icon>
              </el-button>
              <el-button :aria-label="t('workflow.actions.moveDown')" size="small" text :disabled="index === workflowSteps.length - 1" @click.stop="moveStep(index, 1)">
                <el-icon><ArrowDown /></el-icon>
              </el-button>
              <el-button :aria-label="t('workflow.actions.remove')" size="small" text @click.stop="removeStep(step.id)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </article>
        </section>

        <section class="workflow-result-strip" :aria-label="t('workflow.canvas.outputsAriaLabel')">
          <article v-for="output in outputItems" :key="output.label" class="workflow-output">
            <span>{{ output.label }}</span>
            <strong>{{ output.value }}</strong>
          </article>
        </section>
      </main>

      <aside class="workflow-inspector workflow-panel" :aria-label="t('workflow.inspector.title')">
        <div class="workflow-section-head">
          <p>{{ t("workflow.inspector.title") }}</p>
          <span>{{ t("workflow.inspector.description") }}</span>
        </div>

        <el-tabs v-model="activeInspectorTab" class="workflow-tabs">
          <el-tab-pane :label="t('workflow.inspector.editTab')" name="edit">
            <section v-if="selectedStep" class="workflow-inspector-section workflow-editor">
              <h4>{{ t("workflow.editor.title") }}</h4>
              <label>
                <span>{{ t("workflow.editor.name") }}</span>
                <el-input v-model="selectedStep.name" size="small" />
              </label>
              <label>
                <span>{{ t("workflow.editor.symbol") }}</span>
                <el-input v-model="selectedStep.symbol" size="small" />
              </label>
              <label>
                <span>{{ t("workflow.editor.description") }}</span>
                <el-input v-model="selectedStep.description" size="small" type="textarea" :rows="3" />
              </label>
              <label>
                <span>{{ t("workflow.editor.stepType") }}</span>
                <el-select v-model="selectedStep.kind" size="small">
                  <el-option v-for="option in stepTypes" :key="option.type" :label="option.label" :value="option.type" />
                </el-select>
              </label>
              <label>
                <span>{{ t("workflow.editor.executor") }}</span>
                <el-select v-model="selectedStep.executor" size="small">
                  <el-option v-for="option in executorTypes" :key="option.type" :label="option.label" :value="option.type" />
                </el-select>
              </label>
              <label v-if="selectedStep.kind !== 'step'">
                <span>{{ t("workflow.editor.expression") }}</span>
                <el-input v-model="selectedStep.expression" size="small" type="textarea" :rows="3" />
              </label>
              <div class="workflow-editor-grid">
                <label v-if="selectedStep.kind === 'loop'">
                  <span>{{ t("workflow.editor.maxIterations") }}</span>
                  <el-input-number v-model="selectedStep.maxIterations" size="small" :min="1" :max="12" controls-position="right" />
                </label>
                <label v-if="selectedStep.kind === 'parallel' || selectedStep.kind === 'router' || selectedStep.kind === 'condition' || selectedStep.kind === 'steps'">
                  <span>{{ t("workflow.editor.branches") }}</span>
                  <el-input-number v-model="selectedStep.branches" size="small" :min="1" :max="6" controls-position="right" />
                </label>
              </div>
            </section>
            <section v-else class="workflow-inspector-section">
              <h4>{{ t("workflow.editor.noSelectionTitle") }}</h4>
              <p class="workflow-muted">{{ t("workflow.editor.noSelectionDescription") }}</p>
            </section>
          </el-tab-pane>

          <el-tab-pane :label="t('workflow.inspector.validateTab')" name="validate">
            <section class="workflow-inspector-section">
              <h4>{{ validationTitle }}</h4>
              <ul class="workflow-check-list">
                <li v-for="item in validationItems" :key="item.message" :class="`is-${item.level}`">
                  <el-icon>
                    <Check v-if="item.level === 'ok'" />
                    <WarningFilled v-else />
                  </el-icon>
                  <span>{{ item.message }}</span>
                </li>
              </ul>
            </section>
            <section class="workflow-inspector-section">
              <h4>{{ t("workflow.inspector.sessionTitle") }}</h4>
              <ul class="workflow-check-list">
                <li v-for="item in sessionItems" :key="item" class="is-ok">
                  <el-icon><Check /></el-icon>
                  <span>{{ item }}</span>
                </li>
              </ul>
            </section>
            <section class="workflow-inspector-section workflow-run-options">
              <h4>{{ t("workflow.inspector.executionTitle") }}</h4>
              <label class="workflow-option-field">
                <span>{{ t("workflow.inspector.userId") }}</span>
                <el-input v-model="userId" size="small" />
              </label>
              <label class="workflow-option-field">
                <span>{{ t("workflow.inspector.numHistoryRuns") }}</span>
                <el-input-number v-model="numHistoryRuns" size="small" :min="1" :max="12" controls-position="right" />
              </label>
              <el-checkbox v-model="streamEvents">{{ t("workflow.inspector.streamEvents") }}</el-checkbox>
              <el-checkbox v-model="storeEvents">{{ t("workflow.inspector.storeEvents") }}</el-checkbox>
              <el-checkbox v-model="addWorkflowHistoryToSteps">{{ t("workflow.inspector.workflowHistory") }}</el-checkbox>
            </section>
          </el-tab-pane>

          <el-tab-pane :label="t('workflow.inspector.previewTab')" name="preview">
            <section class="workflow-inspector-section workflow-code-panel">
              <div class="workflow-code-head">
                <h4>{{ t("workflow.inspector.logicTitle") }}</h4>
                <el-button size="small" text @click="copyCode">
                  <el-icon><CopyDocument /></el-icon>
                  {{ t("workflow.actions.copyCode") }}
                </el-button>
              </div>
              <pre><code>{{ generatedCode }}</code></pre>
            </section>
          </el-tab-pane>
        </el-tabs>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue"
import {
  ArrowDown,
  ArrowUp,
  Check,
  Connection,
  CopyDocument,
  Delete,
  DocumentChecked,
  Plus,
  VideoPlay,
  WarningFilled,
} from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import {
  buildWorkflowCode,
  constructorName,
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

function executorLabel(executor: WorkflowExecutorType) {
  return executorTypes.value.find((executorType) => executorType.type === executor)?.label || executor
}

function stepMeta(step: WorkflowStep) {
  if (step.kind === "loop") return t("workflow.editor.iterationsValue", { count: step.maxIterations })
  if (step.kind === "router" || step.kind === "condition") return step.expression || t("workflow.editor.needsExpression")
  if (step.kind === "parallel") return t("workflow.editor.parallelValue", { count: step.branches })
  if (step.kind === "steps") return t("workflow.editor.sequenceValue", { count: step.branches })
  return workflowStepSymbol(step)
}

function branchLabels(step: WorkflowStep) {
  if (step.kind !== "parallel" && step.kind !== "router" && step.kind !== "condition" && step.kind !== "steps") return []
  return Array.from({ length: step.branches }, (_, index) => `${constructorName(step.kind)} ${index + 1}`)
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

<style scoped>
.workflow-console {
  display: grid;
  height: 100%;
  min-height: 0;
  grid-template-rows: auto minmax(0, 1fr);
  overflow: hidden;
  background: var(--ag-frame);
  color: var(--ag-text);
}

.workflow-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 0.75fr) auto;
  align-items: start;
  gap: 16px;
  border-bottom: 1px solid var(--ag-border);
  background: var(--ag-panel);
  padding: 14px 16px;
}

.workflow-title {
  min-width: 0;
}

.workflow-kicker,
.workflow-section-head p,
.workflow-canvas-head span:first-child {
  color: var(--ag-blue);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
}

.workflow-title h2,
.workflow-canvas-head h3,
.workflow-inspector-section h4 {
  margin: 0;
  color: var(--ag-heading);
}

.workflow-title h2 {
  margin-top: 4px;
  font-size: 20px;
  line-height: 1.2;
}

.workflow-title p,
.workflow-canvas-head p,
.workflow-section-head span,
.workflow-muted {
  margin: 4px 0 0;
  color: var(--ag-muted);
  font-size: 12px;
  line-height: 1.45;
}

.workflow-actions,
.workflow-canvas-actions,
.workflow-code-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.workflow-workbench {
  display: grid;
  min-height: 0;
  grid-template-columns: 320px minmax(0, 1fr) 380px;
  overflow: hidden;
}

.workflow-panel {
  min-height: 0;
  overflow: auto;
  border-right: 1px solid var(--ag-border);
  background: var(--ag-panel);
}

.workflow-palette,
.workflow-inspector {
  padding: 14px;
}

.workflow-inspector {
  border-right: 0;
  border-left: 1px solid var(--ag-border);
}

.workflow-config,
.workflow-palette-section + .workflow-palette-section,
.workflow-config + .workflow-palette-section {
  margin-top: 18px;
}

.workflow-config {
  display: grid;
  gap: 10px;
  margin-top: 0;
}

.workflow-library-item {
  display: grid;
  width: 100%;
  grid-template-columns: 34px minmax(0, 1fr) 18px;
  align-items: start;
  gap: 10px;
  margin-top: 10px;
  border: 1px solid var(--ag-border);
  border-radius: 8px;
  background: var(--ag-panel-soft);
  padding: 10px;
  color: inherit;
  text-align: left;
  transition:
    border-color 0.18s ease,
    background 0.18s ease,
    transform 0.18s ease;
}

.workflow-library-item:hover {
  border-color: color-mix(in srgb, var(--ag-blue) 42%, var(--ag-border));
  background: var(--ag-blue-soft);
  transform: translateY(-1px);
}

.workflow-step-type:hover {
  border-color: color-mix(in srgb, var(--ag-green) 42%, var(--ag-border));
  background: var(--ag-green-soft);
}

.workflow-badge,
.workflow-step-index {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  border: 1px solid var(--ag-border);
  border-radius: 8px;
  background: var(--ag-panel);
  color: var(--ag-blue);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
  font-weight: 800;
}

.workflow-library-copy,
.workflow-step-copy {
  min-width: 0;
}

.workflow-library-copy strong,
.workflow-step-copy strong,
.workflow-output strong,
.workflow-inspector-section dd {
  display: block;
  color: var(--ag-heading);
  font-size: 13px;
  line-height: 1.35;
}

.workflow-library-copy em,
.workflow-step-copy p,
.workflow-output span,
.workflow-inspector-section dt,
.workflow-check-list span,
.workflow-editor label > span {
  color: var(--ag-muted);
  font-size: 12px;
  font-style: normal;
  line-height: 1.45;
}

.workflow-canvas {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  overflow: hidden;
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--ag-border) 26%, transparent) 1px, transparent 1px),
    linear-gradient(180deg, color-mix(in srgb, var(--ag-border) 20%, transparent) 1px, transparent 1px),
    var(--ag-frame);
  background-size: 28px 28px;
}

.workflow-canvas-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--ag-border);
  background: color-mix(in srgb, var(--ag-panel) 92%, transparent);
  padding: 14px;
}

.workflow-canvas-head h3 {
  margin-top: 4px;
  font-size: 16px;
}

.workflow-runtime-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  border: 1px solid color-mix(in srgb, var(--ag-green) 42%, var(--ag-border));
  border-radius: 8px;
  background: var(--ag-green-soft);
  padding: 7px 9px;
  color: var(--ag-green);
  font-size: 12px;
  font-weight: 700;
}

.workflow-flow {
  display: grid;
  align-content: start;
  gap: 12px;
  min-height: 0;
  overflow: auto;
  padding: 18px;
}

.workflow-board-step {
  position: relative;
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  gap: 12px;
  width: min(820px, 100%);
  border: 1px solid var(--ag-border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--ag-panel) 92%, transparent);
  padding: 14px;
  box-shadow: var(--ag-shadow-panel);
  cursor: pointer;
}

.workflow-board-step.is-selected {
  border-color: var(--step-tone);
  background: color-mix(in srgb, var(--step-tone) 10%, var(--ag-panel));
}

.workflow-connector {
  position: absolute;
  top: -13px;
  left: 31px;
  width: 1px;
  height: 12px;
  background: var(--ag-border-strong);
}

.workflow-step-copy > span {
  color: var(--step-tone);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
}

.workflow-step-copy strong {
  margin-top: 4px;
}

.workflow-step-copy p {
  margin: 4px 0 0;
}

.workflow-step-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.workflow-branch-rail {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(86px, 1fr));
  gap: 6px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid color-mix(in srgb, var(--step-tone) 28%, var(--ag-border));
}

.workflow-branch-rail span {
  min-width: 0;
  border: 1px solid color-mix(in srgb, var(--step-tone) 34%, var(--ag-border));
  border-radius: 8px;
  background: color-mix(in srgb, var(--step-tone) 8%, var(--ag-panel-soft));
  padding: 5px 7px;
  overflow-wrap: anywhere;
  color: var(--ag-muted-strong);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
  font-weight: 800;
}

.workflow-step-actions {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.workflow-step-meta em,
.workflow-output {
  border: 1px solid var(--ag-border);
  border-radius: 8px;
  background: var(--ag-panel-soft);
}

.workflow-step-meta em {
  max-width: 100%;
  padding: 4px 7px;
  overflow-wrap: anywhere;
  color: var(--ag-muted-strong);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px;
  font-style: normal;
  font-weight: 700;
}

.tone-blue {
  --step-tone: var(--ag-blue);
  border-color: color-mix(in srgb, var(--ag-blue) 32%, var(--ag-border));
}

.tone-green {
  --step-tone: var(--ag-green);
  border-color: color-mix(in srgb, var(--ag-green) 32%, var(--ag-border));
}

.tone-yellow {
  --step-tone: var(--ag-yellow);
  border-color: color-mix(in srgb, var(--ag-yellow) 38%, var(--ag-border));
}

.tone-red {
  --step-tone: var(--ag-red);
  border-color: color-mix(in srgb, var(--ag-red) 32%, var(--ag-border));
}

.tone-purple {
  --step-tone: var(--ag-purple);
  border-color: color-mix(in srgb, var(--ag-purple) 34%, var(--ag-border));
}

.workflow-result-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  border-top: 1px solid var(--ag-border);
  background: color-mix(in srgb, var(--ag-panel) 90%, transparent);
  padding: 12px 14px;
}

.workflow-output {
  min-width: 0;
  padding: 10px;
}

.workflow-output strong {
  margin-top: 4px;
  overflow-wrap: anywhere;
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 12px;
}

.workflow-tabs {
  margin-top: 12px;
}

.workflow-inspector-section {
  margin-top: 14px;
  border: 1px solid var(--ag-border);
  border-radius: 8px;
  background: var(--ag-panel-soft);
  padding: 12px;
}

.workflow-inspector-section h4 {
  font-size: 13px;
}

.workflow-editor,
.workflow-editor label {
  display: grid;
  gap: 10px;
}

.workflow-editor label {
  gap: 5px;
}

.workflow-editor-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.workflow-run-options {
  display: grid;
  gap: 8px;
}

.workflow-option-field {
  display: grid;
  gap: 5px;
}

.workflow-check-list {
  display: grid;
  gap: 9px;
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
}

.workflow-check-list li {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}

.workflow-check-list .el-icon {
  margin-top: 2px;
}

.workflow-check-list .is-ok .el-icon {
  color: var(--ag-green);
}

.workflow-check-list .is-warning .el-icon {
  color: var(--ag-yellow);
}

.workflow-code-head {
  justify-content: space-between;
}

.workflow-code-panel pre {
  max-height: 520px;
  margin: 12px 0 0;
  overflow: auto;
}

.workflow-code-panel code {
  display: block;
  border: 1px solid var(--ag-border);
  border-radius: 8px;
  background: var(--ag-code-bg);
  padding: 10px;
  color: var(--ag-code-text);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre;
}

@media (max-width: 1280px) {
  .workflow-header {
    grid-template-columns: minmax(0, 1fr);
  }

  .workflow-actions {
    justify-content: flex-start;
  }

  .workflow-workbench {
    grid-template-columns: 280px minmax(0, 1fr);
    grid-auto-rows: minmax(0, auto);
  }

  .workflow-inspector {
    grid-column: 1 / -1;
    border-top: 1px solid var(--ag-border);
    border-left: 0;
  }
}

@media (max-width: 860px) {
  .workflow-console {
    overflow: auto;
  }

  .workflow-workbench {
    grid-template-columns: minmax(0, 1fr);
    overflow: visible;
  }

  .workflow-palette {
    display: none;
  }

  .workflow-inspector {
    border-top: 1px solid var(--ag-border);
  }

  .workflow-canvas {
    min-height: 0;
    overflow: visible;
  }

  .workflow-result-strip,
  .workflow-editor-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .workflow-canvas-head {
    display: grid;
  }

  .workflow-board-step {
    grid-template-columns: 36px minmax(0, 1fr);
  }

  .workflow-step-actions {
    grid-column: 1 / -1;
    flex-direction: row;
  }
}
</style>
