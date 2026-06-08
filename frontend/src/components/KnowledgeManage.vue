<template>
  <div class="knowledge-console mx-auto max-w-7xl space-y-4 text-[#15202B] dark:text-[#DCE7EF]">
    <header class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 class="text-lg font-semibold text-[#0F172A] dark:text-white">RAG 知识库</h3>
        <p class="mt-1 text-sm text-[#5F6F7C] dark:text-[#91A4B3]">
          文档写入、删除管理、检索验证与 RAG 参数配置
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <el-button class="cursor-pointer" :loading="loading" @click="loadKnowledge">
          <el-icon class="mr-1"><Refresh /></el-icon>
          刷新
        </el-button>
        <el-button
          type="danger"
          plain
          class="cursor-pointer"
          :disabled="documents.length === 0"
          :loading="clearing"
          @click="clearAllDocuments"
        >
          <el-icon class="mr-1"><Delete /></el-icon>
          清空
        </el-button>
      </div>
    </header>

    <section class="grid gap-3 md:grid-cols-4">
      <article v-for="metric in metrics" :key="metric.label" class="knowledge-metric">
        <span>{{ metric.label }}</span>
        <strong>{{ metric.value }}</strong>
        <em>{{ metric.hint }}</em>
      </article>
    </section>

    <div class="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_360px]">
      <main class="min-w-0 space-y-4">
        <section class="knowledge-panel">
          <div class="panel-title">
            <el-icon><Upload /></el-icon>
            写入知识
          </div>

          <el-tabs v-model="activeIngestTab" class="knowledge-tabs mt-4">
            <el-tab-pane label="文件上传" name="upload">
              <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
                <el-upload
                  ref="browserUploadRef"
                  v-model:file-list="browserFileList"
                  drag
                  :auto-upload="false"
                  :limit="1"
                  accept=".md,.markdown,.txt,.log,text/plain,text/markdown"
                  class="knowledge-upload"
                  :on-change="handleBrowserFileChange"
                  :on-remove="handleBrowserFileRemove"
                  :on-exceed="handleBrowserFileExceed"
                >
                  <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
                  <div class="el-upload__text">
                    拖入文件或 <em>选择文件</em>
                  </div>
                  <template #tip>
                    <div class="el-upload__tip">Markdown / TXT / LOG</div>
                  </template>
                </el-upload>

                <div class="space-y-3">
                  <label class="knowledge-field">
                    <span>标题</span>
                    <el-input v-model="browserForm.title" placeholder="默认使用文件名" clearable />
                  </label>
                  <label class="knowledge-field">
                    <span>来源</span>
                    <el-input v-model="browserForm.source" placeholder="upload" clearable />
                  </label>
                  <el-button
                    type="primary"
                    class="!w-full cursor-pointer"
                    :loading="uploadingBrowserFile"
                    @click="submitBrowserUpload"
                  >
                    <el-icon class="mr-1"><DocumentAdd /></el-icon>
                    写入选中文件
                  </el-button>
                </div>
              </div>
            </el-tab-pane>

            <el-tab-pane label="文本写入" name="text">
              <div class="grid gap-3 md:grid-cols-2">
                <label class="knowledge-field">
                  <span>标题</span>
                  <el-input v-model="textForm.title" placeholder="例如 应急处置规范" clearable />
                </label>
                <label class="knowledge-field">
                  <span>来源</span>
                  <el-input v-model="textForm.source" placeholder="manual" clearable />
                </label>
                <label class="knowledge-field md:col-span-2">
                  <span>内容</span>
                  <el-input
                    v-model="textForm.content"
                    type="textarea"
                    :rows="8"
                    placeholder="输入需要沉淀到知识库的文本"
                  />
                </label>
                <div class="md:col-span-2 flex justify-end">
                  <el-button
                    type="primary"
                    class="cursor-pointer"
                    :loading="savingText"
                    @click="submitTextDocument"
                  >
                    <el-icon class="mr-1"><DocumentAdd /></el-icon>
                    写入文本
                  </el-button>
                </div>
              </div>
            </el-tab-pane>

            <el-tab-pane label="服务端路径" name="path">
              <div class="grid gap-3 md:grid-cols-[minmax(0,1fr)_240px]">
                <label class="knowledge-field">
                  <span>文件路径</span>
                  <el-input v-model="pathForm.path" placeholder="/abs/path/report.md" clearable />
                </label>
                <label class="knowledge-field">
                  <span>标题</span>
                  <el-input v-model="pathForm.title" placeholder="可选" clearable />
                </label>
                <div class="md:col-span-2 flex justify-end">
                  <el-button
                    type="primary"
                    class="cursor-pointer"
                    :loading="savingPath"
                    @click="submitPathDocument"
                  >
                    <el-icon class="mr-1"><FolderOpened /></el-icon>
                    导入路径
                  </el-button>
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </section>

        <section class="knowledge-panel">
          <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div class="panel-title">
              <el-icon><Files /></el-icon>
              文档管理
            </div>
            <el-input
              v-model="documentQuery"
              class="document-filter"
              placeholder="按标题、来源或 ID 筛选"
              clearable
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </div>

          <div v-if="loading && documents.length === 0" class="py-12 text-center text-sm text-[#6B7C8A] dark:text-[#91A4B3]">
            <el-icon class="is-loading mr-2"><Loading /></el-icon>
            加载中...
          </div>

          <el-table
            v-else
            :data="filteredDocuments"
            class="knowledge-table"
            empty-text="暂无知识文档"
          >
            <el-table-column label="文档" min-width="260">
              <template #default="{ row }: { row: KnowledgeDocument }">
                <div class="min-w-0">
                  <div class="flex min-w-0 items-center gap-2">
                    <span class="doc-title truncate">{{ row.title }}</span>
                    <span class="doc-id">{{ row.id }}</span>
                  </div>
                  <div class="mt-2 flex flex-wrap gap-1.5">
                    <span
                      v-for="tag in metadataTags(row)"
                      :key="tag"
                      class="metadata-tag"
                    >
                      {{ tag }}
                    </span>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="来源" min-width="220">
              <template #default="{ row }: { row: KnowledgeDocument }">
                <span class="source-text" :title="row.source">{{ row.source || "manual" }}</span>
              </template>
            </el-table-column>
            <el-table-column label="Chunks" width="96" align="right">
              <template #default="{ row }: { row: KnowledgeDocument }">
                <span class="font-mono text-xs">{{ row.chunks }}</span>
              </template>
            </el-table-column>
            <el-table-column label="创建时间" width="170">
              <template #default="{ row }: { row: KnowledgeDocument }">
                <span class="text-xs text-[#6B7C8A] dark:text-[#91A4B3]">{{ formatDate(row.created_at) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="92" fixed="right" align="center">
              <template #default="{ row }: { row: KnowledgeDocument }">
                <el-button
                  type="danger"
                  text
                  class="cursor-pointer"
                  :loading="deletingDocId === row.id"
                  @click="deleteDocument(row)"
                >
                  <el-icon><Delete /></el-icon>
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </section>
      </main>

      <aside class="space-y-4">
        <section class="knowledge-panel">
          <div class="panel-title">
            <el-icon><DataLine /></el-icon>
            当前状态
          </div>
          <dl class="mt-4 space-y-3 text-xs">
            <div class="context-row">
              <dt>Collection</dt>
              <dd>{{ status?.collection || "-" }}</dd>
            </div>
            <div class="context-row">
              <dt>Embedding</dt>
              <dd>{{ status?.embedding || "-" }}</dd>
            </div>
            <div class="context-row">
              <dt>Chroma Path</dt>
              <dd :title="status?.path">{{ status?.path || "-" }}</dd>
            </div>
          </dl>
        </section>

        <section class="knowledge-panel">
          <div class="panel-title">
            <el-icon><Search /></el-icon>
            检索验证
          </div>
          <div class="mt-4 space-y-3">
            <el-input
              v-model="searchForm.query"
              type="textarea"
              :rows="3"
              placeholder="输入检索问题"
            />
            <div class="flex items-center gap-3">
              <span class="setting-label">Limit</span>
              <el-input-number v-model="searchForm.limit" :min="1" :max="20" size="small" />
              <el-button
                type="primary"
                class="ml-auto cursor-pointer"
                :loading="searching"
                @click="runSearch"
              >
                检索
              </el-button>
            </div>
          </div>

          <div class="mt-4 space-y-2">
            <div v-if="searching" class="empty-box">检索中...</div>
            <div v-else-if="searched && searchResults.length === 0" class="empty-box">暂无命中</div>
            <article
              v-for="result in searchResults"
              :key="`${result.doc_id}:${result.chunk_index}`"
              class="search-hit"
            >
              <div class="flex items-center justify-between gap-2">
                <strong class="truncate">{{ result.title || result.doc_id }}</strong>
                <span>{{ result.score }}</span>
              </div>
              <p class="mt-2 line-clamp-3">{{ result.content }}</p>
            </article>
          </div>
        </section>

        <section class="knowledge-panel">
          <div class="mb-4 flex items-center justify-between gap-3">
            <div class="panel-title">
              <el-icon><Setting /></el-icon>
              RAG 参数
            </div>
            <span class="placeholder-badge">占位</span>
          </div>

          <div class="space-y-4">
            <label class="knowledge-field">
              <span>Agent Top-K</span>
              <el-slider v-model="ragSettings.agentTopK" :min="1" :max="20" disabled />
            </label>
            <label class="knowledge-field">
              <span>Chunk Size</span>
              <el-input-number v-model="ragSettings.chunkSize" :min="200" :max="4000" :step="100" disabled class="!w-full" />
            </label>
            <label class="knowledge-field">
              <span>Chunk Overlap</span>
              <el-input-number v-model="ragSettings.chunkOverlap" :min="0" :max="800" :step="20" disabled class="!w-full" />
            </label>
            <label class="knowledge-field">
              <span>Embedding Provider</span>
              <el-select v-model="ragSettings.embeddingProvider" disabled>
                <el-option label="Local Hash 256" value="local-hash-256" />
                <el-option label="OpenAI-compatible" value="openai-compatible" />
                <el-option label="BGE / bge-m3" value="bge-m3" />
              </el-select>
            </label>
            <div class="flex items-center justify-between rounded-2 border border-[#D8E0E7] bg-[#F8FAFC] px-3 py-2 dark:border-[#22313A] dark:bg-[#0B151C]">
              <span class="setting-label">Reranker</span>
              <el-switch v-model="ragSettings.reranker" disabled />
            </div>
            <div class="grid grid-cols-2 gap-2">
              <el-tooltip content="后端配置接口待接入" placement="top">
                <el-button disabled class="!w-full">
                  保存参数
                </el-button>
              </el-tooltip>
              <el-tooltip content="向量重建接口待接入" placement="top">
                <el-button disabled class="!w-full">
                  重建索引
                </el-button>
              </el-tooltip>
            </div>
          </div>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import type { UploadFile, UploadFiles, UploadInstance, UploadUserFile } from "element-plus"
import {
  DataLine,
  Delete,
  DocumentAdd,
  Files,
  FolderOpened,
  Loading,
  Refresh,
  Search,
  Setting,
  Upload,
  UploadFilled,
} from "@element-plus/icons-vue"
import { useKnowledgeApi } from "../composables/useApi"
import type { KnowledgeDocument, KnowledgeSearchResult, KnowledgeStatus } from "../types"

type IngestTab = "upload" | "text" | "path"

const activeIngestTab = ref<IngestTab>("upload")
const status = ref<KnowledgeStatus | null>(null)
const documents = ref<KnowledgeDocument[]>([])
const documentQuery = ref("")
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
})

const ragSettings = reactive({
  agentTopK: 5,
  chunkSize: 1200,
  chunkOverlap: 160,
  embeddingProvider: "local-hash-256",
  reranker: false,
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

const metrics = computed(() => [
  { label: "Documents", value: status.value?.documents ?? documents.value.length, hint: "已登记文档" },
  { label: "Chunks", value: status.value?.chunks ?? totalChunks.value, hint: "向量切片数" },
  { label: "Embedding", value: status.value?.embedding || "unknown", hint: "当前向量实现" },
  { label: "Collection", value: status.value?.collection || "-", hint: "Chroma 集合" },
])

const totalChunks = computed(() => documents.value.reduce((sum, item) => sum + Number(item.chunks || 0), 0))

const filteredDocuments = computed(() => {
  const query = documentQuery.value.trim().toLowerCase()
  if (!query) return documents.value
  return documents.value.filter((item) => {
    const metadataText = Object.values(item.metadata || {}).join(" ")
    return [item.id, item.title, item.source, metadataText].some((text) => String(text || "").toLowerCase().includes(query))
  })
})

const loadKnowledge = async () => {
  try {
    const data = await fetchKnowledge()
    status.value = data.status
    documents.value = data.documents
    if (data.status.embedding) {
      ragSettings.embeddingProvider = data.status.embedding
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "加载知识库失败")
  }
}

const stripExtension = (name: string) => name.replace(/\.(md|markdown|txt|log)$/i, "")

const isSupportedTextFile = (file: File) => {
  return /\.(md|markdown|txt|log)$/i.test(file.name)
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
  ElMessage.warning("一次仅支持选择一个文件")
}

const resetBrowserUpload = () => {
  browserForm.title = ""
  browserForm.source = "upload"
  selectedBrowserFile.value = null
  browserFileList.value = []
  browserUploadRef.value?.clearFiles()
}

const submitBrowserUpload = async () => {
  const file = selectedBrowserFile.value
  if (!file) {
    ElMessage.warning("请选择文件")
    return
  }
  if (!isSupportedTextFile(file)) {
    ElMessage.warning("仅支持 md、markdown、txt、log 文件")
    return
  }

  uploadingBrowserFile.value = true
  try {
    const content = (await file.text()).trim()
    if (!content) {
      ElMessage.warning("文件内容为空")
      return
    }
    await addTextDocument({
      title: browserForm.title.trim() || stripExtension(file.name),
      content,
      source: browserForm.source.trim() || `upload:${file.name}`,
      metadata: {
        file_name: file.name,
        upload_mode: "browser",
        file_size: String(file.size),
        mime_type: file.type || "text/plain",
      },
    })
    resetBrowserUpload()
    await loadKnowledge()
    ElMessage.success("文件已写入知识库")
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "写入文件失败")
  } finally {
    uploadingBrowserFile.value = false
  }
}

const submitTextDocument = async () => {
  if (!textForm.title.trim() || !textForm.content.trim()) {
    ElMessage.warning("标题和内容不能为空")
    return
  }
  savingText.value = true
  try {
    await addTextDocument({
      title: textForm.title.trim(),
      content: textForm.content.trim(),
      source: textForm.source.trim() || "manual",
      metadata: { input_mode: "manual" },
    })
    textForm.title = ""
    textForm.source = "manual"
    textForm.content = ""
    await loadKnowledge()
    ElMessage.success("文本已写入知识库")
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "写入文本失败")
  } finally {
    savingText.value = false
  }
}

const submitPathDocument = async () => {
  if (!pathForm.path.trim()) {
    ElMessage.warning("文件路径不能为空")
    return
  }
  savingPath.value = true
  try {
    await addFileDocument({
      path: pathForm.path.trim(),
      title: pathForm.title.trim() || null,
    })
    pathForm.path = ""
    pathForm.title = ""
    await loadKnowledge()
    ElMessage.success("文件已导入知识库")
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "导入文件失败")
  } finally {
    savingPath.value = false
  }
}

const deleteDocument = async (doc: KnowledgeDocument) => {
  try {
    await ElMessageBox.confirm(`确认删除「${doc.title}」？`, "删除知识文档", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    })
    deletingDocId.value = doc.id
    await deleteKnowledgeDocument(doc.id)
    documents.value = documents.value.filter((item) => item.id !== doc.id)
    await loadKnowledge()
    ElMessage.success("知识文档已删除")
  } catch (err) {
    if (err !== "cancel" && err !== "close") {
      ElMessage.error(err instanceof Error ? err.message : "删除知识文档失败")
    }
  } finally {
    deletingDocId.value = null
  }
}

const clearAllDocuments = async () => {
  if (documents.value.length === 0) return
  try {
    await ElMessageBox.confirm("确认清空全部知识文档和向量切片？", "清空知识库", {
      confirmButtonText: "清空",
      cancelButtonText: "取消",
      type: "warning",
    })
    clearing.value = true
    await clearKnowledge()
    documents.value = []
    searchResults.value = []
    searched.value = false
    await loadKnowledge()
    ElMessage.success("知识库已清空")
  } catch (err) {
    if (err !== "cancel" && err !== "close") {
      ElMessage.error(err instanceof Error ? err.message : "清空知识库失败")
    }
  } finally {
    clearing.value = false
  }
}

const runSearch = async () => {
  const query = searchForm.query.trim()
  if (!query) {
    ElMessage.warning("检索问题不能为空")
    return
  }
  searching.value = true
  searched.value = true
  try {
    const data = await searchKnowledge(query, searchForm.limit)
    searchResults.value = data.results
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : "检索知识库失败")
  } finally {
    searching.value = false
  }
}

const metadataTags = (doc: KnowledgeDocument) => {
  return Object.entries(doc.metadata || {})
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${value}`)
}

const formatDate = (value: string) => {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

onMounted(() => {
  loadKnowledge()
})
</script>

<style scoped>
.knowledge-metric,
.knowledge-panel,
.search-hit {
  border: 1px solid #d8e0e7;
  border-radius: 8px;
  background: #ffffff;
}

.knowledge-metric {
  padding: 12px;
}

.knowledge-metric span,
.knowledge-metric em {
  display: block;
  color: #6b7c8a;
  font-size: 11px;
  font-style: normal;
}

.knowledge-metric strong {
  display: block;
  margin-top: 4px;
  overflow: hidden;
  color: #15202b;
  font-size: 16px;
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.knowledge-panel {
  padding: 14px;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #15202b;
  font-size: 13px;
  font-weight: 750;
}

.knowledge-field {
  display: grid;
  gap: 7px;
  min-width: 0;
}

.knowledge-field > span,
.setting-label {
  color: #526170;
  font-size: 12px;
  font-weight: 650;
}

.document-filter {
  width: min(100%, 320px);
}

.doc-title {
  color: #15202b;
  font-size: 13px;
  font-weight: 700;
}

.doc-id,
.metadata-tag,
.placeholder-badge {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  border: 1px solid #d8e0e7;
  border-radius: 999px;
  background: #f8fafc;
  color: #526170;
  font-size: 10px;
  font-weight: 700;
}

.doc-id {
  padding: 1px 7px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.metadata-tag,
.placeholder-badge {
  padding: 2px 7px;
}

.metadata-tag {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-text {
  display: block;
  overflow: hidden;
  color: #526170;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.context-row {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}

.context-row dt {
  color: #6b7c8a;
}

.context-row dd {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: #15202b;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-hit {
  padding: 10px;
}

.search-hit strong {
  color: #15202b;
  font-size: 12px;
  font-weight: 700;
}

.search-hit span {
  flex: 0 0 auto;
  color: #14824a;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  font-weight: 700;
}

.search-hit p {
  color: #526170;
  font-size: 12px;
  line-height: 1.6;
}

.empty-box {
  border: 1px solid #d8e0e7;
  border-radius: 8px;
  background: #f8fafc;
  padding: 14px;
  color: #6b7c8a;
  font-size: 12px;
  text-align: center;
}

.line-clamp-3 {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.knowledge-upload :deep(.el-upload-dragger) {
  border-radius: 8px;
  background: #f8fafc;
}

.knowledge-table :deep(.el-table__cell) {
  vertical-align: top;
}

html.dark .knowledge-metric,
html.dark .knowledge-panel,
html.dark .search-hit {
  border-color: #20313d;
  background: #0e171f;
}

html.dark .knowledge-metric span,
html.dark .knowledge-metric em,
html.dark .knowledge-field > span,
html.dark .setting-label,
html.dark .context-row dt,
html.dark .source-text,
html.dark .search-hit p {
  color: #91a4b3;
}

html.dark .knowledge-metric strong,
html.dark .panel-title,
html.dark .doc-title,
html.dark .context-row dd,
html.dark .search-hit strong {
  color: #dce7ef;
}

html.dark .doc-id,
html.dark .metadata-tag,
html.dark .placeholder-badge,
html.dark .empty-box {
  border-color: #2a3a45;
  background: #0b141b;
  color: #91a4b3;
}

html.dark .knowledge-upload :deep(.el-upload-dragger) {
  background: #0b151c;
  border-color: #22313a;
}

@media (max-width: 640px) {
  .context-row {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}
</style>
