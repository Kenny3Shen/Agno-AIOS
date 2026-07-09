<template>
  <section class="knowledge-document-list">
    <div class="document-management-bar">
      <div class="document-management-title">
        <h4>{{ t("knowledge.workbench.documents") }}</h4>
        <span>{{ t("knowledge.documents.visibleCount", { count: filteredDocuments.length, total: documents.length }) }}</span>
      </div>
      <div class="document-management-controls">
        <div class="document-command-group">
          <el-tooltip :content="t('shell.actions.refresh')" placement="top">
            <el-button size="small" class="cursor-pointer" :loading="loading" @click="$emit('refresh')">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip :content="t('knowledge.actions.clear')" placement="top">
            <el-button type="danger" plain size="small" class="cursor-pointer" :disabled="documents.length === 0" :loading="clearing" @click="$emit('clear')">
              <el-icon><Delete /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip :content="t('knowledge.workbench.addDocument')" placement="top">
            <el-button type="primary" size="small" class="cursor-pointer" @click="$emit('add')">
              <el-icon><DocumentAdd /></el-icon>
            </el-button>
          </el-tooltip>
        </div>
        <el-input v-model="query" class="document-filter" :placeholder="t('knowledge.documents.searchPlaceholder')" clearable>
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </div>
    </div>

    <div v-if="loading && documents.length === 0" class="document-loading">
      <el-icon class="is-loading"><Loading /></el-icon>
      {{ t("knowledge.documents.loading") }}
    </div>

    <div v-else class="document-table document-list-compact" role="table" :aria-label="t('knowledge.documents.ariaLabel')">
      <div class="document-table-head" role="row">
        <span role="columnheader">{{ t("knowledge.documents.columns.name") }}</span>
        <span role="columnheader">{{ t("knowledge.documents.columns.embeddingStatus") }}</span>
        <span role="columnheader">{{ t("knowledge.documents.columns.visibility") }}</span>
        <span role="columnheader" class="document-actions-head">{{ t("knowledge.documents.columns.actions") }}</span>
      </div>

      <div v-if="filteredDocuments.length === 0" class="empty-box">{{ t("knowledge.documents.empty") }}</div>

      <article
        v-for="row in filteredDocuments"
        :key="row.id"
        class="document-row"
        :class="{ selected: row.id === selectedDocumentId }"
        role="row"
        @click="$emit('select', row.id)"
      >
        <div class="document-cell document-main" role="cell">
          <span class="doc-title" :title="row.title">{{ row.title }}</span>
          <em>{{ documentType(row) }} · {{ row.chunks }} chunks</em>
        </div>
        <div class="document-cell" role="cell" :data-label="t('knowledge.documents.columns.embeddingStatus')">
          <span class="status-badge" :class="documentStatus(row).tone">{{ t(documentStatus(row).labelKey) }}</span>
        </div>
        <div class="document-cell document-visibility-cell" role="cell" :data-label="t('knowledge.documents.columns.visibility')">
          <ResourceVisibilityTabs
            :model-value="row.visibility || 'private'"
            class="document-visibility-tabs"
            :disabled="!row.can_manage"
            :aria-label="t('knowledge.documents.visibilityLabel', { title: row.title })"
            @click.stop
            @update:model-value="(value) => updateDocumentVisibility(row, value)"
          />
        </div>
        <div class="document-actions" role="cell" :data-label="t('knowledge.documents.columns.actions')" @click.stop>
          <div class="document-action-buttons">
            <el-tooltip :content="t('knowledge.workbench.updateDocument')" placement="top">
              <el-button text class="cursor-pointer" :disabled="!row.can_manage || updatingDocId === row.id" :loading="updatingDocId === row.id" :aria-label="t('knowledge.documents.replaceSourceLabel', { title: row.title })" @click="$emit('update', row)">
                <el-icon><UploadFilled /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip :content="t('knowledge.documents.rebuild')" placement="top">
              <el-button text class="cursor-pointer" :disabled="!row.can_manage || rebuildingDocId === row.id" :loading="rebuildingDocId === row.id" :aria-label="t('knowledge.documents.reEmbeddingLabel', { title: row.title })" @click="$emit('rebuild', row)">
                <el-icon><RefreshRight /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip :content="t('knowledge.documents.delete')" placement="top">
              <el-button type="danger" text class="cursor-pointer" :loading="deletingDocId === row.id" :aria-label="t('knowledge.documents.deleteLabel', { title: row.title })" @click="$emit('delete', row)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </el-tooltip>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue"
import { useI18n } from "vue-i18n"
import { Delete, DocumentAdd, Loading, Refresh, RefreshRight, Search, UploadFilled } from "@element-plus/icons-vue"
import type { KnowledgeDocument, ResourceVisibility } from "../../types"
import { knowledgeDocumentStatus, knowledgeDocumentType } from "../../modules/knowledgeWorkbench"
import ResourceVisibilityTabs from "../common/ResourceVisibilityTabs.vue"

const props = defineProps<{
  documents: KnowledgeDocument[]
  selectedDocumentId: string
  loading: boolean
  clearing: boolean
  deletingDocId: string | null
  rebuildingDocId: string | null
  updatingDocId: string | null
}>()

const emit = defineEmits<{
  add: []
  refresh: []
  clear: []
  select: [documentId: string]
  update: [document: KnowledgeDocument]
  rebuild: [document: KnowledgeDocument]
  delete: [document: KnowledgeDocument]
  visibility: [document: KnowledgeDocument, visibility: ResourceVisibility]
}>()

const { t } = useI18n()
const query = ref("")
const documentType = knowledgeDocumentType
const documentStatus = knowledgeDocumentStatus

const filteredDocuments = computed(() => {
  const value = query.value.trim().toLowerCase()
  if (!value) return props.documents
  return props.documents.filter((doc) => {
    const metadataText = Object.values(doc.metadata || {}).join(" ")
    return [doc.id, doc.title, doc.source, metadataText].some((text) => String(text || "").toLowerCase().includes(value))
  })
})

const updateDocumentVisibility = (document: KnowledgeDocument, visibility: ResourceVisibility) => {
  emit("visibility", document, visibility)
}
</script>

<style scoped>
.knowledge-document-list {
  min-width: 0;
}

.document-management-bar {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 12px;
  border: 1px solid var(--kn-border);
  border-radius: var(--ag-radius-control);
  background: var(--kn-panel-soft);
  padding: 12px;
}

.document-management-title {
  display: grid;
  min-width: min(220px, 100%);
  gap: 4px;
}

.document-management-title h4 {
  margin: 0;
  color: var(--kn-heading);
  font-size: 15px;
  font-weight: 820;
}

.document-management-title span {
  color: var(--kn-muted);
  font-size: 12px;
}

.document-management-controls,
.document-command-group {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.document-management-controls {
  flex: 1 1 auto;
  flex-wrap: wrap;
}

.document-command-group :deep(.el-button) {
  width: 32px;
  height: 32px;
  margin-left: 0;
  padding: 0;
}

.document-filter {
  width: min(100%, 320px);
}

.document-loading,
.empty-box {
  display: grid;
  min-height: 120px;
  place-items: center;
  color: var(--kn-muted);
  font-size: 12px;
  text-align: center;
}

.document-table {
  --document-table-font-size: 11px;

  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--kn-border);
  border-radius: 12px;
}

.document-table-head,
.document-row {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(84px, 0.34fr) minmax(96px, 0.38fr) 132px;
  min-width: 0;
  font-size: var(--document-table-font-size);
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
  padding: 8px 7px;
}

.document-actions-head,
.document-actions {
  display: flex;
  justify-content: flex-start;
}

.document-row {
  background: var(--kn-panel);
  transition: background 0.18s ease;
}

.document-row.selected {
  border-color: color-mix(in srgb, var(--kn-embedding) 56%, var(--kn-border));
  background: color-mix(in srgb, var(--kn-embedding-soft) 44%, var(--kn-panel));
  box-shadow: inset 3px 0 0 var(--kn-embedding);
}

.document-row + .document-row {
  border-top: 1px solid var(--kn-border);
}

.document-main {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.document-main em,
.doc-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-title {
  color: var(--kn-heading);
  font-size: 12px;
  font-weight: 760;
}

.document-main em {
  color: var(--kn-muted);
  font-size: 11px;
  font-style: normal;
}

.document-visibility-cell {
  display: flex;
  align-items: center;
}

.document-visibility-tabs {
  --visibility-tab-font-size: 10px;
  --visibility-tab-height: 24px;
  --visibility-tab-min-width: 44px;
  --visibility-tab-padding: 3px 6px;

  width: max-content;
  max-width: 100%;
}

.document-actions,
.document-action-buttons {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: 2px;
}

.document-action-buttons :deep(.el-button) {
  width: 24px;
  height: 24px;
  margin-left: 0;
  padding: 0;
}

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

.status-badge.ready {
  border-color: color-mix(in srgb, var(--kn-ready) 45%, var(--kn-border));
  background: var(--kn-ready-soft);
  color: var(--kn-ready);
}

.status-badge.parsing {
  border-color: color-mix(in srgb, var(--kn-parsing) 45%, var(--kn-border));
  background: var(--kn-parsing-soft);
  color: var(--kn-parsing);
}

.status-badge.failed {
  border-color: color-mix(in srgb, var(--kn-failed) 45%, var(--kn-border));
  background: var(--kn-failed-soft);
  color: var(--kn-failed);
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

  .document-cell:not(.document-main),
  .document-actions {
    display: grid;
    grid-template-columns: minmax(72px, 96px) minmax(0, 1fr);
    gap: 8px;
    align-items: center;
  }

  .document-cell:not(.document-main)::before,
  .document-actions::before {
    content: attr(data-label);
    color: var(--kn-muted);
    font-size: 10px;
    font-weight: 800;
  }
}
</style>
