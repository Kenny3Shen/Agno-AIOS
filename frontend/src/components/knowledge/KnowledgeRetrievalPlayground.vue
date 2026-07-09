<template>
  <section class="knowledge-panel ag-content-panel retrieval-playground">
    <SectionHeader :title="t('knowledge.retrieval.title')">
      <template #actions>
        <StatusChip tone="blue">{{ searchType }}</StatusChip>
      </template>
    </SectionHeader>

    <div class="retrieval-compare-shell">
      <aside class="retrieval-control-rail">
        <el-input v-model="query" class="retrieval-query-input" type="textarea" :rows="6" :placeholder="t('knowledge.retrieval.queryPlaceholder')" />
        <div class="retrieval-control-stack">
          <label class="knowledge-field">
            <span>{{ t("knowledge.labels.searchType") }}</span>
            <el-select v-model="searchType" class="retrieval-control-select">
              <el-option :label="t('knowledge.labels.hybrid')" value="hybrid" />
              <el-option :label="t('knowledge.labels.vector')" value="vector" />
              <el-option :label="t('knowledge.labels.keyword')" value="keyword" />
            </el-select>
          </label>
          <label class="knowledge-field">
            <span>{{ t("knowledge.labels.topK") }}</span>
            <el-input-number v-model="limit" :min="1" :max="20" class="retrieval-control-number" />
          </label>
          <el-button type="primary" class="retrieval-control-button cursor-pointer" :disabled="searching || !query.trim()" :loading="searching" @click="emitSearch">
            {{ t("knowledge.actions.search") }}
          </el-button>
        </div>
      </aside>

      <section class="retrieval-results-panel">
        <PanelHeader
          :title="t('knowledge.retrieval.resultTitle')"
          :subtitle="t('knowledge.retrieval.resultCount', { count: searchResults.length })"
        />

        <div v-if="searchResults.length" class="answer-preview">
          <span>{{ t("knowledge.retrieval.answer") }}</span>
          <p>{{ retrievalAnswer }}</p>
          <em>{{ t("knowledge.retrieval.reference", { value: retrievalReferences }) }}</em>
        </div>

        <div class="retrieval-results-body">
          <EmptyState v-if="searching" class="min-h-full" :icon="Loading" loading>
            {{ t("knowledge.retrieval.searching") }}
          </EmptyState>
          <EmptyState v-else-if="searched && searchResults.length === 0" class="min-h-full">{{ t("knowledge.retrieval.noResults") }}</EmptyState>
          <EmptyState v-else-if="!searched" class="min-h-full">{{ t("knowledge.retrieval.idle") }}</EmptyState>

          <article v-for="result in searchResults" :key="`${result.doc_id}:${result.chunk_index}`" class="retrieval-hit">
            <div class="hit-toolbar">
              <strong class="truncate">{{ result.title || result.doc_id || t("knowledge.labels.untitledChunk") }}</strong>
              <DataChip
                :label="t('knowledge.labels.score')"
                :value="formatScore(result.score)"
              />
            </div>
            <p>{{ result.content }}</p>
            <div class="hit-meta">
              <DataChip :label="t('knowledge.labels.chunk')" :value="result.chunk_index" />
              <DataChip
                :label="t('knowledge.labels.source')"
                :value="result.source || '-'"
                :title="result.source || '-'"
              />
              <DataChip
                :label="t('knowledge.labels.document')"
                :value="shortId(result.doc_id)"
                :title="result.doc_id || '-'"
              />
            </div>
          </article>
        </div>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from "vue"
import { useI18n } from "vue-i18n"
import { Loading } from "@element-plus/icons-vue"
import type { KnowledgeSearchResult } from "../../types"
import DataChip from "../common/DataChip.vue"
import EmptyState from "../common/EmptyState.vue"
import PanelHeader from "../common/PanelHeader.vue"
import SectionHeader from "../common/SectionHeader.vue"
import StatusChip from "../common/StatusChip.vue"

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
  padding: 0;
}

.retrieval-control-stack,
.hit-toolbar,
.hit-meta {
  display: flex;
  gap: 10px;
}

.hit-toolbar {
  align-items: center;
  justify-content: space-between;
}

.retrieval-compare-shell {
  display: grid;
  grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);
  min-height: 228px;
  background: var(--kn-panel);
}

.retrieval-control-rail {
  display: grid;
  align-content: start;
  gap: 12px;
  border-right: 1px solid var(--kn-border);
  background: color-mix(in srgb, var(--kn-panel-soft) 72%, transparent);
  padding: 12px;
}

.retrieval-query-input :deep(.el-textarea__inner) {
  min-height: 118px;
  resize: vertical;
}

.retrieval-control-stack {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: stretch;
}

.knowledge-field {
  display: grid;
  flex: 1 1 160px;
  gap: 7px;
  min-width: 0;
}

.knowledge-field > span,
.answer-preview em,
.answer-preview span {
  color: var(--kn-muted);
  font-size: 12px;
}

.retrieval-results-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  padding: 12px;
}

.retrieval-control-select,
.retrieval-control-number,
.retrieval-control-button {
  width: 100%;
  min-height: 36px;
}

.retrieval-control-select :deep(.el-select__wrapper),
.retrieval-control-number :deep(.el-input__wrapper) {
  min-height: 36px;
  font-size: 13px;
}

.retrieval-control-number :deep(.el-input-number__decrease),
.retrieval-control-number :deep(.el-input-number__increase) {
  width: 34px;
}

.retrieval-results-body {
  display: grid;
  flex: 1 1 auto;
  gap: 10px;
  min-height: 0;
  font-size: 13px;
}

.retrieval-hit,
.answer-preview {
  border: 1px solid var(--kn-border);
  border-radius: var(--ag-radius-control);
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
  font-size: 13px;
  line-height: 1.65;
}

.hit-meta {
  flex-wrap: wrap;
  margin-top: 10px;
}

.answer-preview {
  display: grid;
  gap: 5px;
  background: color-mix(in srgb, var(--kn-embedding-soft) 28%, var(--kn-panel-soft));
}

.answer-preview p {
  margin: 0;
}

@media (max-width: 980px) {
  .retrieval-compare-shell {
    grid-template-columns: minmax(0, 1fr);
  }

  .retrieval-control-rail {
    border-right: 0;
    border-bottom: 1px solid var(--kn-border);
  }
}
</style>
