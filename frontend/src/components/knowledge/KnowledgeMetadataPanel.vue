<template>
  <section class="knowledge-metadata-panel knowledge-panel ag-content-panel">
    <SectionHeader
      :title="t('knowledge.workbench.selectedMetadata')"
      :status-label="document ? shortId(document.id) : undefined"
      status-tone="blue"
    />

    <EmptyState v-if="!document" class="mt-3 min-h-[120px]">{{ t("knowledge.workbench.noSelection") }}</EmptyState>
    <el-descriptions v-else class="metadata-descriptions mt-3" :column="1" border size="small">
      <el-descriptions-item v-for="item in metadataItems" :key="item.label" :label="item.label">
        <span class="metadata-value" :title="item.value">{{ item.value }}</span>
      </el-descriptions-item>
    </el-descriptions>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { useI18n } from "vue-i18n"
import type { KnowledgeDocument } from "../../types"
import { knowledgeDocumentSize, knowledgeDocumentType } from "../../modules/knowledgeWorkbench"
import EmptyState from "../common/EmptyState.vue"
import SectionHeader from "../common/SectionHeader.vue"

const props = defineProps<{ document: KnowledgeDocument | null }>()

const { t, locale } = useI18n()
const documentType = knowledgeDocumentType

const shortId = (value: string) => value.length > 14 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value || "-"
const formatDate = (value: string) => {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(locale.value, { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })
}
const metadataValue = (key: string) => String(props.document?.metadata?.[key] || "").trim()
const displayValue = (value: string | number | null | undefined) => {
  const text = String(value || "").trim()
  return text || "-"
}

const metadataItems = computed(() => {
  const doc = props.document
  if (!doc) return []
  const primary = [
    { label: t("knowledge.drawer.documentName"), value: displayValue(doc.title) },
    { label: t("knowledge.drawer.type"), value: documentType(doc) },
    { label: t("knowledge.drawer.chunks"), value: String(doc.chunks) },
    { label: t("knowledge.drawer.updated"), value: formatDate(doc.created_at) },
  ]
  const secondary = [
    { label: t("knowledge.drawer.source"), value: displayValue(doc.source || metadataValue("source")) },
    { label: t("knowledge.drawer.readerStrategy"), value: displayValue(metadataValue("reader") || metadataValue("chunk_strategy")) },
    { label: t("knowledge.drawer.reference"), value: displayValue(metadataValue("file_name") || metadataValue("path")) },
    { label: t("knowledge.drawer.size"), value: knowledgeDocumentSize(doc) },
    { label: t("knowledge.documents.columns.visibility"), value: displayValue(doc.visibility || metadataValue("visibility")) },
    { label: t("knowledge.drawer.mime"), value: displayValue(metadataValue("mime_type") || metadataValue("file_type")) },
  ]
  return [...primary, ...secondary]
})
</script>

<style scoped>
.knowledge-metadata-panel {
  min-width: 0;
}

.metadata-descriptions {
  width: 100%;
  min-width: 0;
  overflow: hidden;
}

.metadata-descriptions :deep(.el-descriptions__table) {
  width: 100%;
  table-layout: fixed;
}

.metadata-descriptions :deep(.el-descriptions__label.el-descriptions__cell) {
  width: 108px;
  background: var(--kn-panel-soft);
  color: var(--kn-muted);
  font-size: 11px;
  font-weight: 760;
}

.metadata-descriptions :deep(.el-descriptions__content.el-descriptions__cell) {
  min-width: 0;
  background: var(--kn-panel);
}

.metadata-value {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--kn-heading);
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 12px;
  font-weight: 760;
}

</style>
