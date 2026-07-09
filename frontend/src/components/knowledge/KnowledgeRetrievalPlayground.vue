<template>
  <section class="knowledge-panel ag-content-panel retrieval-playground">
    <div class="knowledge-section-head">
      <h4>{{ t("knowledge.retrieval.title") }}</h4>
      <span class="status-badge embedding">{{ searchType }}</span>
    </div>

    <div class="playground-question">
      <el-input v-model="query" type="textarea" :rows="4" :placeholder="t('knowledge.retrieval.queryPlaceholder')" />
      <div class="playground-controls">
        <label class="knowledge-field">
          <span>{{ t("knowledge.labels.searchType") }}</span>
          <el-select v-model="searchType" size="small">
            <el-option :label="t('knowledge.labels.hybrid')" value="hybrid" />
            <el-option :label="t('knowledge.labels.vector')" value="vector" />
            <el-option :label="t('knowledge.labels.keyword')" value="keyword" />
          </el-select>
        </label>
        <label class="knowledge-field">
          <span>{{ t("knowledge.labels.topK") }}</span>
          <el-input-number v-model="limit" :min="1" :max="20" size="small" class="!w-full" />
        </label>
        <el-button type="primary" class="cursor-pointer" :disabled="searching || !query.trim()" :loading="searching" @click="emitSearch">
          {{ t("knowledge.actions.search") }}
        </el-button>
      </div>
    </div>

    <div class="playground-results">
      <div class="result-head">
        <strong>{{ t("knowledge.retrieval.resultTitle") }}</strong>
        <span>{{ t("knowledge.retrieval.resultCount", { count: searchResults.length }) }}</span>
      </div>

      <div v-if="searching" class="empty-box">
        <el-icon class="is-loading mr-1"><Loading /></el-icon>
        {{ t("knowledge.retrieval.searching") }}
      </div>
      <div v-else-if="searched && searchResults.length === 0" class="empty-box">{{ t("knowledge.retrieval.noResults") }}</div>
      <div v-else-if="!searched" class="empty-box">{{ t("knowledge.retrieval.idle") }}</div>

      <article v-for="result in searchResults" :key="`${result.doc_id}:${result.chunk_index}`" class="retrieval-hit">
        <div class="hit-toolbar">
          <strong class="truncate">{{ result.title || result.doc_id || t("knowledge.labels.untitledChunk") }}</strong>
          <span class="score-badge">{{ formatScore(result.score) }}</span>
        </div>
        <p>{{ result.content }}</p>
        <div class="hit-meta">
          <span>{{ t("knowledge.labels.chunkIndex", { index: result.chunk_index }) }}</span>
          <span :title="result.source">{{ t("knowledge.labels.sourceValue", { value: result.source || "-" }) }}</span>
          <span :title="result.doc_id">{{ t("knowledge.labels.docValue", { value: shortId(result.doc_id) }) }}</span>
        </div>
      </article>

      <div v-if="searchResults.length" class="answer-preview">
        <span>{{ t("knowledge.retrieval.answer") }}</span>
        <p>{{ retrievalAnswer }}</p>
        <em>{{ t("knowledge.retrieval.reference", { value: retrievalReferences }) }}</em>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from "vue"
import { useI18n } from "vue-i18n"
import { Loading } from "@element-plus/icons-vue"
import type { KnowledgeSearchResult } from "../../types"

defineProps<{
  searching: boolean
  searched: boolean
  searchResults: KnowledgeSearchResult[]
  retrievalAnswer: string
  retrievalReferences: string
}>()

const emit = defineEmits<{
  search: [query: string, limit: number, searchType: string]
}>()

const { t } = useI18n()
const query = ref("")
const limit = ref(5)
const searchType = ref("hybrid")

const emitSearch = () => {
  const cleanQuery = query.value.trim()
  if (!cleanQuery) return
  emit("search", cleanQuery, limit.value, searchType.value)
}

const formatScore = (value: number) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return "-"
  return n <= 1 ? n.toFixed(3) : n.toFixed(2)
}

const shortId = (value: string) => value ? (value.length > 12 ? `${value.slice(0, 8)}...` : value) : "-"
</script>

<style scoped>
.retrieval-playground {
  min-width: 0;
}

.knowledge-section-head,
.playground-controls,
.hit-toolbar,
.hit-meta {
  display: flex;
  gap: 12px;
}

.knowledge-section-head,
.hit-toolbar {
  align-items: center;
  justify-content: space-between;
}

.knowledge-section-head {
  margin-bottom: 12px;
}

.knowledge-section-head h4 {
  margin: 0;
  color: var(--kn-heading);
  font-size: 15px;
  font-weight: 820;
}

.playground-question,
.playground-results {
  display: grid;
  gap: 12px;
}

.playground-controls {
  align-items: end;
}

.knowledge-field {
  display: grid;
  flex: 1 1 160px;
  gap: 7px;
  min-width: 0;
}

.knowledge-field > span,
.result-head,
.hit-meta,
.answer-preview em,
.answer-preview span {
  color: var(--kn-muted);
  font-size: 12px;
}

.result-head {
  display: flex;
  justify-content: space-between;
}

.retrieval-hit,
.answer-preview,
.empty-box {
  border: 1px solid var(--kn-border);
  border-radius: 12px;
  background: var(--kn-panel);
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
  flex-wrap: wrap;
  margin-top: 10px;
}

.hit-meta span,
.score-badge,
.status-badge {
  display: inline-flex;
  border: 1px solid var(--kn-border);
  border-radius: 999px;
  background: var(--kn-panel-soft);
  color: var(--kn-muted);
  font-size: 10px;
  font-weight: 800;
  line-height: 1.3;
  padding: 3px 7px;
}

.status-badge.embedding {
  border-color: color-mix(in srgb, var(--kn-embedding) 45%, var(--kn-border));
  background: var(--kn-embedding-soft);
  color: var(--kn-embedding);
}

.answer-preview {
  background: var(--kn-panel-soft);
}

.empty-box {
  color: var(--kn-muted);
  text-align: center;
}

@media (max-width: 760px) {
  .playground-controls {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
