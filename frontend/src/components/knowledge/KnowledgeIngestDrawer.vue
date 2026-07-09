<template>
  <el-drawer
    :model-value="modelValue"
    class="knowledge-ingest-drawer"
    :title="mode === 'update' ? t('knowledge.drawer.updateTitle') : t('knowledge.drawer.addTitle')"
    direction="rtl"
    size="460px"
    :before-close="beforeClose"
    @update:model-value="(value: boolean) => emit('update:modelValue', value)"
  >
    <div class="drawer-ingest-flow">
      <div v-if="mode === 'update' && targetDocument" class="knowledge-runtime-chip update-target">
        <span>{{ t("knowledge.drawer.updateTarget") }}</span>
        <strong :title="targetDocument.title">{{ targetDocument.title }}</strong>
      </div>

      <el-tabs v-if="mode === 'add'" v-model="inputMode">
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
        <el-upload drag :auto-upload="false" :limit="1" :on-change="onFileChange" :on-remove="clearSelectedFile">
          <el-icon><UploadFilled /></el-icon>
          <div>{{ t("knowledge.upload.dropText") }} {{ t("knowledge.upload.chooseFile") }}</div>
        </el-upload>
      </template>

      <label v-if="mode === 'add'" class="knowledge-field">
        <span>{{ t("knowledge.documents.columns.visibility") }}</span>
        <ResourceVisibilityTabs v-model="visibility" />
      </label>

      <el-collapse v-model="advancedPanels" class="drawer-advanced-ingest">
        <el-collapse-item name="advanced">
          <template #title>
            <div class="advanced-title">
              <span>{{ t("knowledge.drawer.advancedIngest") }}</span>
              <em>{{ t("knowledge.drawer.advancedIngestHint") }}</em>
            </div>
          </template>
          <div class="advanced-grid compact">
            <label class="knowledge-field">
              <span>{{ t("knowledge.drawer.readerStrategy") }}</span>
              <el-select v-model="ingestOptions.reader_strategy">
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
import { createDefaultKnowledgeIngestOptions } from "../../modules/knowledgeWorkbench"
import ResourceVisibilityTabs from "../common/ResourceVisibilityTabs.vue"

type DrawerMode = "add" | "update"
type InputMode = "file" | "text" | "path"

interface FileSubmitPayload {
  file: File
  title: string
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
  visibility: ResourceVisibility
  ingest_options: KnowledgeIngestOptions | null
}

interface UpdateSubmitPayload {
  document: KnowledgeDocument
  file: File
  title: string
  source: string
  metadata: Record<string, string>
  ingest_options: KnowledgeIngestOptions | null
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
}>()

const { t } = useI18n()
const inputMode = ref<InputMode>("file")
const selectedFile = ref<File | null>(null)
const visibility = ref<ResourceVisibility>("private")
const advancedPanels = ref<string[]>([])
const ingestOptions = reactive<KnowledgeIngestOptions>(createDefaultKnowledgeIngestOptions(props.status))
const textForm = reactive({ title: "", content: "", source: "manual" })
const pathForm = reactive({ path: "", title: "" })

const advancedIngestOpen = computed(() => advancedPanels.value.includes("advanced"))
const readerStrategyOptions = computed(() => [
  { label: t("knowledge.drawer.automaticReader"), value: "auto" },
  ...(props.status?.chunk_profiles || []).map((profile) => ({
    label: `${profile.label} · ${profile.reader}`,
    value: profile.strategy,
  })),
])

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    Object.assign(ingestOptions, createDefaultKnowledgeIngestOptions(props.status))
    visibility.value = props.targetDocument?.visibility || "private"
    textForm.title = ""
    textForm.content = ""
    textForm.source = "manual"
    pathForm.path = ""
    pathForm.title = ""
    selectedFile.value = null
    advancedPanels.value = []
    inputMode.value = "file"
  },
)

const onFileChange = (file: UploadFile) => {
  selectedFile.value = file.raw || null
}

const clearSelectedFile = () => {
  selectedFile.value = null
}

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
  if (props.mode === "update") return Boolean(props.targetDocument && selectedFile.value)
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
  if (props.mode === "update" && props.targetDocument && selectedFile.value) {
    emit("submit-update-file", {
      document: props.targetDocument,
      file: selectedFile.value,
      title: props.targetDocument.title,
      source: `upload:${selectedFile.value.name}`,
      metadata: { file_name: selectedFile.value.name },
      ingest_options,
    })
    return
  }
  if (inputMode.value === "file" && selectedFile.value) {
    emit("submit-file", {
      file: selectedFile.value,
      title: selectedFile.value.name.replace(/\.[^.]+$/i, ""),
      visibility: visibility.value,
      ingest_options,
    })
    return
  }
  if (inputMode.value === "text") {
    emit("submit-text", {
      title: textForm.title.trim(),
      content: textForm.content,
      source: textForm.source.trim() || "manual",
      metadata: { input_mode: "manual" },
      visibility: visibility.value,
      ingest_options,
    })
    return
  }
  emit("submit-path", {
    path: pathForm.path.trim(),
    title: pathForm.title.trim(),
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

.knowledge-runtime-chip {
  display: grid;
  gap: 4px;
  border: 1px solid var(--kn-border);
  border-radius: var(--ag-radius-control);
  background: var(--kn-panel-soft);
  padding: 8px 10px;
}

.knowledge-runtime-chip span {
  color: var(--kn-muted);
  font-size: 11px;
  font-weight: 760;
}

.knowledge-runtime-chip strong {
  color: var(--kn-heading);
  font-size: 12px;
}

.advanced-title {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  color: var(--kn-heading);
  font-weight: 800;
}

.advanced-title em {
  color: var(--kn-muted);
  font-size: 12px;
  font-style: normal;
  font-weight: 500;
}

.drawer-footer-actions {
  display: inline-flex;
  width: 100%;
  justify-content: flex-end;
  gap: 8px;
}
</style>
