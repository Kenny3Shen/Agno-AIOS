import assert from "node:assert/strict"
import {
  knowledge,
  knowledgeIngestDrawer,
  useKnowledgeApiSource,
} from "./testSource.mjs"

assert.match(
  useKnowledgeApiSource,
  /const updateKnowledgeDocumentMetadata = \(docId: string, payload: KnowledgeDocumentUpdateRequest\) => request<KnowledgeDocument>\(`\/documents\/\$\{encodeURIComponent\(docId\)\}`,\s*\{\s*method: 'PATCH'/,
  "Knowledge API must expose a PATCH metadata update request for existing documents",
)

assert.match(
  knowledgeIngestDrawer,
  /"submit-update-metadata": \[payload: UpdateMetadataPayload\]/,
  "Knowledge Drawer must expose a metadata-only update submission event",
)

assert.match(
  knowledgeIngestDrawer,
  /if \(props\.mode === "update"\) return Boolean\(props\.targetDocument && \(selectedFile\.value \|\| hasMetadataChanges\.value\)\)/,
  "Knowledge Drawer update mode must allow submitting metadata-only changes without selecting a new file",
)

assert.match(
  knowledgeIngestDrawer,
  /emit\("submit-update-metadata", \{/,
  "Knowledge Drawer must branch metadata-only updates away from file replacement",
)

assert.match(
  knowledgeIngestDrawer,
  /emit\("submit-update-file", \{[\s\S]*?visibility: visibility\.value,/,
  "Knowledge Drawer must preserve visibility changes when replacing a file",
)

assert.match(
  knowledge,
  /updateKnowledgeDocumentMetadata/,
  "Knowledge page must call the metadata PATCH API for source-only updates",
)

assert.match(
  knowledge,
  /const submitDrawerUpdateMetadata = async \(payload: DrawerUpdateMetadataPayload\) =>/,
  "Knowledge page must own a dedicated metadata-only update handler",
)

assert.match(
  knowledge,
  /replaceKnowledgeDocumentSource\(doc\.id, \{[\s\S]*?visibility: payload\.visibility,/,
  "Knowledge page must send replacement visibility to the backend",
)
