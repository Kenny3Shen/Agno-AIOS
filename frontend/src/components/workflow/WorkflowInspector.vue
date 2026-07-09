<template>
  <aside :aria-label="t('workflow.inspector.title')">
    <SectionHeader :title="t('workflow.inspector.title')" :subtitle="t('workflow.inspector.description')" />

    <el-tabs v-model="activeTabModel" class="mt-3">
      <el-tab-pane :label="t('workflow.inspector.editTab')" name="edit">
        <section v-if="selectedStep" class="mt-3 grid gap-2.5 rounded-2 border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] p-3">
          <SectionHeader :title="t('workflow.editor.title')" :status-label="selectedStep.name || t('workflow.editor.untitled')" status-tone="blue" />
          <label class="grid gap-1.25">
            <span class="ag-field-label">{{ t("workflow.editor.name") }}</span>
            <el-input v-model="selectedStep.name" size="small" />
          </label>
          <label class="grid gap-1.25">
            <span class="ag-field-label">{{ t("workflow.editor.symbol") }}</span>
            <el-input v-model="selectedStep.symbol" size="small" />
          </label>
          <label class="grid gap-1.25">
            <span class="ag-field-label">{{ t("workflow.editor.description") }}</span>
            <el-input v-model="selectedStep.description" size="small" type="textarea" :rows="3" />
          </label>
          <label class="grid gap-1.25">
            <span class="ag-field-label">{{ t("workflow.editor.stepType") }}</span>
            <el-select v-model="selectedStep.kind" size="small">
              <el-option v-for="option in stepTypes" :key="option.type" :label="option.label" :value="option.type" />
            </el-select>
          </label>
          <label class="grid gap-1.25">
            <span class="ag-field-label">{{ t("workflow.editor.executor") }}</span>
            <el-select v-model="selectedStep.executor" size="small">
              <el-option v-for="option in executorTypes" :key="option.type" :label="option.label" :value="option.type" />
            </el-select>
          </label>
          <label v-if="selectedStep.kind !== 'step'" class="grid gap-1.25">
            <span class="ag-field-label">{{ t("workflow.editor.expression") }}</span>
            <el-input v-model="selectedStep.expression" size="small" type="textarea" :rows="3" />
          </label>
          <div class="grid grid-cols-2 gap-2.5 max-sm:grid-cols-1">
            <label v-if="selectedStep.kind === 'loop'" class="grid gap-1.25">
              <span class="ag-field-label">{{ t("workflow.editor.maxIterations") }}</span>
              <el-input-number v-model="selectedStep.maxIterations" size="small" :min="1" :max="12" controls-position="right" />
            </label>
            <label v-if="supportsBranches(selectedStep.kind)" class="grid gap-1.25">
              <span class="ag-field-label">{{ t("workflow.editor.branches") }}</span>
              <el-input-number v-model="selectedStep.branches" size="small" :min="1" :max="6" controls-position="right" />
            </label>
          </div>
        </section>
        <section v-else class="ag-empty-compact mt-3">
          <strong class="block text-[var(--ag-heading)]">{{ t("workflow.editor.noSelectionTitle") }}</strong>
          <span class="mt-1 block text-xs text-[var(--ag-muted)]">{{ t("workflow.editor.noSelectionDescription") }}</span>
        </section>
      </el-tab-pane>

      <el-tab-pane :label="t('workflow.inspector.validateTab')" name="validate">
        <section class="mt-3 rounded-2 border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] p-3">
          <SectionHeader :title="validationTitle" :count="validationItems.length" :status-label="validationStatus.label" :status-tone="validationStatus.tone" />
          <ul class="mt-3 grid gap-2.25 p-0">
            <li v-for="item in validationItems" :key="item.message" class="grid grid-cols-[18px_minmax(0,1fr)] items-start gap-2">
              <StatusDot :label="item.message" :tone="item.level === 'ok' ? 'green' : 'yellow'" />
              <span class="text-xs leading-snug text-[var(--ag-muted)]">{{ item.message }}</span>
            </li>
          </ul>
        </section>
        <section class="mt-3 rounded-2 border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] p-3">
          <SectionHeader :title="t('workflow.inspector.sessionTitle')" :count="sessionItems.length" count-label="Items" />
          <ul class="mt-3 grid gap-2.25 p-0">
            <li v-for="item in sessionItems" :key="item" class="grid grid-cols-[18px_minmax(0,1fr)] items-start gap-2">
              <StatusDot :label="item" tone="green" />
              <span class="text-xs leading-snug text-[var(--ag-muted)]">{{ item }}</span>
            </li>
          </ul>
        </section>
        <section class="mt-3 grid gap-2 rounded-2 border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] p-3">
          <SectionHeader :title="t('workflow.inspector.executionTitle')" />
          <label class="grid gap-1.25">
            <span class="ag-field-label">{{ t("workflow.inspector.userId") }}</span>
            <el-input v-model="userIdModel" size="small" />
          </label>
          <label class="grid gap-1.25">
            <span class="ag-field-label">{{ t("workflow.inspector.numHistoryRuns") }}</span>
            <el-input-number v-model="numHistoryRunsModel" size="small" :min="1" :max="12" controls-position="right" />
          </label>
          <el-checkbox v-model="streamEventsModel">{{ t("workflow.inspector.streamEvents") }}</el-checkbox>
          <el-checkbox v-model="storeEventsModel">{{ t("workflow.inspector.storeEvents") }}</el-checkbox>
          <el-checkbox v-model="addWorkflowHistoryToStepsModel">{{ t("workflow.inspector.workflowHistory") }}</el-checkbox>
        </section>
      </el-tab-pane>

      <el-tab-pane :label="t('workflow.inspector.previewTab')" name="preview">
        <section class="mt-3 grid gap-2.5 rounded-2 border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] p-3">
          <SectionHeader :title="t('workflow.inspector.logicTitle')">
            <template #actions>
              <el-button size="small" text @click="emit('copyCode')">
                <el-icon><CopyDocument /></el-icon>
                {{ t("workflow.actions.copyCode") }}
              </el-button>
            </template>
          </SectionHeader>
          <PayloadViewer
            :text="generatedCode"
            mode="text"
            :empty-text="t('workflow.editor.emptyDescription')"
            :copy-label="t('workflow.actions.copyCode')"
            :max-collapsed-height="520"
          />
        </section>
      </el-tab-pane>
    </el-tabs>
  </aside>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { CopyDocument } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import PayloadViewer from "../common/PayloadViewer.vue"
import SectionHeader from "../common/SectionHeader.vue"
import StatusDot from "../common/StatusDot.vue"
import type { WorkflowExecutorType, WorkflowStepDraft, WorkflowStepKind } from "../../modules/workflowBuilder"

type Tone = "blue" | "green" | "yellow" | "red" | "purple"
type ValidationLevel = "ok" | "warning"

interface WorkflowStep extends WorkflowStepDraft {
  tone: Tone
}

interface WorkflowOption<TType extends string> {
  type: TType
  label: string
}

const props = defineProps<{
  activeTab: string
  userId: string
  numHistoryRuns: number
  streamEvents: boolean
  storeEvents: boolean
  addWorkflowHistoryToSteps: boolean
  selectedStep?: WorkflowStep
  stepTypes: WorkflowOption<WorkflowStepKind>[]
  executorTypes: WorkflowOption<WorkflowExecutorType>[]
  validationTitle: string
  validationItems: Array<{ level: ValidationLevel; message: string }>
  sessionItems: string[]
  generatedCode: string
}>()

const emit = defineEmits<{
  "update:activeTab": [value: string]
  "update:userId": [value: string]
  "update:numHistoryRuns": [value: number]
  "update:streamEvents": [value: boolean]
  "update:storeEvents": [value: boolean]
  "update:addWorkflowHistoryToSteps": [value: boolean]
  copyCode: []
}>()

const { t } = useI18n()

const activeTabModel = computed({
  get: () => props.activeTab,
  set: (value) => emit("update:activeTab", value),
})
const userIdModel = computed({
  get: () => props.userId,
  set: (value) => emit("update:userId", value),
})
const numHistoryRunsModel = computed({
  get: () => props.numHistoryRuns,
  set: (value) => emit("update:numHistoryRuns", value),
})
const streamEventsModel = computed({
  get: () => props.streamEvents,
  set: (value) => emit("update:streamEvents", value),
})
const storeEventsModel = computed({
  get: () => props.storeEvents,
  set: (value) => emit("update:storeEvents", value),
})
const addWorkflowHistoryToStepsModel = computed({
  get: () => props.addWorkflowHistoryToSteps,
  set: (value) => emit("update:addWorkflowHistoryToSteps", value),
})

const supportsBranches = (kind: WorkflowStepKind) => kind === "parallel" || kind === "router" || kind === "condition" || kind === "steps"

const validationStatus = computed(() => {
  const warnings = props.validationItems.filter((item) => item.level === "warning").length
  if (warnings) return { label: props.validationTitle, tone: "yellow" as const }
  return { label: t("workflow.validation.readyTitle"), tone: "green" as const }
})
</script>
