import type { KnowledgeDocument, KnowledgeIngestOptions, KnowledgeStatus } from "../types"

const metadataValue = (doc: KnowledgeDocument, ...keys: string[]) => {
  for (const key of keys) {
    const value = doc.metadata?.[key]
    if (value) return value
  }
  return ""
}

export const createDefaultKnowledgeIngestOptions = (
  status?: Pick<KnowledgeStatus, "chunk_size" | "chunk_overlap" | "code_chunk_size" | "semantic_threshold"> | null,
): KnowledgeIngestOptions => ({
  chunk_size: status?.chunk_size ?? null,
  chunk_overlap: status?.chunk_overlap ?? null,
  code_chunk_size: status?.code_chunk_size ?? null,
  semantic_threshold: status?.semantic_threshold ?? null,
  reader_strategy: "auto",
})

export const resolveSelectedKnowledgeDocumentId = (
  documents: KnowledgeDocument[],
  selectedId: string | null,
) => {
  if (selectedId && documents.some((doc) => doc.id === selectedId)) return selectedId
  return documents[0]?.id || ""
}

export const mergeUpdatedKnowledgeDocument = (
  documents: KnowledgeDocument[],
  oldId: string | null,
  updated: KnowledgeDocument,
) => {
  const withoutOld = documents.filter((doc) => doc.id !== oldId && doc.id !== updated.id)
  return [updated, ...withoutOld]
}

export const knowledgeDocumentType = (doc: KnowledgeDocument) => {
  const metaType = String(doc.type || metadataValue(doc, "file_type", "mime_type") || "")
  if (metaType) return metaType.replace(/^\./, "").toUpperCase()
  const text = `${doc.title} ${doc.source} ${metadataValue(doc, "file_name")}`
  const suffix = text.match(/\.([a-z0-9]+)(?:\s|$)/i)?.[1]
  return (suffix || "TEXT").toUpperCase()
}

export const knowledgeDocumentSize = (doc: KnowledgeDocument) => {
  const size = Number(doc.size ?? metadataValue(doc, "file_size"))
  if (!Number.isFinite(size) || size <= 0) return "-"
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

export const knowledgeDocumentStatus = (doc: KnowledgeDocument) => {
  const raw = String(doc.status || metadataValue(doc, "status", "embedding_status")).toLowerCase()
  if (raw.includes("fail") || raw.includes("error")) {
    return { labelKey: "knowledge.status.failed", value: "failed" as const, tone: "failed" }
  }
  if (["completed", "complete", "ready", "done", "success", "succeeded"].some((item) => raw.includes(item))) {
    return { labelKey: "knowledge.status.ready", value: "ready" as const, tone: "ready" }
  }
  if (Number(doc.chunks || 0) > 0) {
    return { labelKey: "knowledge.status.ready", value: "ready" as const, tone: "ready" }
  }
  return { labelKey: "knowledge.status.parsing", value: "parsing" as const, tone: "parsing" }
}
