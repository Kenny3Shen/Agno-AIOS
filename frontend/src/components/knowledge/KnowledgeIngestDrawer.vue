<template>
  <el-drawer
    :model-value="modelValue"
    class="knowledge-ingest-drawer"
    :title="mode === 'update' ? t('knowledge.drawer.updateTitle') : t('knowledge.drawer.addTitle')"
    direction="rtl"
    :size="drawerSize"
    :before-close="beforeClose"
    @update:model-value="(value: boolean) => emit('update:modelValue', value)"
  >
    <div class="drawer-ingest-flow">
      <DataChip
        v-if="mode === 'update' && targetDocument"
        class="update-target"
        :label="t('knowledge.drawer.updateTarget')"
        :value="targetDocument.title"
        :title="targetDocument.title"
      />

      <section class="drawer-section drawer-source-section">
        <SectionHeader class="border-b-0 pb-0" :title="t('knowledge.drawer.sourceSection')" :subtitle="selectedReaderLabel" />

        <el-tabs v-if="mode === 'add'" v-model="inputMode" class="drawer-source-tabs">
          <el-tab-pane :label="t('knowledge.upload.fileTab')" name="file">
            <el-upload drag :auto-upload="false" :limit="1" :on-change="onFileChange" :on-remove="clearSelectedFile">
              <el-icon><UploadFilled /></el-icon>
              <div>{{ t("knowledge.upload.dropText") }} {{ t("knowledge.upload.chooseFile") }}</div>
            </el-upload>
          </el-tab-pane>
          <el-tab-pane :label="t('knowledge.upload.textTab')" name="text">
            <div class="drawer-form-grid">
              <el-input v-model="textForm.title" :placeholder="t('knowledge.drawer.documentName')" />
              <el-input v-model="textForm.content" type="textarea" :rows="8" :placeholder="t('knowledge.upload.contentPlaceholder')" />
            </div>
          </el-tab-pane>
          <el-tab-pane :label="t('knowledge.upload.pathTab')" name="path">
            <div class="drawer-form-grid">
              <el-input v-model="pathForm.path" :placeholder="t('knowledge.upload.pathLabel')" />
              <el-input v-model="pathForm.title" :placeholder="t('knowledge.upload.optionalPlaceholder')" />
            </div>
          </el-tab-pane>
        </el-tabs>

        <template v-else>
          <div class="drawer-form-grid">
            <label class="knowledge-field">
              <span>{{ t("knowledge.drawer.documentName") }}</span>
              <el-input v-model="updateForm.title" :placeholder="t('knowledge.drawer.documentName')" />
            </label>
          </div>
          <el-upload drag :auto-upload="false" :limit="1" :on-change="onFileChange" :on-remove="clearSelectedFile">
            <el-icon><UploadFilled /></el-icon>
            <div>{{ t("knowledge.upload.dropText") }} {{ t("knowledge.upload.chooseFile") }}</div>
          </el-upload>
        </template>

        <label class="knowledge-field source-field">
          <span>{{ t("knowledge.drawer.source") }}</span>
          <el-input v-model="currentSource" :placeholder="sourcePlaceholder" />
        </label>
      </section>

      <section class="drawer-section drawer-visibility-section">
        <SectionHeader class="border-b-0 pb-0" :title="t('knowledge.documents.columns.visibility')">
          <template #actions>
          <ResourceVisibilityTabs v-model="visibility" />
          </template>
        </SectionHeader>
      </section>

      <el-collapse v-model="advancedPanels" class="drawer-advanced-ingest">
        <el-collapse-item name="advanced">
          <template #title>
            <div class="advanced-title">
              <span>{{ t("knowledge.drawer.advancedIngest") }}</span>
            </div>
          </template>
          <div class="advanced-grid compact">
            <label class="knowledge-field">
              <span>{{ t("knowledge.drawer.readerStrategy") }}</span>
              <el-select v-model="ingestOptions.reader_strategy" class="reader-strategy-select">
                <el-option v-for="option in readerStrategyOptions" :key="option.value" :label="option.label" :value="option.value" />
              </el-select>
            </label>
            <label class="knowledge-field">
              <span>{{ t("knowledge.drawer.chunkSize") }}</span>
              <el-input-number v-model="ingestOptions.chunk_size" :min="200" :step="100" />
            </label>
            <label class="knowledge-field">
              <span>{{ t("knowledge.drawer.chunkOverlap") }}</span>
              <el-input-number v-model="ingestOptions.chunk_overlap" :min="0" :step="20" />
            </label>
            <label class="knowledge-field">
              <span>{{ t("knowledge.drawer.codeChunkSize") }}</span>
              <el-input-number v-model="ingestOptions.code_chunk_size" :min="256" :step="100" />
            </label>
            <label class="knowledge-field">
              <span>{{ t("knowledge.drawer.semanticThreshold") }}</span>
              <el-input-number v-model="ingestOptions.semantic_threshold" :min="0" :max="1" :step="0.01" />
            </label>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <template #footer>
      <div class="drawer-footer-actions">
        <el-button :disabled="loading" @click="emit('update:modelValue', false)">{{ t("knowledge.actions.cancel") }}</el-button>
        <el-button type="primary" :loading="loading" :disabled="!canSubmit" @click="submit">
          {{ mode === "update" ? t("knowledge.workbench.updateDocument") : t("knowledge.workbench.addDocument") }}
        </el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue"
import { ElMessageBox, type UploadFile } from "element-plus"
import { useI18n } from "vue-i18n"
import { UploadFilled } from "@element-plus/icons-vue"
import type { KnowledgeDocument, KnowledgeIngestOptions, KnowledgeStatus, ResourceVisibility } from "../../types"
import { createDefaultKnowledgeIngestOptions, readerStrategyForFilename } from "../../modules/knowledgeWorkbench"
import DataChip from "../common/DataChip.vue"
import ResourceVisibilityTabs from "../common/ResourceVisibilityTabs.vue"
import SectionHeader from "../common/SectionHeader.vue"

type DrawerMode = "add" | "update"
type InputMode = "file" | "text" | "path"
type SourceMode = InputMode | "update"

interface FileSubmitPayload {
  file: File
  title: string
  source: string
  visibility: ResourceVisibility
  ingest_options: KnowledgeIngestOptions | null
}

interface TextSubmitPayload {
  title: string
  content: string
  source: string
  metadata: Record<string, string>
  visibility: ResourceVisibility
  ingest_options: KnowledgeIngestOptions | null
}

interface PathSubmitPayload {
  path: string
  title: string
  source: string
  visibility: ResourceVisibility
  ingest_options: KnowledgeIngestOptions | null
}

interface UpdateSubmitPayload {
  document: KnowledgeDocument
  file: File
  title: string
  source: string
  visibility: ResourceVisibility
  metadata: Record<string, string>
  ingest_options: KnowledgeIngestOptions | null
}

interface UpdateMetadataPayload {
  document: KnowledgeDocument
  title: string
  source: string
  visibility: ResourceVisibility
  metadata: Record<string, string>
}

const props = defineProps<{
  modelValue: boolean
  mode: DrawerMode
  targetDocument: KnowledgeDocument | null
  status: KnowledgeStatus | null
  loading: boolean
}>()

const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  "submit-file": [payload: FileSubmitPayload]
  "submit-text": [payload: TextSubmitPayload]
  "submit-path": [payload: PathSubmitPayload]
  "submit-update-file": [payload: UpdateSubmitPayload]
  "submit-update-metadata": [payload: UpdateMetadataPayload]
}>()

const { t } = useI18n()
const drawerSize = "min(460px, 100vw)"
const inputMode = ref<InputMode>("file")
const selectedFile = ref<File | null>(null)
const visibility = ref<ResourceVisibility>("private")
const advancedPanels = ref<string[]>([])
const ingestOptions = reactive<KnowledgeIngestOptions>(createDefaultKnowledgeIngestOptions(props.status))
const sourceForm = reactive<Record<SourceMode, string>>({
  file: "",
  text: "manual",
  path: "",
  update: "",
})
const textForm = reactive({ title: "", content: "" })
const pathForm = reactive({ path: "", title: "" })
const updateForm = reactive({ title: "" })

const advancedIngestOpen = computed(() => advancedPanels.value.includes("advanced"))
const readerStrategyOptions = computed(() => [
  { label: t("knowledge.drawer.automaticReader"), value: "auto" },
  ...(props.status?.chunk_profiles || []).map((profile) => ({
    label: `${profile.label} · ${profile.reader}`,
    value: profile.strategy,
  })),
])
const selectedReaderLabel = computed(() => {
  const selected = ingestOptions.reader_strategy || "auto"
  return readerStrategyOptions.value.find((option) => option.value === selected)?.label || selected
})
const activeSourceMode = computed<SourceMode>(() => (props.mode === "update" ? "update" : inputMode.value))
const currentSource = computed({
  get: () => sourceForm[activeSourceMode.value],
  set: (value: string) => {
    sourceForm[activeSourceMode.value] = value
  },
})
const sourcePlaceholder = computed(() => fallbackSourceFor(activeSourceMode.value) || t("knowledge.upload.sourceManualPlaceholder"))
const hasMetadataChanges = computed(() => {
  const doc = props.targetDocument
  if (props.mode !== "update" || !doc) return false
  return (
    updateForm.title.trim() !== (doc.title || "").trim() ||
    currentSource.value.trim() !== (doc.source || "").trim() ||
    visibility.value !== (doc.visibility || "private")
  )
})

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    Object.assign(ingestOptions, createDefaultKnowledgeIngestOptions(props.status))
    visibility.value = props.targetDocument?.visibility || "private"
    textForm.title = ""
    textForm.content = ""
    pathForm.path = ""
    pathForm.title = ""
    updateForm.title = props.targetDocument?.title || ""
    sourceForm.file = ""
    sourceForm.text = "manual"
    sourceForm.path = ""
    sourceForm.update = props.targetDocument?.source || ""
    selectedFile.value = null
    advancedPanels.value = []
    inputMode.value = "file"
    syncReaderStrategy(props.targetDocument?.metadata?.file_name || props.targetDocument?.title || "")
  },
)

const onFileChange = (file: UploadFile) => {
  selectedFile.value = file.raw || null
  syncReaderStrategy(file.raw?.name || file.name || "")
}

const clearSelectedFile = () => {
  selectedFile.value = null
  syncReaderStrategy(inputMode.value === "path" ? pathForm.path : "")
}

watch(
  () => pathForm.path,
  (path) => {
    if (inputMode.value === "path") syncReaderStrategy(path)
  },
)

watch(inputMode, (mode) => {
  if (mode === "file") syncReaderStrategy(selectedFile.value?.name || "")
  else if (mode === "path") syncReaderStrategy(pathForm.path)
  else syncReaderStrategy("")
})

const syncReaderStrategy = (filename: string) => {
  ingestOptions.reader_strategy = readerStrategyForFilename(filename)
}

const fallbackSourceFor = (mode: SourceMode) => {
  if (mode === "text") return "manual"
  if (mode === "path") return pathForm.path.trim()
  return selectedFile.value ? `upload:${selectedFile.value.name}` : ""
}

const sourceValueFor = (mode: SourceMode) => sourceForm[mode].trim() || fallbackSourceFor(mode)

const ingestOptionsPayload = () => {
  if (!advancedIngestOpen.value) return null
  return {
    chunk_size: ingestOptions.chunk_size ?? null,
    chunk_overlap: ingestOptions.chunk_overlap ?? null,
    code_chunk_size: ingestOptions.code_chunk_size ?? null,
    semantic_threshold: ingestOptions.semantic_threshold ?? null,
    reader_strategy: ingestOptions.reader_strategy === "auto" ? null : ingestOptions.reader_strategy || null,
  }
}

const canSubmit = computed(() => {
  if (props.loading) return false
  if (props.mode === "update") return Boolean(props.targetDocument && (selectedFile.value || hasMetadataChanges.value))
  if (inputMode.value === "file") return Boolean(selectedFile.value)
  if (inputMode.value === "text") return Boolean(textForm.title.trim() && textForm.content.trim())
  return Boolean(pathForm.path.trim())
})

const beforeClose = async (done: () => void) => {
  if (!props.loading) {
    done()
    return
  }
  await ElMessageBox.confirm(t("knowledge.drawer.closeDuringMutation"), t("knowledge.confirm.closeTitle"))
  done()
}

const submit = () => {
  const ingest_options = ingestOptionsPayload()
  if (props.mode === "update" && props.targetDocument) {
    if (selectedFile.value) {
      emit("submit-update-file", {
        document: props.targetDocument,
        file: selectedFile.value,
        title: updateForm.title.trim() || props.targetDocument.title,
        source: sourceValueFor("update"),
        visibility: visibility.value,
        metadata: { file_name: selectedFile.value.name },
        ingest_options,
      })
      return
    }
    emit("submit-update-metadata", {
      document: props.targetDocument,
      title: updateForm.title.trim() || props.targetDocument.title,
      source: sourceValueFor("update"),
      visibility: visibility.value,
      metadata: {},
    })
    return
  }
  if (inputMode.value === "file" && selectedFile.value) {
    emit("submit-file", {
      file: selectedFile.value,
      title: selectedFile.value.name.replace(/\.[^.]+$/i, ""),
      source: sourceValueFor("file"),
      visibility: visibility.value,
      ingest_options,
    })
    return
  }
  if (inputMode.value === "text") {
    emit("submit-text", {
      title: textForm.title.trim(),
      content: textForm.content,
      source: sourceValueFor("text"),
      metadata: { input_mode: "manual" },
      visibility: visibility.value,
      ingest_options,
    })
    return
  }
  emit("submit-path", {
    path: pathForm.path.trim(),
    title: pathForm.title.trim(),
    source: sourceValueFor("path"),
    visibility: visibility.value,
    ingest_options,
  })
}
</script>

<style scoped>
.drawer-ingest-flow,
.drawer-form-grid,
.advanced-grid {
  display: grid;
  gap: 12px;
}

.drawer-section {
  display: grid;
  gap: 12px;
  border: 1px solid var(--kn-border);
  border-radius: var(--ag-radius-control);
  background: color-mix(in srgb, var(--kn-panel-soft) 70%, transparent);
  padding: 12px;
}

.drawer-source-tabs {
  min-width: 0;
}

.knowledge-field {
  display: grid;
  gap: 7px;
  min-width: 0;
}

.knowledge-field > span {
  color: var(--kn-muted);
  font-size: 12px;
  font-weight: 700;
}

.advanced-title {
  display: flex;
  min-width: 0;
  align-items: center;
  color: var(--kn-heading);
  font-weight: 800;
}

.drawer-advanced-ingest {
  border-radius: var(--ag-radius-control);
}

.drawer-advanced-ingest :deep(.el-collapse-item__header) {
  border: 1px solid var(--kn-border);
  border-radius: var(--ag-radius-control);
  background: color-mix(in srgb, var(--kn-panel-soft) 70%, transparent);
  padding: 0 12px;
}

.drawer-advanced-ingest :deep(.el-collapse-item__wrap) {
  margin-top: 8px;
  border: 1px solid var(--kn-border);
  border-radius: var(--ag-radius-control);
  background: color-mix(in srgb, var(--kn-panel-soft) 70%, transparent);
}

.drawer-advanced-ingest :deep(.el-collapse-item__content) {
  padding: 12px;
}

.drawer-advanced-ingest :deep(.el-input__wrapper),
.drawer-advanced-ingest :deep(.el-select__wrapper) {
  border-radius: var(--ag-radius-control);
}

.reader-strategy-select {
  width: 100%;
}

.drawer-footer-actions {
  display: inline-flex;
  width: 100%;
  justify-content: flex-end;
  gap: 8px;
}
</style>
