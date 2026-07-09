import assert from "node:assert/strict"
import {
  createDefaultKnowledgeIngestOptions,
  knowledgeDocumentStatus,
  knowledgeDocumentType,
  mergeUpdatedKnowledgeDocument,
  resolveSelectedKnowledgeDocumentId,
} from "./knowledgeWorkbench.ts"

const docs = [
  { id: "doc-a", title: "a.md", source: "upload:a.md", chunks: 2, created_at: "", metadata: { file_type: ".md" } },
  { id: "doc-b", title: "b.csv", source: "upload:b.csv", chunks: 0, created_at: "", metadata: { file_name: "b.csv" } },
]

assert.equal(
  resolveSelectedKnowledgeDocumentId(docs, null),
  "doc-a",
  "selection should default to first document",
)

assert.equal(
  resolveSelectedKnowledgeDocumentId(docs, "doc-b"),
  "doc-b",
  "selection should keep an existing selected document",
)

assert.equal(
  resolveSelectedKnowledgeDocumentId([docs[0]], "doc-b"),
  "doc-a",
  "selection should recover when filtering hides the selected document",
)

assert.deepEqual(
  mergeUpdatedKnowledgeDocument(docs, "doc-a", { ...docs[0], id: "doc-new", title: "new.js" }).map((doc) => doc.id),
  ["doc-new", "doc-b"],
  "updated documents should replace old id and select returned id",
)

assert.equal(
  knowledgeDocumentType({ ...docs[1], type: "" }),
  "CSV",
  "document type should fall back to file metadata",
)

assert.deepEqual(
  knowledgeDocumentStatus({ ...docs[0], status: "completed" }),
  { labelKey: "knowledge.status.ready", value: "ready", tone: "ready" },
  "completed documents should display as ready",
)

assert.deepEqual(
  createDefaultKnowledgeIngestOptions({
    chunk_size: 1200,
    chunk_overlap: 160,
    code_chunk_size: 1800,
    semantic_threshold: 0.52,
  }),
  {
    chunk_size: 1200,
    chunk_overlap: 160,
    code_chunk_size: 1800,
    semantic_threshold: 0.52,
    reader_strategy: "auto",
  },
  "default ingest options should mirror status defaults",
)
