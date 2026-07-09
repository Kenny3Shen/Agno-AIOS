<template>
  <div class="knowledge-console knowledge-workflow-shell ag-page-flow">
    <section class="knowledge-document-workbench">
      <KnowledgeDocumentList
        :documents="documents"
        :selected-document-id="selectedDocumentId"
        :loading="loading"
        :clearing="clearing"
        :deleting-doc-id="deletingDocId"
        :rebuilding-doc-id="rebuildingDocId"
        :updating-doc-id="replacingSourceDocId"
        @add="openAddDrawer"
        @refresh="loadKnowledge"
        @clear="clearAllDocuments"
        @select="selectedDocumentId = $event"
        @update="openUpdateDrawer"
        @rebuild="rebuildDocument"
        @delete="deleteDocument"
        @visibility="updateDocumentVisibility"
      />
      <KnowledgeMetadataPanel :document="selectedDocument" />
    </section>

    <KnowledgeRetrievalPlayground
      :searching="searching"
      :searched="searched"
      :search-results="searchResults"
      :retrieval-answer="retrievalAnswer"
      :retrieval-references="retrievalReferences"
      @search="runSearch"
    />

    <KnowledgeIngestDrawer
      v-model="ingestDrawerOpen"
      :mode="ingestDrawerMode"
      :target-document="ingestTargetDocument"
      :status="status"
      :loading="drawerMutating"
      @submit-file="submitDrawerFileUpload"
      @submit-text="submitDrawerTextDocument"
      @submit-path="submitDrawerPathDocument"
      @submit-update-file="submitDrawerUpdateFile"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { useI18n } from "vue-i18n"
import { useKnowledgeApi } from "../composables/useKnowledgeApi"
import type { KnowledgeDocument, KnowledgeIngestOptions, KnowledgeSearchResult, KnowledgeStatus, ResourceVisibility } from "../types"
import { mergeUpdatedKnowledgeDocument, resolveSelectedKnowledgeDocumentId } from "../modules/knowledgeWorkbench"
import KnowledgeDocumentList from "./knowledge/KnowledgeDocumentList.vue"
import KnowledgeIngestDrawer from "./knowledge/KnowledgeIngestDrawer.vue"
import KnowledgeMetadataPanel from "./knowledge/KnowledgeMetadataPanel.vue"
import KnowledgeRetrievalPlayground from "./knowledge/KnowledgeRetrievalPlayground.vue"

type IngestDrawerMode = "add" | "update"

interface DrawerFilePayload {
  file: File
  title: string
  source: string
  visibility: ResourceVisibility
  ingest_options: KnowledgeIngestOptions | null
}

interface DrawerTextPayload {
  title: string
  content: string
  source: string
  metadata: Record<string, string>
  visibility: ResourceVisibility
  ingest_options: KnowledgeIngestOptions | null
}

interface DrawerPathPayload {
  path: string
  title: string
  source: string
  visibility: ResourceVisibility
  ingest_options: KnowledgeIngestOptions | null
}

interface DrawerUpdatePayload {
  document: KnowledgeDocument
  file: File
  title: string
  source: string
  metadata: Record<string, string>
  ingest_options: KnowledgeIngestOptions | null
}

const { t } = useI18n()

const status = ref<KnowledgeStatus | null>(null)
const documents = ref<KnowledgeDocument[]>([])
const selectedDocumentId = ref("")
const ingestDrawerOpen = ref(false)
const ingestDrawerMode = ref<IngestDrawerMode>("add")
const ingestTargetDocument = ref<KnowledgeDocument | null>(null)
const savingText = ref(false)
const savingPath = ref(false)
const uploadingBrowserFile = ref(false)
const deletingDocId = ref<string | null>(null)
const rebuildingDocId = ref<string | null>(null)
const replacingSourceDocId = ref<string | null>(null)
const clearing = ref(false)
const searching = ref(false)
const searched = ref(false)
const searchResults = ref<KnowledgeSearchResult[]>([])

const {
  loading,
  fetchKnowledge,
  addTextDocument,
  addFileDocument,
  updateKnowledgeDocumentVisibility,
  rebuildKnowledgeDocument,
  replaceKnowledgeDocumentSource,
  deleteKnowledgeDocument,
  clearKnowledge,
  searchKnowledge,
} = useKnowledgeApi()

const selectedDocument = computed(() => documents.value.find((doc) => doc.id === selectedDocumentId.value) || null)
const drawerMutating = computed(() => uploadingBrowserFile.value || savingText.value || savingPath.value || Boolean(replacingSourceDocId.value))

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
    const previousSelection = selectedDocumentId.value
    const data = await fetchKnowledge()
    status.value = data.status
    documents.value = data.documents
    selectedDocumentId.value = resolveSelectedKnowledgeDocumentId(documents.value, previousSelection)
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("knowledge.messages.loadFailed"))
  }
}

const isSupportedTextFile = (file: File) => {
  return /\.(md|markdown|txt|log|csv|tsv|json|jsonl|ya?ml|toml|py|js|jsx|ts|tsx|vue|go|rs|java|c|cc|cpp|h|hpp|cs|php|rb|sh|sql)$/i.test(file.name)
}

const fileMetadata = (file: File) => ({
  file_name: file.name,
  upload_mode: "browser",
  file_size: String(file.size),
  file_type: file.name.match(/\.[^.]+$/)?.[0]?.toLowerCase() || "text",
  mime_type: file.type || "text/plain",
})

const readKnowledgeFile = async (file: File) => {
  if (!isSupportedTextFile(file)) {
    throw new Error(t("knowledge.messages.selectTextFile"))
  }
  const content = (await file.text()).trim()
  if (!content) {
    throw new Error(t("knowledge.upload.emptyFile"))
  }
  return content
}

const closeDrawerAfterMutation = (nextSelectedId: string) => {
  selectedDocumentId.value = resolveSelectedKnowledgeDocumentId(documents.value, nextSelectedId)
  ingestDrawerOpen.value = false
  ingestTargetDocument.value = null
}

const submitDrawerFileUpload = async (payload: DrawerFilePayload) => {
  uploadingBrowserFile.value = true
  try {
    const content = await readKnowledgeFile(payload.file)
    const created = await addTextDocument({
      title: payload.title.trim() || payload.file.name.replace(/\.[^.]+$/i, ""),
      content,
      source: payload.source.trim() || `upload:${payload.file.name}`,
      visibility: payload.visibility,
      metadata: fileMetadata(payload.file),
      ingest_options: payload.ingest_options,
    })
    documents.value = [created, ...documents.value.filter((doc) => doc.id !== created.id)]
    await loadKnowledge()
    closeDrawerAfterMutation(created.id)
    ElMessage.success(t("knowledge.messages.updated"))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("knowledge.messages.taskFailed", { title: payload.title }))
  } finally {
    uploadingBrowserFile.value = false
  }
}

const submitDrawerTextDocument = async (payload: DrawerTextPayload) => {
  if (!payload.title.trim() || !payload.content.trim()) {
    ElMessage.warning(t("knowledge.messages.titleContentRequired"))
    return
  }
  savingText.value = true
  try {
    const created = await addTextDocument({
      title: payload.title.trim(),
      content: payload.content.trim(),
      source: payload.source.trim() || "manual",
      visibility: payload.visibility,
      metadata: payload.metadata,
      ingest_options: payload.ingest_options,
    })
    documents.value = [created, ...documents.value.filter((doc) => doc.id !== created.id)]
    await loadKnowledge()
    closeDrawerAfterMutation(created.id)
    ElMessage.success(t("knowledge.messages.updated"))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("knowledge.messages.taskFailed", { title: payload.title }))
  } finally {
    savingText.value = false
  }
}

const submitDrawerPathDocument = async (payload: DrawerPathPayload) => {
  if (!payload.path.trim()) {
    ElMessage.warning(t("knowledge.messages.pathRequired"))
    return
  }
  savingPath.value = true
  try {
    const created = await addFileDocument({
      path: payload.path.trim(),
      title: payload.title.trim() || null,
      source: payload.source.trim() || payload.path.trim(),
      visibility: payload.visibility,
      ingest_options: payload.ingest_options,
    })
    documents.value = [created, ...documents.value.filter((doc) => doc.id !== created.id)]
    await loadKnowledge()
    closeDrawerAfterMutation(created.id)
    ElMessage.success(t("knowledge.messages.updated"))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("knowledge.messages.taskFailed", { title: payload.path }))
  } finally {
    savingPath.value = false
  }
}

const submitDrawerUpdateFile = async (payload: DrawerUpdatePayload) => {
  const doc = payload.document
  replacingSourceDocId.value = doc.id
  try {
    const content = await readKnowledgeFile(payload.file)
    const updated = await replaceKnowledgeDocumentSource(doc.id, {
      title: payload.title || doc.title,
      content,
      file_name: payload.file.name,
      source: payload.source.trim() || `upload:${payload.file.name}`,
      metadata: {
        ...fileMetadata(payload.file),
        ...payload.metadata,
      },
      ingest_options: payload.ingest_options,
    })
    documents.value = mergeUpdatedKnowledgeDocument(documents.value, doc.id, updated)
    selectedDocumentId.value = updated.id
    await loadKnowledge()
    closeDrawerAfterMutation(updated.id)
    ElMessage.success(t("knowledge.messages.sourceReplaced"))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("knowledge.messages.sourceReplaceFailed"))
  } finally {
    replacingSourceDocId.value = null
  }
}

const openAddDrawer = () => {
  ingestDrawerMode.value = "add"
  ingestTargetDocument.value = null
  ingestDrawerOpen.value = true
}

const openUpdateDrawer = (doc: KnowledgeDocument) => {
  if (!doc.can_manage || replacingSourceDocId.value === doc.id) return
  ingestDrawerMode.value = "update"
  ingestTargetDocument.value = doc
  ingestDrawerOpen.value = true
}

const updateDocumentVisibility = async (doc: KnowledgeDocument, visibility: ResourceVisibility) => {
  if (!doc.can_manage) return
  const currentVisibility = doc.visibility || "private"
  if (visibility === currentVisibility) return
  try {
    const updated = await updateKnowledgeDocumentVisibility(doc.id, visibility)
    doc.visibility = updated.visibility || visibility
    doc.metadata = updated.metadata || doc.metadata
    ElMessage.success(t("visibility.updated"))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("visibility.updateFailed"))
  }
}

const rebuildDocument = async (doc: KnowledgeDocument) => {
  if (!doc.can_manage || rebuildingDocId.value) return
  rebuildingDocId.value = doc.id
  try {
    const updated = await rebuildKnowledgeDocument(doc.id)
    documents.value = documents.value.map((item) => item.id === doc.id ? { ...item, ...updated } : item)
    await loadKnowledge()
    selectedDocumentId.value = resolveSelectedKnowledgeDocumentId(documents.value, updated.id)
    ElMessage.success(t("knowledge.messages.rebuilt"))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("knowledge.messages.rebuildFailed"))
  } finally {
    rebuildingDocId.value = null
  }
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
    selectedDocumentId.value = resolveSelectedKnowledgeDocumentId(documents.value, selectedDocumentId.value)
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
    selectedDocumentId.value = ""
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

const runSearch = async (query: string, limit: number, searchType: string) => {
  if (!query.trim()) {
    ElMessage.warning(t("knowledge.retrieval.questionRequired"))
    return
  }
  searching.value = true
  searched.value = true
  try {
    const data = await searchKnowledge(query.trim(), limit, searchType)
    searchResults.value = data.results
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("knowledge.messages.searchFailed"))
  } finally {
    searching.value = false
  }
}

const shortId = (value: string) => {
  if (!value) return "-"
  return value.length > 14 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value
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
  color: var(--kn-text);
}

.knowledge-document-workbench {
  display: grid;
  grid-template-columns: minmax(0, 7fr) minmax(320px, 3fr);
  gap: 14px;
  align-items: start;
}

.retrieval-playground {
  margin-top: 14px;
}

@media (max-width: 1120px) {
  .knowledge-document-workbench {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 760px) {
  .knowledge-console {
    padding: 12px;
  }
}
</style>
