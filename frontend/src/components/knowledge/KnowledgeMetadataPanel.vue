<template>
  <section class="knowledge-metadata-panel knowledge-panel ag-content-panel">
    <SectionHeader
      :title="t('knowledge.workbench.selectedMetadata')"
      :status-label="document ? shortId(document.id) : undefined"
      status-tone="blue"
    />

    <EmptyState v-if="!document" class="mt-3 min-h-[120px]">{{ t("knowledge.workbench.noSelection") }}</EmptyState>
    <template v-else>
      <div class="knowledge-runtime-summary metadata-primary mt-3">
        <DataChip
          v-for="item in primaryItems"
          :key="item.label"
          :label="item.label"
          :value="item.value"
          :title="item.value"
        />
      </div>

      <div class="metadata-secondary">
        <div v-for="item in secondaryItems" :key="item.label" class="metadata-row">
          <span>{{ item.label }}</span>
          <strong :title="item.value">{{ item.value }}</strong>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { useI18n } from "vue-i18n"
import type { KnowledgeDocument } from "../../types"
import { knowledgeDocumentSize, knowledgeDocumentType } from "../../modules/knowledgeWorkbench"
import DataChip from "../common/DataChip.vue"
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

const primaryItems = computed(() => {
  const doc = props.document
  if (!doc) return []
  return [
    { label: t("knowledge.drawer.documentName"), value: displayValue(doc.title) },
    { label: t("knowledge.drawer.type"), value: documentType(doc) },
    { label: t("knowledge.drawer.chunks"), value: String(doc.chunks) },
    { label: t("knowledge.drawer.updated"), value: formatDate(doc.created_at) },
  ]
})

const secondaryItems = computed(() => {
  const doc = props.document
  if (!doc) return []
  return [
    { label: t("knowledge.drawer.source"), value: displayValue(doc.source || metadataValue("source")) },
    { label: t("knowledge.drawer.readerStrategy"), value: displayValue(metadataValue("reader") || metadataValue("chunk_strategy")) },
    { label: t("knowledge.drawer.reference"), value: displayValue(metadataValue("file_name") || metadataValue("path")) },
    { label: t("knowledge.drawer.size"), value: knowledgeDocumentSize(doc) },
    { label: t("knowledge.documents.columns.visibility"), value: displayValue(doc.visibility || metadataValue("visibility")) },
    { label: t("knowledge.drawer.mime"), value: displayValue(metadataValue("mime_type") || metadataValue("file_type")) },
  ]
})
</script>

<style scoped>
.knowledge-metadata-panel {
  min-width: 0;
}

.metadata-primary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}

.metadata-secondary {
  display: grid;
  gap: 8px;
}

.metadata-row {
  display: grid;
  grid-template-columns: minmax(72px, 0.32fr) minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  border: 1px solid var(--kn-border);
  border-radius: var(--ag-radius-control);
  background: var(--kn-panel-soft);
  padding: 9px 10px;
}

.metadata-row span,
.metadata-row strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metadata-row span {
  color: var(--kn-muted);
  font-size: 11px;
  font-weight: 760;
}

.metadata-row strong {
  color: var(--kn-heading);
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 12px;
  font-weight: 760;
}

</style>
