<template>
  <section class="knowledge-document-list">
    <div class="document-management-bar">
      <SectionHeader
        class="min-w-[min(220px,100%)] flex-1 border-b-0 pb-0"
        :title="t('knowledge.workbench.documents')"
        :subtitle="t('knowledge.documents.visibleCount', { count: documents.length, total })"
      />
      <div class="document-management-controls">
        <div class="document-command-group">
          <el-tooltip :content="t('shell.actions.refresh')" placement="top">
            <el-button size="small" class="cursor-pointer" :loading="loading" @click="$emit('refresh')">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip :content="t('knowledge.actions.clear')" placement="top">
            <el-button type="danger" plain size="small" class="cursor-pointer" :disabled="total === 0" :loading="clearing" @click="$emit('clear')">
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

    <el-table
      v-loading="loading"
      class="document-table document-table-desktop"
      :data="documents"
      row-key="id"
      :row-class-name="documentRowClass"
      :empty-text="t('knowledge.documents.empty')"
      @row-click="(row: KnowledgeDocument) => $emit('select', row.id)"
      @sort-change="handleSortChange"
    >
      <el-table-column prop="title" :label="t('knowledge.documents.columns.name')" min-width="210" sortable="custom">
        <template #default="{ row }: { row: KnowledgeDocument }">
          <div class="document-main">
            <span class="doc-title" :title="row.title">{{ row.title }}</span>
            <span class="document-subline">{{ documentType(row) }} · {{ row.chunks }} chunks</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="status" :label="t('knowledge.documents.columns.embeddingStatus')" width="116" sortable="custom">
        <template #default="{ row }: { row: KnowledgeDocument }">
          <StatusChip :tone="documentStatusTone(documentStatus(row).tone)">
            {{ t(documentStatus(row).labelKey) }}
          </StatusChip>
        </template>
      </el-table-column>
      <el-table-column :label="t('knowledge.documents.columns.visibility')" width="150">
        <template #default="{ row }: { row: KnowledgeDocument }">
          <ResourceVisibilityTabs
            :model-value="row.visibility || 'private'"
            class="document-visibility-tabs"
            :disabled="!row.can_manage"
            :aria-label="t('knowledge.documents.visibilityLabel', { title: row.title })"
            @click.stop
            @update:model-value="(value) => updateDocumentVisibility(row, value)"
          />
        </template>
      </el-table-column>
      <el-table-column :label="t('knowledge.documents.columns.actions')" width="132" fixed="right">
        <template #default="{ row }: { row: KnowledgeDocument }">
          <DocumentActions
            :row="row"
            :deleting-doc-id="deletingDocId || undefined"
            :rebuilding-doc-id="rebuildingDocId || undefined"
            :updating-doc-id="updatingDocId || undefined"
            @update="$emit('update', row)"
            @rebuild="$emit('rebuild', row)"
            @delete="$emit('delete', row)"
          />
        </template>
      </el-table-column>
    </el-table>

    <div v-loading="loading" class="document-list-mobile">
      <EmptyState v-if="!documents.length && !loading" class="min-h-[120px]">{{ t("knowledge.documents.empty") }}</EmptyState>
      <article
        v-for="row in documents"
        :key="row.id"
        class="document-card"
        :class="{ selected: row.id === selectedDocumentId }"
        tabindex="0"
        @click="$emit('select', row.id)"
        @keydown.enter.prevent="$emit('select', row.id)"
        @keydown.space.prevent="$emit('select', row.id)"
      >
        <div class="document-main">
          <span class="doc-title" :title="row.title">{{ row.title }}</span>
          <span class="document-subline">{{ documentType(row) }} · {{ row.chunks }} chunks</span>
        </div>
        <div class="document-card-field">
          <span>{{ t("knowledge.documents.columns.embeddingStatus") }}</span>
          <StatusChip :tone="documentStatusTone(documentStatus(row).tone)">{{ t(documentStatus(row).labelKey) }}</StatusChip>
        </div>
        <div class="document-card-field" @click.stop>
          <span>{{ t("knowledge.documents.columns.visibility") }}</span>
          <ResourceVisibilityTabs
            :model-value="row.visibility || 'private'"
            class="document-visibility-tabs"
            :disabled="!row.can_manage"
            :aria-label="t('knowledge.documents.visibilityLabel', { title: row.title })"
            @update:model-value="(value) => updateDocumentVisibility(row, value)"
          />
        </div>
        <div class="document-card-actions" @click.stop>
          <DocumentActions
            :row="row"
            :deleting-doc-id="deletingDocId || undefined"
            :rebuilding-doc-id="rebuildingDocId || undefined"
            :updating-doc-id="updatingDocId || undefined"
            @update="$emit('update', row)"
            @rebuild="$emit('rebuild', row)"
            @delete="$emit('delete', row)"
          />
        </div>
      </article>
    </div>

    <div v-if="total > pageSize" class="document-pagination">
      <el-pagination
        small
        background
        layout="prev, pager, next"
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        @current-change="$emit('page-change', $event)"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { defineComponent, h } from "vue"
import { useI18n } from "vue-i18n"
import { Delete, DocumentAdd, Refresh, RefreshRight, Search, UploadFilled } from "@element-plus/icons-vue"
import { ElButton, ElIcon, ElTooltip } from "element-plus"
import type { KnowledgeDocument, KnowledgePagination, ResourceVisibility } from "../../types"
import { knowledgeDocumentStatus, knowledgeDocumentType } from "../../modules/knowledgeWorkbench"
import EmptyState from "../common/EmptyState.vue"
import ResourceVisibilityTabs from "../common/ResourceVisibilityTabs.vue"
import SectionHeader from "../common/SectionHeader.vue"
import StatusChip from "../common/StatusChip.vue"

const props = defineProps<{
  documents: KnowledgeDocument[]
  selectedDocumentId: string
  page: number
  pageSize: number
  total: number
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
  "page-change": [page: number]
  "sort-change": [sort: { sortBy: KnowledgePagination["sort_by"]; sortOrder: KnowledgePagination["sort_order"] }]
}>()

const query = defineModel<string>("query", { default: "" })
const { t } = useI18n()
const documentType = knowledgeDocumentType
const documentStatus = knowledgeDocumentStatus
const documentStatusTone = (tone: string) => {
  if (tone === "ready") return "green"
  if (tone === "parsing") return "yellow"
  if (tone === "failed") return "red"
  return "muted"
}

const documentRowClass = ({ row }: { row: KnowledgeDocument }) => row.id === props.selectedDocumentId ? "is-selected" : ""

const handleSortChange = ({ prop, order }: { prop: string; order: string | null }) => {
  if (!order) {
    emit("sort-change", { sortBy: "updated_at", sortOrder: "desc" })
    return
  }
  emit("sort-change", {
    sortBy: prop === "title" ? "name" : "status",
    sortOrder: order === "ascending" ? "asc" : "desc",
  })
}

const updateDocumentVisibility = (document: KnowledgeDocument, visibility: ResourceVisibility) => {
  emit("visibility", document, visibility)
}

const DocumentActions = defineComponent({
  props: {
    row: { type: Object as () => KnowledgeDocument, required: true },
    deletingDocId: { type: String, default: null },
    rebuildingDocId: { type: String, default: null },
    updatingDocId: { type: String, default: null },
  },
  emits: ["update", "rebuild", "delete"],
  setup(actionProps, { emit: actionEmit }) {
    const action = (label: string, icon: typeof UploadFilled, options: { danger?: boolean; loading?: boolean; disabled?: boolean }, event: "update" | "rebuild" | "delete") => h(
      ElTooltip,
      { content: label, placement: "top" },
      { default: () => h(ElButton, {
        text: true,
        type: options.danger ? "danger" : undefined,
        loading: options.loading,
        disabled: options.disabled,
        "aria-label": label,
        onClick: () => actionEmit(event),
      }, { default: () => h(ElIcon, null, { default: () => h(icon) }) }) },
    )
    return () => h("div", { class: "document-action-buttons" }, [
      action(t("knowledge.workbench.updateDocument"), UploadFilled, {
        loading: actionProps.updatingDocId === actionProps.row.id,
        disabled: !actionProps.row.can_manage || actionProps.updatingDocId === actionProps.row.id,
      }, "update"),
      action(t("knowledge.documents.rebuild"), RefreshRight, {
        loading: actionProps.rebuildingDocId === actionProps.row.id,
        disabled: !actionProps.row.can_manage || actionProps.rebuildingDocId === actionProps.row.id,
      }, "rebuild"),
      action(t("knowledge.documents.delete"), Delete, {
        danger: true,
        loading: actionProps.deletingDocId === actionProps.row.id,
        disabled: !actionProps.row.can_manage,
      }, "delete"),
    ])
  },
})
</script>

<style scoped>
.knowledge-document-list { min-width: 0; }
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
.document-management-controls, .document-command-group { display: flex; min-width: 0; align-items: center; justify-content: flex-end; gap: 8px; }
.document-management-controls { flex: 1 1 auto; flex-wrap: wrap; }
.document-command-group :deep(.el-button) { width: 32px; height: 32px; margin-left: 0; padding: 0; }
.document-filter { width: min(100%, 320px); }
.document-table { width: 100%; border: 1px solid var(--kn-border); border-radius: var(--ag-radius-panel); overflow: hidden; }
.document-table :deep(th.el-table__cell) { background: var(--kn-panel-soft); color: var(--kn-muted); font-size: 10px; font-weight: 800; }
.document-table :deep(td.el-table__cell) { background: var(--kn-panel); padding: 7px 0; }
.document-table :deep(.el-table__row) { cursor: pointer; }
.document-table :deep(.el-table__row:hover > td.el-table__cell) { background: var(--kn-embedding-soft); }
.document-table :deep(.el-table__row.is-selected > td.el-table__cell) { background: color-mix(in srgb, var(--kn-embedding-soft) 52%, var(--kn-panel)); }
.document-table :deep(.el-table__row.is-selected > td:first-child) { box-shadow: inset 3px 0 0 var(--kn-embedding); }
.document-main { display: grid; min-width: 0; gap: 3px; }
.doc-title, .document-subline { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.doc-title { color: var(--kn-heading); font-size: 12px; font-weight: 760; }
.document-subline { color: var(--kn-muted); font-size: 11px; }
.document-visibility-tabs { --visibility-tab-font-size: 10px; --visibility-tab-height: 24px; --visibility-tab-min-width: 44px; --visibility-tab-padding: 3px 6px; width: max-content; max-width: 100%; }
:deep(.document-action-buttons) { display: inline-flex; align-items: center; gap: 2px; }
:deep(.document-action-buttons .el-button) { width: 24px; height: 24px; margin-left: 0; padding: 0; }
.document-list-mobile { display: none; min-height: 120px; }
.document-pagination { display: flex; justify-content: flex-end; padding-top: 12px; }

@media (max-width: 1120px) {
  .document-table-desktop { display: none; }
  .document-list-mobile { display: grid; gap: 10px; }
  .document-card { display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px; border: 1px solid var(--kn-border); border-radius: var(--ag-radius-panel); background: var(--kn-panel); padding: 12px; outline: none; }
  .document-card:hover, .document-card:focus-visible { border-color: color-mix(in srgb, var(--kn-embedding) 44%, var(--kn-border)); background: var(--kn-embedding-soft); }
  .document-card.selected { box-shadow: inset 3px 0 0 var(--kn-embedding); }
  .document-card-field { display: grid; grid-template-columns: minmax(84px, 110px) minmax(0, 1fr); align-items: center; gap: 8px; }
  .document-card-field > span { color: var(--kn-muted); font-size: 10px; font-weight: 800; }
  .document-card-actions { display: flex; justify-content: flex-end; }
}

@media (max-width: 680px) {
  .document-management-bar { align-items: stretch; flex-direction: column; }
  .document-management-controls { justify-content: space-between; }
  .document-filter { flex: 1 1 200px; }
}
</style>
