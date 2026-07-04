<template>
  <div class="knowledge-console knowledge-workflow-shell">
    <section class="knowledge-stat-dashboard ag-stat-strip" :aria-label="t('knowledge.stats.ariaLabel')">
      <article v-for="card in statisticsCards" :key="card.label" class="knowledge-stat-card ag-stat-chip">
        <span>{{ card.label }}</span>
        <strong :title="card.value">{{ card.value }}</strong>
      </article>
    </section>

    <div class="knowledge-workspace-grid">
      <section class="knowledge-panel knowledge-upload-panel">
        <div class="knowledge-section-head">
          <h4>{{ t('knowledge.upload.title') }}</h4>
          <span class="status-badge" :class="ingestTask.status">{{ ingestStatusLabel }}</span>
        </div>

        <div
          v-if="ingestTask.status === 'running' || ingestTask.status === 'error'"
          class="knowledge-upload-pipeline"
          :aria-label="t('knowledge.labels.pipelineAria')"
        >
          <div
            v-for="step in ingestSteps"
            :key="step.key"
            class="pipeline-step"
            :class="{ active: step.active, done: step.done, failed: step.failed }"
          >
            <span>{{ step.label }}</span>
          </div>
        </div>

        <div v-if="ingestTask.message && ingestTask.status !== 'idle'" class="task-feedback" :class="ingestTask.status">
          <span>{{ ingestTask.message }}</span>
          <el-button v-if="ingestTask.status === 'error'" size="small" text class="cursor-pointer" @click="retryIngestTask">
            {{ t('knowledge.actions.retry') }}
          </el-button>
        </div>

        <el-tabs v-model="activeIngestTab" class="knowledge-tabs">
          <el-tab-pane :label="t('knowledge.upload.fileTab')" name="upload">
            <div class="upload-mode-grid">
              <el-upload
                ref="browserUploadRef"
                v-model:file-list="browserFileList"
                drag
                :auto-upload="false"
                :limit="1"
                :accept="browserAccept"
                class="knowledge-upload"
                :on-change="handleBrowserFileChange"
                :on-remove="handleBrowserFileRemove"
                :on-exceed="handleBrowserFileExceed"
              >
                <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
                <div class="el-upload__text">
                  {{ t('knowledge.upload.dropText') }} <em>{{ t('knowledge.upload.chooseFile') }}</em>
                </div>
                <template #tip>
                  <div class="el-upload__tip">{{ t('knowledge.upload.supportedTypes') }}</div>
                </template>
              </el-upload>

              <div class="upload-side-form">
                <label class="knowledge-field">
                  <span>{{ t('knowledge.upload.titleLabel') }}</span>
                  <el-input v-model="browserForm.title" :placeholder="t('knowledge.upload.titlePlaceholder')" clearable />
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.upload.sourceLabel') }}</span>
                  <el-input v-model="browserForm.source" placeholder="upload" clearable />
                </label>
                <div class="reader-auto-note">
                  <strong>{{ t('knowledge.labels.reader') }}</strong>
                  <span>{{ detectedReaderLabel }}</span>
                </div>
                <el-button
                  type="primary"
                  class="!w-full cursor-pointer"
                  :loading="uploadingBrowserFile"
                  @click="submitBrowserUpload"
                >
                  <el-icon class="mr-1"><DocumentAdd /></el-icon>
                  {{ t('knowledge.actions.writeSelectedFile') }}
                </el-button>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane :label="t('knowledge.upload.textTab')" name="text">
            <div class="text-import-grid">
              <label class="knowledge-field">
                <span>{{ t('knowledge.upload.titleLabel') }}</span>
                <el-input v-model="textForm.title" :placeholder="t('knowledge.upload.textTitlePlaceholder')" clearable />
              </label>
              <label class="knowledge-field">
                <span>{{ t('knowledge.upload.sourceLabel') }}</span>
                <el-input v-model="textForm.source" placeholder="manual" clearable />
              </label>
              <label class="knowledge-field text-import-content">
                <span>{{ t('knowledge.upload.contentLabel') }}</span>
                <el-input
                  v-model="textForm.content"
                  type="textarea"
                  :rows="8"
                  :placeholder="t('knowledge.upload.contentPlaceholder')"
                />
              </label>
              <div class="form-action-row">
                <el-button type="primary" class="cursor-pointer" :loading="savingText" @click="submitTextDocument">
                  <el-icon class="mr-1"><DocumentAdd /></el-icon>
                  {{ t('knowledge.actions.writeText') }}
                </el-button>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane :label="t('knowledge.upload.pathTab')" name="path">
            <div class="path-import-grid">
              <label class="knowledge-field">
                <span>{{ t('knowledge.upload.pathLabel') }}</span>
                <el-input v-model="pathForm.path" placeholder="/abs/path/report.md" clearable />
              </label>
              <label class="knowledge-field">
                <span>{{ t('knowledge.upload.titleLabel') }}</span>
                <el-input v-model="pathForm.title" :placeholder="t('knowledge.upload.optionalPlaceholder')" clearable />
              </label>
              <div class="form-action-row path-action">
                <el-button type="primary" class="cursor-pointer" :loading="savingPath" @click="submitPathDocument">
                  <el-icon class="mr-1"><FolderOpened /></el-icon>
                  {{ t('knowledge.actions.importPath') }}
                </el-button>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </section>

      <section class="knowledge-panel retrieval-playground">
        <div class="knowledge-section-head">
          <h4>{{ t('knowledge.retrieval.title') }}</h4>
          <span class="status-badge embedding">{{ searchForm.searchType }}</span>
        </div>

        <div class="playground-question">
          <el-input
            v-model="searchForm.query"
            type="textarea"
            :rows="4"
            :placeholder="t('knowledge.retrieval.queryPlaceholder')"
          />
          <div class="playground-controls">
            <label class="knowledge-field">
              <span>{{ t('knowledge.labels.searchType') }}</span>
              <el-select v-model="searchForm.searchType" size="small">
                <el-option :label="t('knowledge.labels.hybrid')" value="hybrid" />
                <el-option :label="t('knowledge.labels.vector')" value="vector" />
                <el-option :label="t('knowledge.labels.keyword')" value="keyword" />
              </el-select>
            </label>
            <label class="knowledge-field">
              <span>{{ t('knowledge.labels.topK') }}</span>
              <el-input-number v-model="searchForm.limit" :min="1" :max="20" size="small" class="!w-full" />
            </label>
            <el-button type="primary" class="cursor-pointer" :loading="searching" @click="runSearch">
              {{ t('knowledge.actions.search') }}
            </el-button>
          </div>
        </div>

        <div class="playground-results">
          <div class="result-head">
            <strong>{{ t('knowledge.retrieval.resultTitle') }}</strong>
            <span>{{ t('knowledge.retrieval.resultCount', { count: searchResults.length }) }}</span>
          </div>

          <div v-if="searching" class="empty-box">
            <el-icon class="is-loading mr-1"><Loading /></el-icon>
            {{ t('knowledge.retrieval.searching') }}
          </div>
          <div v-else-if="searched && searchResults.length === 0" class="empty-box">{{ t('knowledge.retrieval.noResults') }}</div>
          <div v-else-if="!searched" class="empty-box">{{ t('knowledge.retrieval.idle') }}</div>

          <article
            v-for="result in searchResults"
            :key="`${result.doc_id}:${result.chunk_index}`"
            class="retrieval-hit"
          >
            <div class="hit-toolbar">
              <strong class="truncate">{{ result.title || result.doc_id || t('knowledge.labels.untitledChunk') }}</strong>
              <span class="score-badge">{{ formatScore(result.score) }}</span>
            </div>
            <p>{{ result.content }}</p>
            <div class="hit-meta">
              <span>{{ t('knowledge.labels.chunkIndex', { index: result.chunk_index }) }}</span>
              <span :title="result.source">{{ t('knowledge.labels.sourceValue', { value: result.source || '-' }) }}</span>
              <span :title="result.doc_id">{{ t('knowledge.labels.docValue', { value: shortId(result.doc_id) }) }}</span>
            </div>
          </article>

          <div v-if="searchResults.length" class="answer-preview">
            <span>{{ t('knowledge.retrieval.answer') }}</span>
            <p>{{ retrievalAnswer }}</p>
            <em>{{ t('knowledge.retrieval.reference', { value: retrievalReferences }) }}</em>
          </div>
        </div>
      </section>
    </div>

    <section class="knowledge-panel knowledge-documents-section">
      <div class="knowledge-section-head documents-head">
        <h4>{{ t('knowledge.documents.title') }}</h4>
        <div class="document-tools">
          <el-button class="cursor-pointer" size="small" :loading="loading" @click="loadKnowledge">
            <el-icon><Refresh /></el-icon>
          </el-button>
          <el-button
            type="danger"
            plain
            size="small"
            class="cursor-pointer"
            :disabled="documents.length === 0"
            :loading="clearing"
            @click="clearAllDocuments"
          >
            <el-icon><Delete /></el-icon>
          </el-button>
          <el-input v-model="documentQuery" class="document-filter" :placeholder="t('knowledge.documents.searchPlaceholder')" clearable>
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <el-select v-model="documentTypeFilter" size="small" class="document-select" :placeholder="t('knowledge.documents.typePlaceholder')">
            <el-option :label="t('knowledge.documents.allTypes')" value="all" />
            <el-option v-for="type in documentTypes" :key="type" :label="type" :value="type" />
          </el-select>
          <el-select v-model="documentStatusFilter" size="small" class="document-select" :placeholder="t('knowledge.documents.statusPlaceholder')">
            <el-option :label="t('knowledge.documents.allStatus')" value="all" />
            <el-option :label="t('knowledge.status.ready')" value="ready" />
            <el-option :label="t('knowledge.status.parsing')" value="parsing" />
            <el-option :label="t('knowledge.status.failed')" value="failed" />
          </el-select>
        </div>
      </div>

      <div v-if="loading && documents.length === 0" class="document-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        {{ t('knowledge.documents.loading') }}
      </div>

      <div v-else class="document-table" role="table" :aria-label="t('knowledge.documents.ariaLabel')">
        <div class="document-table-head" role="row">
          <span role="columnheader">{{ t('knowledge.documents.columns.name') }}</span>
          <span role="columnheader">{{ t('knowledge.documents.columns.type') }}</span>
          <span role="columnheader">{{ t('knowledge.documents.columns.size') }}</span>
          <span role="columnheader">{{ t('knowledge.documents.columns.chunks') }}</span>
          <span role="columnheader">{{ t('knowledge.documents.columns.embeddingStatus') }}</span>
          <span role="columnheader">{{ t('knowledge.documents.columns.updatedTime') }}</span>
          <span role="columnheader">{{ t('knowledge.documents.columns.source') }}</span>
          <span role="columnheader">{{ t('knowledge.documents.columns.actions') }}</span>
        </div>

        <div v-if="filteredDocuments.length === 0" class="empty-box">{{ t('knowledge.documents.empty') }}</div>

        <article v-for="row in filteredDocuments" :key="row.id" class="document-row" role="row">
          <div class="document-cell document-main" role="cell">
            <div class="document-primary">
              <span class="doc-title" :title="row.title">{{ row.title }}</span>
              <span class="doc-id" :title="row.id">{{ shortId(row.id) }}</span>
            </div>
          </div>
          <div class="document-cell" role="cell">
            <span class="type-badge">{{ documentType(row) }}</span>
          </div>
          <div class="document-cell document-number" role="cell">{{ documentSize(row) }}</div>
          <div class="document-cell document-number" role="cell">{{ row.chunks }}</div>
          <div class="document-cell" role="cell">
            <span class="status-badge" :class="documentStatus(row).tone">{{ documentStatus(row).label }}</span>
          </div>
          <div class="document-cell document-time" role="cell">{{ formatDate(row.created_at) }}</div>
          <div class="document-cell" role="cell">
            <span class="source-text" :title="row.source">{{ row.source || "manual" }}</span>
          </div>
          <div class="document-actions" role="cell">
            <el-tooltip :content="t('knowledge.documents.preview')" placement="top">
              <el-button text class="cursor-pointer" :aria-label="t('knowledge.documents.previewLabel', { title: row.title })" @click="openPreview(row)">
                <el-icon><View /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip :content="t('knowledge.documents.rebuildPending')" placement="top">
              <el-button text disabled :aria-label="t('knowledge.documents.reEmbeddingLabel', { title: row.title })">
                <el-icon><RefreshRight /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip :content="t('knowledge.documents.metadata')" placement="top">
              <el-button text class="cursor-pointer" :aria-label="t('knowledge.documents.metadataLabel', { title: row.title })" @click="openMetadata(row)">
                <el-icon><Tickets /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip :content="t('knowledge.documents.delete')" placement="top">
              <el-button
                type="danger"
                text
                class="cursor-pointer"
                :loading="deletingDocId === row.id"
                :aria-label="t('knowledge.documents.deleteLabel', { title: row.title })"
                @click="deleteDocument(row)"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </el-tooltip>
          </div>
        </article>
      </div>
    </section>

    <section class="knowledge-panel advanced-configuration">
      <el-collapse v-model="advancedSections">
        <el-collapse-item name="advanced">
          <template #title>
            <div class="advanced-title">
              <el-icon><Setting /></el-icon>
              <span>{{ t('knowledge.advanced.title') }}</span>
              <em>{{ t('knowledge.advanced.description') }}</em>
            </div>
          </template>

          <div class="advanced-grid">
            <section class="advanced-card">
              <div class="panel-title">
                <el-icon><Document /></el-icon>
                {{ t('knowledge.advanced.readerChunkStrategy') }}
              </div>
              <div class="reader-auto-note roomy">
                <strong>Reader</strong>
                <span>{{ t('knowledge.advanced.readerAuto') }}</span>
              </div>
              <div class="knowledge-strategy-grid">
                <article v-for="profile in chunkProfiles" :key="profile.strategy" class="strategy-card">
                  <div>
                    <strong>{{ profile.label }}</strong>
                    <span>{{ profile.reader }}</span>
                  </div>
                  <p>{{ profile.description }}</p>
                  <em>{{ profile.suffixes.join(" ") }}</em>
                </article>
              </div>
            </section>

            <section class="advanced-card">
              <div class="panel-title">
                <el-icon><Operation /></el-icon>
                {{ t('knowledge.advanced.ragParameters') }}
              </div>
              <div class="rag-settings-grid">
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.searchType') }}</span>
                  <el-select v-model="ragSettings.searchType" disabled>
                    <el-option :label="t('knowledge.labels.hybrid')" value="hybrid" />
                    <el-option :label="t('knowledge.labels.vector')" value="vector" />
                    <el-option :label="t('knowledge.labels.keyword')" value="keyword" />
                  </el-select>
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.topK') }}</span>
                  <el-slider v-model="ragSettings.agentTopK" :min="1" :max="20" disabled />
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.candidate') }}</span>
                  <el-slider v-model="ragSettings.candidates" :min="1" :max="50" disabled />
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.chunkSize') }}</span>
                  <el-slider v-model="ragSettings.chunkSize" :min="200" :max="4000" :step="100" disabled />
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.overlap') }}</span>
                  <el-slider v-model="ragSettings.chunkOverlap" :min="0" :max="800" :step="20" disabled />
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.threshold') }}</span>
                  <el-slider v-model="ragSettings.semanticThreshold" :min="0.1" :max="0.9" :step="0.01" disabled />
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.vectorWeight') }}</span>
                  <el-slider v-model="ragSettings.vectorWeight" :min="0" :max="1" :step="0.05" disabled />
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.bm25Weight') }}</span>
                  <el-slider v-model="ragSettings.bm25Weight" :min="0" :max="1" :step="0.05" disabled />
                </label>
                <div class="toggle-row">
                  <span>{{ t('knowledge.labels.hybrid') }}</span>
                  <el-switch v-model="ragSettings.hybrid" disabled />
                </div>
                <div class="toggle-row">
                  <span>MMR</span>
                  <el-switch v-model="ragSettings.mmr" disabled />
                </div>
                <div class="toggle-row">
                  <span>{{ t('knowledge.labels.reranker') }}</span>
                  <el-switch v-model="ragSettings.reranker" disabled />
                </div>
              </div>
            </section>

            <section class="advanced-card">
              <div class="panel-title">
                <el-icon><InfoFilled /></el-icon>
                {{ t('knowledge.advanced.parserOcrMetadata') }}
              </div>
              <div class="advanced-info-list">
                <div class="context-row">
                  <dt>{{ t('knowledge.advanced.parser') }}</dt>
                  <dd>{{ t('knowledge.advanced.autoByReader') }}</dd>
                </div>
                <div class="context-row">
                  <dt>{{ t('knowledge.advanced.ocr') }}</dt>
                  <dd>{{ t('knowledge.advanced.notEnabled') }}</dd>
                </div>
                <div class="context-row">
                  <dt>{{ t('knowledge.advanced.metadata') }}</dt>
                  <dd>source, file_name, file_size, file_type</dd>
                </div>
              </div>
            </section>

            <section class="advanced-card">
              <div class="panel-title">
                <el-icon><DataLine /></el-icon>
                {{ t('knowledge.advanced.advancedInformation') }}
              </div>
              <dl class="advanced-info-list">
                <div v-for="row in advancedInfoRows" :key="row.label" class="context-row">
                  <dt>{{ row.label }}</dt>
                  <dd :title="row.value">{{ row.value }}</dd>
                </div>
              </dl>
            </section>
          </div>
        </el-collapse-item>
      </el-collapse>
    </section>

    <el-drawer
      v-model="previewDrawerOpen"
      class="document-preview-drawer"
      :title="t('knowledge.drawer.previewTitle')"
      direction="rtl"
      size="420px"
    >
      <template v-if="previewDocument">
        <div class="drawer-stack">
          <div>
            <span class="drawer-label">{{ t('knowledge.drawer.documentName') }}</span>
            <strong>{{ previewDocument.title }}</strong>
          </div>
          <div>
            <span class="drawer-label">{{ t('knowledge.drawer.source') }}</span>
            <p>{{ previewDocument.source || "manual" }}</p>
          </div>
          <div class="drawer-grid">
            <div>
              <span class="drawer-label">{{ t('knowledge.drawer.type') }}</span>
              <strong>{{ documentType(previewDocument) }}</strong>
            </div>
            <div>
              <span class="drawer-label">{{ t('knowledge.drawer.chunks') }}</span>
              <strong>{{ previewDocument.chunks }}</strong>
            </div>
            <div>
              <span class="drawer-label">{{ t('knowledge.drawer.size') }}</span>
              <strong>{{ documentSize(previewDocument) }}</strong>
            </div>
            <div>
              <span class="drawer-label">{{ t('knowledge.drawer.updated') }}</span>
              <strong>{{ formatDate(previewDocument.created_at) }}</strong>
            </div>
          </div>
          <div>
            <span class="drawer-label">{{ t('knowledge.drawer.reference') }}</span>
            <pre class="metadata-json">{{ prettyJson(previewDocument) }}</pre>
          </div>
        </div>
      </template>
    </el-drawer>

    <el-dialog v-model="metadataDialogOpen" :title="t('knowledge.drawer.metadataTitle')" width="560px">
      <pre class="metadata-json">{{ prettyJson(metadataDocument?.metadata || {}) }}</pre>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue"
import { useI18n } from "vue-i18n"
import { ElMessage, ElMessageBox } from "element-plus"
import type { UploadFile, UploadFiles, UploadInstance, UploadUserFile } from "element-plus"
import {
  DataLine,
  Delete,
  Document,
  DocumentAdd,
  FolderOpened,
  InfoFilled,
  Loading,
  Operation,
  Refresh,
  RefreshRight,
  Search,
  Setting,
  Tickets,
  UploadFilled,
  View,
} from "@element-plus/icons-vue"
import { useKnowledgeApi } from "../composables/useApi"
import type { KnowledgeDocument, KnowledgeSearchResult, KnowledgeStatus } from "../types"

type IngestTab = "upload" | "text" | "path"
type IngestStage = "uploading" | "parsing" | "chunking" | "embedding" | "completed"
type IngestStatus = "idle" | "running" | "success" | "error"

const { t, locale } = useI18n()

const activeIngestTab = ref<IngestTab>("upload")
const status = ref<KnowledgeStatus | null>(null)
const documents = ref<KnowledgeDocument[]>([])
const documentQuery = ref("")
const documentTypeFilter = ref("all")
const documentStatusFilter = ref("all")
const browserUploadRef = ref<UploadInstance>()
const browserFileList = ref<UploadUserFile[]>([])
const selectedBrowserFile = ref<File | null>(null)
const savingText = ref(false)
const savingPath = ref(false)
const uploadingBrowserFile = ref(false)
const deletingDocId = ref<string | null>(null)
const clearing = ref(false)
const searching = ref(false)
const searched = ref(false)
const searchResults = ref<KnowledgeSearchResult[]>([])
const advancedSections = ref<string[]>([])
const previewDrawerOpen = ref(false)
const metadataDialogOpen = ref(false)
const previewDocument = ref<KnowledgeDocument | null>(null)
const metadataDocument = ref<KnowledgeDocument | null>(null)
const lastIngestRetry = ref<null | (() => Promise<void>)>(null)

const ingestTask = reactive<{
  status: IngestStatus
  stage: IngestStage
  message: string
}>({
  status: "idle",
  stage: "uploading",
  message: t("knowledge.upload.waiting"),
})

const browserForm = reactive({
  title: "",
  source: "upload",
})

const textForm = reactive({
  title: "",
  source: "manual",
  content: "",
})

const pathForm = reactive({
  path: "",
  title: "",
})

const searchForm = reactive({
  query: "",
  limit: 5,
  searchType: "hybrid",
})

const ragSettings = reactive({
  agentTopK: 5,
  candidates: 15,
  chunkSize: 1200,
  chunkOverlap: 160,
  codeChunkSize: 1800,
  semanticThreshold: 0.52,
  vectorWeight: 0.7,
  bm25Weight: 0.3,
  embeddingProvider: "BAAI/bge-small-zh-v1.5",
  reranker: true,
  hybrid: true,
  mmr: false,
  searchType: "hybrid",
})

const {
  loading,
  fetchKnowledge,
  addTextDocument,
  addFileDocument,
  deleteKnowledgeDocument,
  clearKnowledge,
  searchKnowledge,
} = useKnowledgeApi()

const totalChunks = computed(() => documents.value.reduce((sum, item) => sum + Number(item.chunks || 0), 0))

const statisticsCards = computed(() => [
  { label: t("knowledge.stats.documents"), value: String(status.value?.documents ?? documents.value.length), hint: t("knowledge.stats.documentsHint") },
  { label: t("knowledge.stats.chunks"), value: String(status.value?.chunks ?? totalChunks.value), hint: t("knowledge.stats.chunksHint") },
  { label: t("knowledge.stats.embeddingModel"), value: status.value?.embedding || "unknown", hint: status.value?.embedding_dimensions ? `${status.value.embedding_dimensions} dimensions` : t("knowledge.stats.modelRuntime") },
  { label: t("knowledge.stats.vectorDatabase"), value: status.value?.collection || "-", hint: status.value?.search_type || "hybrid" },
  { label: t("knowledge.stats.storage"), value: status.value?.storage || "-", hint: status.value?.database || "postgres" },
  { label: t("knowledge.stats.status"), value: status.value?.torch_runtime_ok === false ? t("knowledge.status.degraded") : t("knowledge.status.ready"), hint: status.value?.cold_start_note || t("knowledge.stats.indexAvailable") },
])

const ingestStatusLabel = computed(() => {
  if (ingestTask.status === "running") {
    return ingestPipeline.value.find((item) => item.key === ingestTask.stage)?.label ?? ingestTask.stage
  }
  if (ingestTask.status === "success") return t("knowledge.status.completed")
  if (ingestTask.status === "error") return t("knowledge.status.failed")
  return t("knowledge.status.ready")
})

const ingestPipeline = computed<Array<{ key: IngestStage; label: string }>>(() => [
  { key: "uploading", label: t("knowledge.status.uploading") },
  { key: "parsing", label: t("knowledge.status.parsing") },
  { key: "chunking", label: t("knowledge.status.chunking") },
  { key: "embedding", label: t("knowledge.status.embedding") },
  { key: "completed", label: t("knowledge.status.completed") },
])

const ingestSteps = computed(() => {
  const currentIndex = ingestPipeline.value.findIndex((item) => item.key === ingestTask.stage)
  return ingestPipeline.value.map((item, index) => ({
    ...item,
    active: ingestTask.status === "running" && item.key === ingestTask.stage,
    done: ingestTask.status === "success" || currentIndex > index && ingestTask.status !== "error",
    failed: ingestTask.status === "error" && item.key === ingestTask.stage,
  }))
})

const browserAccept = [
  ".md",
  ".markdown",
  ".txt",
  ".log",
  ".csv",
  ".tsv",
  ".json",
  ".jsonl",
  ".yaml",
  ".yml",
  ".toml",
  ".py",
  ".js",
  ".jsx",
  ".ts",
  ".tsx",
  ".vue",
  ".go",
  ".rs",
  ".java",
  ".sh",
  ".sql",
  "text/plain",
  "text/markdown",
  "application/json",
  "text/csv",
].join(",")
const browserTextPattern = /\.(md|markdown|txt|log|csv|tsv|json|jsonl|ya?ml|toml|py|js|jsx|ts|tsx|vue|go|rs|java|c|cc|cpp|h|hpp|cs|php|rb|sh|sql)$/i

const chunkProfiles = computed(() => status.value?.chunk_profiles || [
  {
    label: "Markdown",
    strategy: "markdown",
    reader: "MarkdownReader",
    suffixes: [".md", ".markdown"],
    description: t("knowledge.chunkProfiles.markdown"),
  },
  {
    label: "CSV Row",
    strategy: "csv_row",
    reader: "CSVReader",
    suffixes: [".csv", ".tsv"],
    description: t("knowledge.chunkProfiles.csv"),
  },
  {
    label: "Code",
    strategy: "code",
    reader: "TextReader",
    suffixes: [".py", ".ts", ".vue"],
    description: t("knowledge.chunkProfiles.code"),
  },
])

const detectedReaderLabel = computed(() => {
  const file = selectedBrowserFile.value
  if (!file) return t("knowledge.reader.autoOnUpload")
  const suffix = file.name.match(/\.[^.]+$/)?.[0]?.toLowerCase() || ""
  const profile = chunkProfiles.value.find((item) => item.suffixes.includes(suffix))
  return profile ? `${profile.reader} · ${profile.label}` : t("knowledge.reader.textAuto")
})

const documentTypes = computed(() => {
  return [...new Set(documents.value.map((doc) => documentType(doc)).filter(Boolean))].sort()
})

const filteredDocuments = computed(() => {
  const query = documentQuery.value.trim().toLowerCase()
  return documents.value.filter((item) => {
    const metadataText = Object.values(item.metadata || {}).join(" ")
    const matchesQuery = !query || [item.id, item.title, item.source, metadataText].some((text) => String(text || "").toLowerCase().includes(query))
    const matchesType = documentTypeFilter.value === "all" || documentType(item) === documentTypeFilter.value
    const matchesStatus = documentStatusFilter.value === "all" || documentStatus(item).value === documentStatusFilter.value
    return matchesQuery && matchesType && matchesStatus
  })
})

const advancedInfoRows = computed(() => [
  { label: t("knowledge.labels.schema"), value: status.value?.postgres_schema || "-" },
  { label: t("knowledge.labels.dimension"), value: valueOrDash(status.value?.embedding_dimensions) },
  { label: t("knowledge.labels.runtime"), value: status.value?.torch_runtime_ok === false ? t("knowledge.status.degraded") : t("knowledge.status.ready") },
  { label: t("knowledge.labels.candidates"), value: valueOrDash(status.value?.retrieval_candidates) },
  { label: t("knowledge.labels.suffix"), value: status.value?.supported_suffixes?.join(" ") || "-" },
  { label: t("knowledge.labels.device"), value: status.value?.device || "-" },
  { label: t("knowledge.labels.database"), value: status.value?.database || "-" },
  { label: t("knowledge.labels.contents"), value: status.value?.contents_db || "-" },
  { label: t("knowledge.labels.collection"), value: status.value?.collection || "-" },
])

const retrievalAnswer = computed(() => {
  if (!searchResults.value.length) return t("knowledge.retrieval.answerFallback")
  const first = searchResults.value[0]
  return first.content.length > 180 ? `${first.content.slice(0, 180)}...` : first.content
})

const retrievalReferences = computed(() => {
  if (!searchResults.value.length) return "-"
  return searchResults.value
    .slice(0, 3)
    .map((item) => item.title || item.source || shortId(item.doc_id))
    .join(" / ")
})

const loadKnowledge = async () => {
  try {
    const data = await fetchKnowledge()
    status.value = data.status
    documents.value = data.documents
    if (data.status.embedding) {
      ragSettings.embeddingProvider = data.status.embedding
    }
    ragSettings.reranker = data.status.rerank_enabled
    ragSettings.hybrid = (data.status.search_type || "hybrid") === "hybrid"
    if (data.status.chunk_size) {
      ragSettings.chunkSize = data.status.chunk_size
    }
    if (typeof data.status.chunk_overlap === "number") {
      ragSettings.chunkOverlap = data.status.chunk_overlap
    }
    if (data.status.top_k) {
      ragSettings.agentTopK = data.status.top_k
    }
    if (data.status.retrieval_candidates) {
      ragSettings.candidates = data.status.retrieval_candidates
    }
    if (typeof data.status.vector_score_weight === "number") {
      ragSettings.vectorWeight = data.status.vector_score_weight
      ragSettings.bm25Weight = Number((1 - data.status.vector_score_weight).toFixed(2))
    }
    if (data.status.search_type) {
      ragSettings.searchType = data.status.search_type
      searchForm.searchType = data.status.search_type
    }
    if (data.status.code_chunk_size) {
      ragSettings.codeChunkSize = data.status.code_chunk_size
    }
    if (typeof data.status.semantic_threshold === "number") {
      ragSettings.semanticThreshold = data.status.semantic_threshold
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("knowledge.messages.loadFailed"))
  }
}

const stripExtension = (name: string) => name.replace(/\.[^.]+$/i, "")

const isSupportedTextFile = (file: File) => {
  return browserTextPattern.test(file.name)
}

const handleBrowserFileChange = (uploadFile: UploadFile, uploadFiles: UploadFiles) => {
  browserFileList.value = uploadFiles.slice(-1)
  selectedBrowserFile.value = uploadFile.raw ?? null
  if (!browserForm.title && uploadFile.name) {
    browserForm.title = stripExtension(uploadFile.name)
  }
  if (!browserForm.source || browserForm.source === "upload") {
    browserForm.source = `upload:${uploadFile.name}`
  }
}

const handleBrowserFileRemove = () => {
  selectedBrowserFile.value = null
}

const handleBrowserFileExceed = () => {
  ElMessage.warning(t("knowledge.messages.singleFileOnly"))
}

const resetBrowserUpload = () => {
  browserForm.title = ""
  browserForm.source = "upload"
  selectedBrowserFile.value = null
  browserFileList.value = []
  browserUploadRef.value?.clearFiles()
}

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

const runIngestTask = async (title: string, task: () => Promise<void>, retry: () => Promise<void>) => {
  lastIngestRetry.value = retry
  ingestTask.status = "running"
  ingestTask.stage = "uploading"
  ingestTask.message = `${title}: ${t("knowledge.status.uploading")}`
  try {
    await wait(80)
    ingestTask.stage = "parsing"
    ingestTask.message = `${title}: ${t("knowledge.status.parsing")}`
    await task()
    await wait(80)
    ingestTask.stage = "chunking"
    ingestTask.message = `${title}: ${t("knowledge.status.chunking")}`
    await wait(80)
    ingestTask.stage = "embedding"
    ingestTask.message = `${title}: ${t("knowledge.status.embedding")}`
    await loadKnowledge()
    ingestTask.stage = "completed"
    ingestTask.status = "success"
    ingestTask.message = `${title}: ${t("knowledge.status.completed")}`
    ElMessage.success(t("knowledge.messages.updated"))
  } catch (err) {
    ingestTask.status = "error"
    ingestTask.message = err instanceof Error ? err.message : t("knowledge.messages.taskFailed", { title })
    ElMessage.error(ingestTask.message)
  }
}

const retryIngestTask = async () => {
  if (!lastIngestRetry.value) return
  await lastIngestRetry.value()
}

const submitBrowserUpload = async () => {
  const file = selectedBrowserFile.value
  if (!file) {
    ElMessage.warning(t("knowledge.messages.selectFile"))
    return
  }
  if (!isSupportedTextFile(file)) {
    ElMessage.warning(t("knowledge.messages.selectTextFile"))
    return
  }

  uploadingBrowserFile.value = true
  const retry = async () => { await submitBrowserUpload() }
  await runIngestTask(t("knowledge.upload.fileUpload"), async () => {
    const content = (await file.text()).trim()
    if (!content) {
      throw new Error(t("knowledge.upload.emptyFile"))
    }
    await addTextDocument({
      title: browserForm.title.trim() || stripExtension(file.name),
      content,
      source: browserForm.source.trim() || `upload:${file.name}`,
      metadata: {
        file_name: file.name,
        upload_mode: "browser",
        file_size: String(file.size),
        file_type: file.name.match(/\.[^.]+$/)?.[0]?.toLowerCase() || "text",
        mime_type: file.type || "text/plain",
      },
    })
    resetBrowserUpload()
  }, retry)
  uploadingBrowserFile.value = false
}

const submitTextDocument = async () => {
  if (!textForm.title.trim() || !textForm.content.trim()) {
    ElMessage.warning(t("knowledge.messages.titleContentRequired"))
    return
  }
  savingText.value = true
  const retry = async () => { await submitTextDocument() }
  await runIngestTask(t("knowledge.upload.textImport"), async () => {
    await addTextDocument({
      title: textForm.title.trim(),
      content: textForm.content.trim(),
      source: textForm.source.trim() || "manual",
      metadata: { input_mode: "manual" },
    })
    textForm.title = ""
    textForm.source = "manual"
    textForm.content = ""
  }, retry)
  savingText.value = false
}

const submitPathDocument = async () => {
  if (!pathForm.path.trim()) {
    ElMessage.warning(t("knowledge.messages.pathRequired"))
    return
  }
  savingPath.value = true
  const retry = async () => { await submitPathDocument() }
  await runIngestTask(t("knowledge.upload.serverPath"), async () => {
    await addFileDocument({
      path: pathForm.path.trim(),
      title: pathForm.title.trim() || null,
    })
    pathForm.path = ""
    pathForm.title = ""
  }, retry)
  savingPath.value = false
}

const deleteDocument = async (doc: KnowledgeDocument) => {
  try {
    await ElMessageBox.confirm(t("knowledge.confirm.deleteMessage", { title: doc.title }), t("knowledge.confirm.deleteTitle"), {
      confirmButtonText: t("knowledge.actions.delete"),
      cancelButtonText: t("knowledge.actions.cancel"),
      type: "warning",
    })
    deletingDocId.value = doc.id
    await deleteKnowledgeDocument(doc.id)
    documents.value = documents.value.filter((item) => item.id !== doc.id)
    await loadKnowledge()
    ElMessage.success(t("knowledge.documents.deleted"))
  } catch (err) {
    if (err !== "cancel" && err !== "close") {
      ElMessage.error(err instanceof Error ? err.message : t("knowledge.messages.deleteFailed"))
    }
  } finally {
    deletingDocId.value = null
  }
}

const clearAllDocuments = async () => {
  if (documents.value.length === 0) return
  try {
    await ElMessageBox.confirm(t("knowledge.confirm.clearMessage"), t("knowledge.confirm.clearTitle"), {
      confirmButtonText: t("knowledge.actions.clear"),
      cancelButtonText: t("knowledge.actions.cancel"),
      type: "warning",
    })
    clearing.value = true
    await clearKnowledge()
    documents.value = []
    searchResults.value = []
    searched.value = false
    await loadKnowledge()
    ElMessage.success(t("knowledge.messages.cleared"))
  } catch (err) {
    if (err !== "cancel" && err !== "close") {
      ElMessage.error(err instanceof Error ? err.message : t("knowledge.messages.clearFailed"))
    }
  } finally {
    clearing.value = false
  }
}

const runSearch = async () => {
  const query = searchForm.query.trim()
  if (!query) {
    ElMessage.warning(t("knowledge.retrieval.questionRequired"))
    return
  }
  searching.value = true
  searched.value = true
  try {
    const data = await searchKnowledge(query, searchForm.limit, searchForm.searchType)
    searchResults.value = data.results
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("knowledge.messages.searchFailed"))
  } finally {
    searching.value = false
  }
}

const openPreview = (doc: KnowledgeDocument) => {
  previewDocument.value = doc
  previewDrawerOpen.value = true
}

const openMetadata = (doc: KnowledgeDocument) => {
  metadataDocument.value = doc
  metadataDialogOpen.value = true
}

const metadataValue = (doc: KnowledgeDocument, ...keys: string[]) => {
  for (const key of keys) {
    const value = doc.metadata?.[key]
    if (value) return value
  }
  return ""
}

const documentType = (doc: KnowledgeDocument) => {
  const metaType = metadataValue(doc, "file_type", "mime_type")
  if (metaType) return metaType.replace(/^\./, "").toUpperCase()
  const text = `${doc.title} ${doc.source} ${metadataValue(doc, "file_name")}`
  const suffix = text.match(/\.([a-z0-9]+)(?:\s|$)/i)?.[1]
  return (suffix || "TEXT").toUpperCase()
}

const documentSize = (doc: KnowledgeDocument) => {
  const size = Number(metadataValue(doc, "file_size"))
  if (!Number.isFinite(size) || size <= 0) return "-"
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

const documentStatus = (doc: KnowledgeDocument) => {
  const raw = metadataValue(doc, "status", "embedding_status").toLowerCase()
  if (raw.includes("fail") || raw.includes("error")) return { label: t("knowledge.status.failed"), value: "failed", tone: "failed" }
  if (Number(doc.chunks || 0) > 0) return { label: t("knowledge.status.ready"), value: "ready", tone: "ready" }
  return { label: t("knowledge.status.parsing"), value: "parsing", tone: "parsing" }
}

const shortId = (value: string) => {
  if (!value) return "-"
  return value.length > 14 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value
}

const formatDate = (value: string) => {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(locale.value, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

const formatScore = (value: number) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return "-"
  return n <= 1 ? n.toFixed(3) : n.toFixed(2)
}

const valueOrDash = (value: unknown) => {
  if (value === null || value === undefined || value === "") return "-"
  return String(value)
}

const prettyJson = (value: unknown) => {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

onMounted(() => {
  loadKnowledge()
})
</script>

<style scoped>
.knowledge-console {
  --kn-bg: var(--ag-frame);
  --kn-panel: var(--ag-panel);
  --kn-panel-soft: var(--ag-panel-soft);
  --kn-border: var(--ag-border);
  --kn-border-strong: var(--ag-border-strong);
  --kn-text: var(--ag-text);
  --kn-heading: var(--ag-heading);
  --kn-muted: var(--ag-muted);
  --kn-ready: var(--ag-green);
  --kn-ready-soft: var(--ag-green-soft);
  --kn-embedding: var(--ag-blue);
  --kn-embedding-soft: var(--ag-blue-soft);
  --kn-parsing: var(--ag-yellow);
  --kn-parsing-soft: var(--ag-yellow-soft);
  --kn-failed: var(--ag-red);
  --kn-failed-soft: var(--ag-red-soft);
  width: min(1480px, 100%);
  margin: 0 auto;
  padding: 16px;
  color: var(--kn-text);
}

.knowledge-section-head,
.documents-head,
.document-tools,
.hit-toolbar,
.hit-meta,
.playground-controls,
.form-action-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.knowledge-section-head p {
  margin: 0;
  color: var(--kn-muted);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.knowledge-section-head h4 {
  margin: 2px 0 0;
  color: var(--kn-heading);
  font-size: 18px;
  font-weight: 820;
}

.knowledge-section-head h4 {
  font-size: 15px;
}

.knowledge-section-head span {
  display: block;
  min-width: 0;
  margin-top: 4px;
  color: var(--kn-muted);
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.knowledge-stat-dashboard {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
}

.knowledge-stat-card,
.knowledge-panel,
.retrieval-hit,
.answer-preview,
.advanced-card,
.reader-auto-note,
.empty-box {
  border: 1px solid var(--kn-border);
  border-radius: 12px;
  background: var(--kn-panel);
}

.knowledge-stat-card {
  flex: 1 1 148px;
  min-width: 0;
  padding: 8px 10px;
}

.knowledge-stat-card span {
  display: block;
  min-width: 0;
  color: var(--kn-muted);
  font-size: 10px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.knowledge-stat-card strong {
  display: block;
  margin-top: 2px;
  overflow: hidden;
  color: var(--kn-heading);
  font-size: 13px;
  font-weight: 820;
  overflow-wrap: anywhere;
}

.knowledge-workspace-grid {
  display: grid;
  align-items: start;
  gap: 14px;
  grid-template-columns: minmax(0, 1.08fr) minmax(380px, 0.92fr);
  margin-bottom: 14px;
}

.knowledge-panel {
  min-width: 0;
  padding: 14px;
  box-shadow: var(--ag-shadow-panel);
}

.knowledge-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.knowledge-upload-pipeline {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  margin-bottom: 12px;
}

.pipeline-step {
  position: relative;
  border: 1px solid var(--kn-border);
  border-radius: 999px;
  background: var(--kn-panel-soft);
  padding: 6px 8px;
  color: var(--kn-muted);
  font-size: 10px;
  font-weight: 800;
  text-align: center;
}

.pipeline-step.done {
  border-color: color-mix(in srgb, var(--kn-ready) 45%, var(--kn-border));
  background: var(--kn-ready-soft);
  color: var(--kn-ready);
}

.pipeline-step.active {
  border-color: color-mix(in srgb, var(--kn-embedding) 52%, var(--kn-border));
  background: var(--kn-embedding-soft);
  color: var(--kn-embedding);
}

.pipeline-step.failed {
  border-color: color-mix(in srgb, var(--kn-failed) 52%, var(--kn-border));
  background: var(--kn-failed-soft);
  color: var(--kn-failed);
}

.task-feedback {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border-radius: 10px;
  margin-bottom: 12px;
  padding: 8px 10px;
  font-size: 12px;
}

.task-feedback.idle,
.task-feedback.running {
  background: var(--kn-embedding-soft);
  color: var(--kn-embedding);
}

.task-feedback.success {
  background: var(--kn-ready-soft);
  color: var(--kn-ready);
}

.task-feedback.error {
  background: var(--kn-failed-soft);
  color: var(--kn-failed);
}

.upload-mode-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: minmax(0, 1fr) 300px;
}

.upload-side-form,
.text-import-grid,
.path-import-grid,
.playground-question,
.playground-results,
.drawer-stack {
  display: grid;
  gap: 12px;
}

.text-import-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.text-import-content,
.path-action {
  grid-column: 1 / -1;
}

.path-import-grid {
  grid-template-columns: minmax(0, 1fr) 240px;
}

.knowledge-field {
  display: grid;
  gap: 7px;
  min-width: 0;
}

.knowledge-field > span,
.setting-label,
.drawer-label {
  color: var(--kn-muted);
  font-size: 12px;
  font-weight: 700;
}

.reader-auto-note {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  background: var(--kn-panel-soft);
  padding: 9px 10px;
}

.reader-auto-note.roomy {
  margin: 12px 0;
}

.reader-auto-note strong {
  min-width: 0;
  color: var(--kn-heading);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.reader-auto-note span {
  min-width: 0;
  color: var(--kn-muted);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.playground-controls {
  align-items: end;
}

.playground-controls .knowledge-field {
  flex: 1 1 160px;
}

.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--kn-muted);
  font-size: 12px;
}

.retrieval-hit {
  padding: 12px;
}

.retrieval-hit strong {
  color: var(--kn-heading);
  font-size: 13px;
  font-weight: 800;
}

.retrieval-hit p,
.answer-preview p {
  margin: 8px 0 0;
  color: var(--kn-text);
  font-size: 12px;
  line-height: 1.65;
}

.hit-meta {
  justify-content: flex-start;
  flex-wrap: wrap;
  margin-top: 10px;
}

.hit-meta span,
.score-badge,
.type-badge,
.status-badge,
.doc-id {
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  border: 1px solid var(--kn-border);
  border-radius: 999px;
  background: var(--kn-panel-soft);
  color: var(--kn-muted);
  font-size: 10px;
  font-weight: 800;
  line-height: 1.3;
  padding: 3px 7px;
}

.score-badge {
  color: var(--kn-ready);
}

.status-badge.ready,
.status-badge.success {
  border-color: color-mix(in srgb, var(--kn-ready) 45%, var(--kn-border));
  background: var(--kn-ready-soft);
  color: var(--kn-ready);
}

.status-badge.embedding,
.status-badge.running {
  border-color: color-mix(in srgb, var(--kn-embedding) 45%, var(--kn-border));
  background: var(--kn-embedding-soft);
  color: var(--kn-embedding);
}

.status-badge.parsing,
.status-badge.idle {
  border-color: color-mix(in srgb, var(--kn-parsing) 45%, var(--kn-border));
  background: var(--kn-parsing-soft);
  color: var(--kn-parsing);
}

.status-badge.failed,
.status-badge.error {
  border-color: color-mix(in srgb, var(--kn-failed) 45%, var(--kn-border));
  background: var(--kn-failed-soft);
  color: var(--kn-failed);
}

.answer-preview {
  background: var(--kn-panel-soft);
  padding: 12px;
}

.answer-preview span {
  color: var(--kn-muted);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}

.answer-preview em {
  display: block;
  margin-top: 8px;
  color: var(--kn-muted);
  font-size: 11px;
  font-style: normal;
}

.documents-head {
  align-items: center;
}

.document-tools {
  flex-wrap: wrap;
  justify-content: flex-end;
}

.document-filter {
  width: min(100%, 340px);
}

.document-select {
  width: 140px;
}

.document-loading {
  display: grid;
  min-height: 180px;
  place-items: center;
  color: var(--kn-muted);
  font-size: 13px;
}

.document-table {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--kn-border);
  border-radius: 12px;
}

.document-table-head,
.document-row {
  display: grid;
  grid-template-columns: minmax(190px, 1.45fr) 82px 86px 74px 124px 138px minmax(150px, 1fr) 158px;
  min-width: 0;
}

.document-table-head {
  border-bottom: 1px solid var(--kn-border);
  background: var(--kn-panel-soft);
  color: var(--kn-muted);
  font-size: 10px;
  font-weight: 800;
}

.document-table-head > span,
.document-cell,
.document-actions {
  min-width: 0;
  padding: 10px;
}

.document-row {
  background: var(--kn-panel);
  transition: background 0.18s ease;
}

.document-row:hover {
  background: color-mix(in srgb, var(--kn-panel-soft) 48%, var(--kn-panel));
}

.document-row + .document-row {
  border-top: 1px solid var(--kn-border);
}

.document-main,
.document-primary {
  min-width: 0;
}

.document-primary {
  display: flex;
  align-items: center;
  gap: 8px;
}

.doc-title {
  min-width: 0;
  overflow: hidden;
  color: var(--kn-heading);
  font-size: 13px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-id,
.document-number,
.source-text,
.context-row dd,
.metadata-json {
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
}

.document-number {
  color: var(--kn-heading);
  font-size: 12px;
  font-weight: 800;
}

.document-time,
.source-text {
  overflow: hidden;
  color: var(--kn-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.document-actions {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
}

.advanced-configuration {
  margin-top: 14px;
}

.advanced-title {
  display: flex;
  min-width: 0;
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

.advanced-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  padding-top: 8px;
}

.advanced-card {
  padding: 14px;
}

.knowledge-strategy-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
}

.strategy-card {
  display: grid;
  min-height: 112px;
  gap: 8px;
  align-content: start;
  border: 1px solid var(--kn-border);
  border-radius: 10px;
  background: var(--kn-panel-soft);
  padding: 10px;
}

.strategy-card > div {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.strategy-card strong,
.panel-title {
  min-width: 0;
  color: var(--kn-heading);
  font-size: 12px;
  font-weight: 800;
  overflow-wrap: anywhere;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.strategy-card p {
  margin: 0;
  min-width: 0;
  color: var(--kn-muted);
  font-size: 11px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.strategy-card span,
.strategy-card em {
  display: inline-flex;
  min-width: 0;
  max-width: 100%;
  border: 1px solid var(--kn-border);
  border-radius: 999px;
  padding: 2px 7px;
  color: var(--kn-muted);
  font-size: 10px;
  font-style: normal;
  font-weight: 750;
  line-height: 1.35;
  overflow-wrap: anywhere;
  white-space: normal;
}

.rag-settings-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-top: 12px;
}

.toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid var(--kn-border);
  border-radius: 10px;
  background: var(--kn-panel-soft);
  padding: 9px 10px;
  color: var(--kn-muted);
  font-size: 12px;
  font-weight: 700;
}

.advanced-info-list {
  display: grid;
  gap: 10px;
  margin: 12px 0 0;
}

.context-row {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}

.context-row dt {
  color: var(--kn-muted);
  font-size: 12px;
}

.context-row dd {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--kn-heading);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-box {
  padding: 16px;
  color: var(--kn-muted);
  font-size: 12px;
  text-align: center;
}

.drawer-stack strong,
.drawer-stack p {
  display: block;
  margin: 5px 0 0;
  color: var(--kn-heading);
  overflow-wrap: anywhere;
}

.drawer-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.metadata-json {
  max-height: 360px;
  overflow: auto;
  border: 1px solid var(--kn-border);
  border-radius: 10px;
  background: var(--kn-panel-soft);
  padding: 12px;
  color: var(--kn-heading);
  font-size: 11px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.knowledge-upload :deep(.el-upload-dragger) {
  border-radius: 14px;
  background: var(--kn-panel-soft);
}

@media (max-width: 1320px) {
  .knowledge-stat-dashboard {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .knowledge-workspace-grid,
  .advanced-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 1120px) {
  .document-table-head {
    display: none;
  }

  .document-table {
    display: grid;
    gap: 10px;
    overflow: visible;
    border: 0;
  }

  .document-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    border: 1px solid var(--kn-border);
    border-radius: 12px;
  }

  .document-main,
  .document-actions {
    grid-column: 1 / -1;
  }

  .document-actions {
    justify-content: flex-start;
  }
}

@media (max-width: 760px) {
  .knowledge-console {
    padding: 12px;
  }

  .knowledge-stat-dashboard,
  .upload-mode-grid,
  .text-import-grid,
  .path-import-grid,
  .knowledge-upload-pipeline,
  .rag-settings-grid,
  .document-row {
    grid-template-columns: minmax(0, 1fr);
  }

  .knowledge-section-head,
  .documents-head,
  .playground-controls {
    flex-direction: column;
  }

  .document-tools,
  .document-filter,
  .document-select {
    width: 100%;
  }
}
</style>
