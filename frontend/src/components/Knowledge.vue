<template>
  <div class="knowledge-console knowledge-workflow-shell ag-page-flow">
    <div class="knowledge-workspace-grid">
      <section class="knowledge-panel ag-content-panel knowledge-upload-panel">
        <div class="knowledge-section-head">
          <h4>{{ t('knowledge.upload.title') }}</h4>
          <span class="status-badge" :class="ingestTask.status">{{ ingestStatusLabel }}</span>
        </div>

        <div
          v-if="ingestTask.status === 'running' || ingestTask.status === 'error'"
          class="knowledge-upload-pipeline"
          :aria-label="t('knowledge.labels.pipelineAria')"
        >
          <div
            v-for="step in ingestSteps"
            :key="step.key"
            class="pipeline-step"
            :class="{ active: step.active, done: step.done, failed: step.failed }"
          >
            <span>{{ step.label }}</span>
          </div>
        </div>

        <div v-if="ingestTask.message && ingestTask.status !== 'idle'" class="task-feedback" :class="ingestTask.status">
          <span>{{ ingestTask.message }}</span>
          <el-button v-if="ingestTask.status === 'error'" size="small" text class="cursor-pointer" @click="retryIngestTask">
            {{ t('knowledge.actions.retry') }}
          </el-button>
        </div>

        <el-tabs v-model="activeIngestTab" class="knowledge-tabs">
          <el-tab-pane :label="t('knowledge.upload.fileTab')" name="upload">
            <div class="upload-mode-grid">
              <el-upload
                ref="browserUploadRef"
                v-model:file-list="browserFileList"
                drag
                :auto-upload="false"
                :limit="1"
                :accept="browserAccept"
                class="knowledge-upload"
                :on-change="handleBrowserFileChange"
                :on-remove="handleBrowserFileRemove"
                :on-exceed="handleBrowserFileExceed"
              >
                <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
                <div class="el-upload__text">
                  {{ t('knowledge.upload.dropText') }} <em>{{ t('knowledge.upload.chooseFile') }}</em>
                </div>
                <template #tip>
                  <div class="el-upload__tip">{{ t('knowledge.upload.supportedTypes') }}</div>
                </template>
              </el-upload>

              <div class="upload-side-form">
                <label class="knowledge-field">
                  <span>{{ t('knowledge.upload.titleLabel') }}</span>
                  <el-input v-model="browserForm.title" :placeholder="t('knowledge.upload.titlePlaceholder')" clearable />
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.upload.sourceLabel') }}</span>
                  <el-input v-model="browserForm.source" placeholder="upload" clearable />
                </label>
                <label class="knowledge-field">
                  <span>{{ t('visibility.label') }}</span>
                  <ResourceVisibilityTabs v-model="browserForm.visibility" />
                </label>
                <div class="reader-auto-note">
                  <strong>{{ t('knowledge.labels.reader') }}</strong>
                  <span>{{ detectedReaderLabel }}</span>
                </div>
                <el-button
                  type="primary"
                  class="!w-full cursor-pointer"
                  :disabled="!canSubmitBrowserUpload"
                  :loading="uploadingBrowserFile"
                  @click="submitBrowserUpload"
                >
                  <el-icon class="mr-1"><DocumentAdd /></el-icon>
                  {{ t('knowledge.actions.writeSelectedFile') }}
                </el-button>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane :label="t('knowledge.upload.textTab')" name="text">
            <div class="text-import-grid">
              <label class="knowledge-field">
                <span>{{ t('knowledge.upload.titleLabel') }}</span>
                <el-input v-model="textForm.title" :placeholder="t('knowledge.upload.textTitlePlaceholder')" clearable />
              </label>
              <label class="knowledge-field">
                <span>{{ t('knowledge.upload.sourceLabel') }}</span>
                <el-input v-model="textForm.source" :placeholder="t('knowledge.upload.sourceManualPlaceholder')" clearable />
              </label>
              <label class="knowledge-field">
                <span>{{ t('visibility.label') }}</span>
                <ResourceVisibilityTabs v-model="textForm.visibility" />
              </label>
              <label class="knowledge-field text-import-content">
                <span>{{ t('knowledge.upload.contentLabel') }}</span>
                <el-input
                  v-model="textForm.content"
                  type="textarea"
                  :rows="8"
                  :placeholder="t('knowledge.upload.contentPlaceholder')"
                />
              </label>
              <div class="form-action-row">
                <el-button
                  type="primary"
                  class="cursor-pointer"
                  :disabled="!canSubmitTextDocument"
                  :loading="savingText"
                  @click="submitTextDocument"
                >
                  <el-icon class="mr-1"><DocumentAdd /></el-icon>
                  {{ t('knowledge.actions.writeText') }}
                </el-button>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane :label="t('knowledge.upload.pathTab')" name="path">
            <div class="path-import-grid">
              <label class="knowledge-field">
                <span>{{ t('knowledge.upload.pathLabel') }}</span>
                <el-input v-model="pathForm.path" placeholder="/abs/path/report.md" clearable />
              </label>
              <label class="knowledge-field">
                <span>{{ t('knowledge.upload.titleLabel') }}</span>
                <el-input v-model="pathForm.title" :placeholder="t('knowledge.upload.optionalPlaceholder')" clearable />
              </label>
              <label class="knowledge-field">
                <span>{{ t('visibility.label') }}</span>
                <ResourceVisibilityTabs v-model="pathForm.visibility" />
              </label>
              <div class="form-action-row path-action">
                <el-button
                  type="primary"
                  class="cursor-pointer"
                  :disabled="!canSubmitPathDocument"
                  :loading="savingPath"
                  @click="submitPathDocument"
                >
                  <el-icon class="mr-1"><FolderOpened /></el-icon>
                  {{ t('knowledge.actions.importPath') }}
                </el-button>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </section>

      <section class="knowledge-panel ag-content-panel retrieval-playground">
        <div class="knowledge-section-head">
          <h4>{{ t('knowledge.retrieval.title') }}</h4>
          <span class="status-badge embedding">{{ searchForm.searchType }}</span>
        </div>

        <div class="playground-question">
          <el-input
            v-model="searchForm.query"
            type="textarea"
            :rows="4"
            :placeholder="t('knowledge.retrieval.queryPlaceholder')"
          />
          <div class="playground-controls">
            <label class="knowledge-field">
              <span>{{ t('knowledge.labels.searchType') }}</span>
              <el-select v-model="searchForm.searchType" size="small">
                <el-option :label="t('knowledge.labels.hybrid')" value="hybrid" />
                <el-option :label="t('knowledge.labels.vector')" value="vector" />
                <el-option :label="t('knowledge.labels.keyword')" value="keyword" />
              </el-select>
            </label>
            <label class="knowledge-field">
              <span>{{ t('knowledge.labels.topK') }}</span>
              <el-input-number v-model="searchForm.limit" :min="1" :max="20" size="small" class="!w-full" />
            </label>
            <el-button
              type="primary"
              class="cursor-pointer"
              :disabled="searching"
              :loading="searching"
              @click="runSearch"
            >
              {{ t('knowledge.actions.search') }}
            </el-button>
          </div>
        </div>

        <div class="playground-results">
          <div class="result-head">
            <strong>{{ t('knowledge.retrieval.resultTitle') }}</strong>
            <span>{{ t('knowledge.retrieval.resultCount', { count: searchResults.length }) }}</span>
          </div>

          <div v-if="searching" class="empty-box">
            <el-icon class="is-loading mr-1"><Loading /></el-icon>
            {{ t('knowledge.retrieval.searching') }}
          </div>
          <div v-else-if="searched && searchResults.length === 0" class="empty-box">{{ t('knowledge.retrieval.noResults') }}</div>
          <div v-else-if="!searched" class="empty-box">{{ t('knowledge.retrieval.idle') }}</div>

          <article
            v-for="result in searchResults"
            :key="`${result.doc_id}:${result.chunk_index}`"
            class="retrieval-hit"
          >
            <div class="hit-toolbar">
              <strong class="truncate">{{ result.title || result.doc_id || t('knowledge.labels.untitledChunk') }}</strong>
              <span class="score-badge">{{ formatScore(result.score) }}</span>
            </div>
            <p>{{ result.content }}</p>
            <div class="hit-meta">
              <span>{{ t('knowledge.labels.chunkIndex', { index: result.chunk_index }) }}</span>
              <span :title="result.source">{{ t('knowledge.labels.sourceValue', { value: result.source || '-' }) }}</span>
              <span :title="result.doc_id">{{ t('knowledge.labels.docValue', { value: shortId(result.doc_id) }) }}</span>
            </div>
          </article>

          <div v-if="searchResults.length" class="answer-preview">
            <span>{{ t('knowledge.retrieval.answer') }}</span>
            <p>{{ retrievalAnswer }}</p>
            <em>{{ t('knowledge.retrieval.reference', { value: retrievalReferences }) }}</em>
          </div>
        </div>
      </section>
    </div>

    <section class="knowledge-panel ag-content-panel knowledge-documents-section">
      <div class="document-management-bar">
        <div class="document-management-title">
          <h4>{{ t('knowledge.documents.title') }}</h4>
          <span>{{ t('knowledge.documents.visibleCount', { count: filteredDocuments.length, total: documents.length }) }}</span>
        </div>
        <div class="document-management-controls">
          <div class="document-command-group">
            <el-tooltip :content="t('shell.actions.refresh')" placement="top">
              <el-button class="cursor-pointer" size="small" :loading="loading" @click="loadKnowledge">
                <el-icon><Refresh /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip :content="t('knowledge.actions.clear')" placement="top">
              <el-button
                type="danger"
                plain
                size="small"
                class="cursor-pointer"
                :disabled="documents.length === 0"
                :loading="clearing"
                @click="clearAllDocuments"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </el-tooltip>
          </div>
          <el-input v-model="documentQuery" class="document-filter" :placeholder="t('knowledge.documents.searchPlaceholder')" clearable>
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <div class="document-filter-group">
            <el-select v-model="documentTypeFilter" size="small" class="document-select" :placeholder="t('knowledge.documents.typePlaceholder')">
              <el-option :label="t('knowledge.documents.allTypes')" value="all" />
              <el-option v-for="type in documentTypes" :key="type" :label="type" :value="type" />
            </el-select>
            <el-select v-model="documentStatusFilter" size="small" class="document-select" :placeholder="t('knowledge.documents.statusPlaceholder')">
              <el-option :label="t('knowledge.documents.allStatus')" value="all" />
              <el-option :label="t('knowledge.status.ready')" value="ready" />
              <el-option :label="t('knowledge.status.parsing')" value="parsing" />
              <el-option :label="t('knowledge.status.failed')" value="failed" />
            </el-select>
          </div>
        </div>
      </div>

      <div v-if="loading && documents.length === 0" class="document-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        {{ t('knowledge.documents.loading') }}
      </div>

      <div v-else class="document-table" role="table" :aria-label="t('knowledge.documents.ariaLabel')">
        <div class="document-table-head" role="row">
          <span role="columnheader">{{ t('knowledge.documents.columns.name') }}</span>
          <span role="columnheader">{{ t('knowledge.documents.columns.type') }}</span>
          <span role="columnheader">{{ t('knowledge.documents.columns.size') }}</span>
          <span role="columnheader">{{ t('knowledge.documents.columns.chunks') }}</span>
          <span role="columnheader">{{ t('knowledge.documents.columns.embeddingStatus') }}</span>
          <span role="columnheader">{{ t('knowledge.documents.columns.updatedTime') }}</span>
          <span role="columnheader">{{ t('knowledge.documents.columns.source') }}</span>
          <span role="columnheader">{{ t('knowledge.documents.columns.visibility') }}</span>
          <span role="columnheader">{{ t('knowledge.documents.columns.actions') }}</span>
        </div>

        <div v-if="filteredDocuments.length === 0" class="empty-box">{{ t('knowledge.documents.empty') }}</div>

        <article v-for="row in filteredDocuments" :key="row.id" class="document-row" role="row">
          <div class="document-cell document-main" role="cell">
            <div class="document-primary">
              <span class="doc-title" :title="row.title">{{ row.title }}</span>
            </div>
          </div>
          <div class="document-cell" role="cell" :data-label="t('knowledge.documents.columns.type')">
            <span class="type-badge">{{ documentType(row) }}</span>
          </div>
          <div class="document-cell document-number" role="cell" :data-label="t('knowledge.documents.columns.size')">{{ documentSize(row) }}</div>
          <div class="document-cell document-number" role="cell" :data-label="t('knowledge.documents.columns.chunks')">{{ row.chunks }}</div>
          <div class="document-cell" role="cell" :data-label="t('knowledge.documents.columns.embeddingStatus')">
            <span class="status-badge" :class="documentStatus(row).tone">{{ documentStatus(row).label }}</span>
          </div>
          <div class="document-cell document-time" role="cell" :data-label="t('knowledge.documents.columns.updatedTime')">
            <span class="document-time-value">{{ formatDate(row.created_at) }}</span>
          </div>
          <div class="document-cell" role="cell" :data-label="t('knowledge.documents.columns.source')">
            <span class="source-text" :title="row.source">{{ row.source || t('knowledge.labels.manualSource') }}</span>
          </div>
          <div class="document-cell document-visibility-cell" role="cell" :data-label="t('knowledge.documents.columns.visibility')">
            <ResourceVisibilityTabs
              :model-value="row.visibility || 'private'"
              class="document-visibility-tabs"
              :disabled="!row.can_manage"
              :aria-label="t('knowledge.documents.visibilityLabel', { title: row.title })"
              @update:model-value="(value) => updateDocumentVisibility(row, value)"
            />
          </div>
          <div class="document-actions" role="cell" :data-label="t('knowledge.documents.columns.actions')">
            <div class="document-action-buttons">
              <el-tooltip :content="t('knowledge.documents.preview')" placement="top">
                <el-button text class="cursor-pointer" :aria-label="t('knowledge.documents.previewLabel', { title: row.title })" @click="openPreview(row)">
                  <el-icon><View /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip :content="t('knowledge.documents.rebuild')" placement="top">
                <el-button
                  text
                  class="cursor-pointer"
                  :disabled="!row.can_manage || rebuildingDocId === row.id"
                  :loading="rebuildingDocId === row.id"
                  :aria-label="t('knowledge.documents.reEmbeddingLabel', { title: row.title })"
                  @click="rebuildDocument(row)"
                >
                  <el-icon><RefreshRight /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip :content="t('knowledge.documents.replaceSource')" placement="top">
                <el-button
                  text
                  class="cursor-pointer"
                  :disabled="!row.can_manage || replacingSourceDocId === row.id"
                  :loading="replacingSourceDocId === row.id"
                  :aria-label="t('knowledge.documents.replaceSourceLabel', { title: row.title })"
                  @click="openSourceReplacement(row)"
                >
                  <el-icon><UploadFilled /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip :content="t('knowledge.documents.metadata')" placement="top">
                <el-button text class="cursor-pointer" :aria-label="t('knowledge.documents.metadataLabel', { title: row.title })" @click="openMetadata(row)">
                  <el-icon><Tickets /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip :content="t('knowledge.documents.delete')" placement="top">
                <el-button
                  type="danger"
                  text
                  class="cursor-pointer"
                  :loading="deletingDocId === row.id"
                  :aria-label="t('knowledge.documents.deleteLabel', { title: row.title })"
                  @click="deleteDocument(row)"
                >
                  <el-icon><Delete /></el-icon>
                </el-button>
              </el-tooltip>
            </div>
          </div>
        </article>
      </div>
    </section>

    <section class="knowledge-panel ag-content-panel advanced-configuration">
      <el-collapse v-model="advancedSections">
        <el-collapse-item name="advanced">
          <template #title>
            <div class="advanced-title">
              <el-icon><Setting /></el-icon>
              <span>{{ t('knowledge.advanced.title') }}</span>
              <em>{{ t('knowledge.advanced.description') }}</em>
            </div>
          </template>

          <div class="advanced-grid">
            <section class="advanced-card">
              <div class="panel-title">
                <el-icon><Document /></el-icon>
                {{ t('knowledge.advanced.readerChunkStrategy') }}
              </div>
              <div class="reader-strategy-console">
                <div class="reader-auto-note roomy">
                  <strong>{{ t('knowledge.labels.reader') }}</strong>
                  <span>{{ t('knowledge.advanced.readerAuto') }}</span>
                </div>
                <article v-for="profile in chunkProfiles" :key="profile.strategy" class="strategy-row">
                  <div class="strategy-name">
                    <strong>{{ profile.label }}</strong>
                    <span>{{ profile.strategy }}</span>
                  </div>
                  <span class="strategy-reader">{{ profile.reader }}</span>
                  <p>{{ profile.description }}</p>
                  <em>{{ profile.suffixes.join(" ") }}</em>
                </article>
              </div>
            </section>

            <section class="advanced-card">
              <div class="panel-title panel-title-actions">
                <span>
                  <el-icon><Operation /></el-icon>
                  {{ t('knowledge.advanced.ragParameters') }}
                </span>
                <span class="panel-button-row">
                  <el-button size="small" class="cursor-pointer" :disabled="!ragSettingsDirty || ragSaving" @click="resetRagSettings">
                    <el-icon><RefreshLeft /></el-icon>
                    {{ t('knowledge.actions.reset') }}
                  </el-button>
                  <el-button
                    type="primary"
                    size="small"
                    class="cursor-pointer"
                    :disabled="ragSaveDisabled"
                    :loading="ragSaving"
                    :title="canWriteRagSettings ? undefined : t('knowledge.messages.configPermissionRequired')"
                    @click="saveRagSettings"
                  >
                    <el-icon><Check /></el-icon>
                    {{ t('knowledge.actions.save') }}
                  </el-button>
                </span>
              </div>
              <div class="rag-settings-grid">
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.searchType') }}</span>
                  <el-select v-model="ragSettings.searchType">
                    <el-option :label="t('knowledge.labels.hybrid')" value="hybrid" />
                    <el-option :label="t('knowledge.labels.vector')" value="vector" />
                    <el-option :label="t('knowledge.labels.keyword')" value="keyword" />
                  </el-select>
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.embeddingModel') }}</span>
                  <el-input v-model="ragSettings.embeddingModel" clearable />
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.embeddingDimensions') }}</span>
                  <el-input-number v-model="ragSettings.embeddingDimensions" :min="1" :max="4096" class="!w-full" />
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.rerankModel') }}</span>
                  <el-input v-model="ragSettings.rerankModel" clearable :disabled="!ragSettings.reranker" />
                </label>
                <label class="knowledge-field rag-wide-field">
                  <span>{{ t('knowledge.labels.queryPrompt') }}</span>
                  <el-input v-model="ragSettings.queryPrompt" type="textarea" :rows="2" />
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.topK') }}</span>
                  <el-input-number v-model="ragSettings.topK" :min="1" :max="20" class="!w-full" />
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.candidateMultiplier') }}</span>
                  <el-input-number v-model="ragSettings.candidateMultiplier" :min="1" :max="10" class="!w-full" />
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.minCandidates') }}</span>
                  <el-input-number v-model="ragSettings.minCandidates" :min="1" :max="100" class="!w-full" />
                </label>
                <div class="rag-static-metric">
                  <span>{{ t('knowledge.labels.effectiveCandidates') }}</span>
                  <strong>{{ effectiveCandidates }}</strong>
                </div>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.contentLanguage') }}</span>
                  <el-input v-model="ragSettings.contentLanguage" clearable />
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.chunkSize') }}</span>
                  <el-input-number v-model="ragSettings.chunkSize" :min="200" :max="4000" :step="100" class="!w-full" />
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.overlap') }}</span>
                  <el-input-number v-model="ragSettings.chunkOverlap" :min="0" :max="800" :step="20" class="!w-full" />
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.codeChunkSize') }}</span>
                  <el-input-number v-model="ragSettings.codeChunkSize" :min="256" :max="6000" :step="100" class="!w-full" />
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.threshold') }}</span>
                  <el-slider v-model="ragSettings.semanticThreshold" :min="0" :max="1" :step="0.01" />
                </label>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.vectorWeight') }}</span>
                  <el-slider v-model="ragSettings.vectorWeight" :min="0" :max="1" :step="0.05" />
                </label>
                <div class="rag-static-metric">
                  <span>{{ t('knowledge.labels.bm25Weight') }}</span>
                  <strong>{{ ragBm25Weight.toFixed(2) }}</strong>
                </div>
                <div class="toggle-row">
                  <span>{{ t('knowledge.labels.prefixMatch') }}</span>
                  <el-switch v-model="ragSettings.prefixMatch" />
                </div>
                <div class="toggle-row">
                  <span>{{ t('knowledge.labels.reranker') }}</span>
                  <el-switch v-model="ragSettings.reranker" />
                </div>
                <label class="knowledge-field">
                  <span>{{ t('knowledge.labels.device') }}</span>
                  <el-input v-model="ragSettings.device" clearable />
                </label>
              </div>
            </section>

            <section class="advanced-card">
              <div class="panel-title">
                <el-icon><InfoFilled /></el-icon>
                {{ t('knowledge.advanced.parserOcrMetadata') }}
              </div>
              <div class="knowledge-runtime-summary metadata-summary" :aria-label="t('knowledge.stats.ariaLabel')">
                <div v-for="card in statisticsCards" :key="card.label" class="knowledge-runtime-chip">
                  <span>{{ card.label }}</span>
                  <strong :title="card.value">{{ card.value }}</strong>
                </div>
              </div>
              <div class="advanced-info-list">
                <div class="context-row">
                  <dt>{{ t('knowledge.advanced.parser') }}</dt>
                  <dd>{{ t('knowledge.advanced.autoByReader') }}</dd>
                </div>
                <div class="context-row">
                  <dt>{{ t('knowledge.advanced.ocr') }}</dt>
                  <dd>{{ t('knowledge.advanced.notEnabled') }}</dd>
                </div>
                <div class="context-row">
                  <dt>{{ t('knowledge.advanced.metadata') }}</dt>
                  <dd>source, file_name, file_size, file_type</dd>
                </div>
              </div>
            </section>

            <section class="advanced-card">
              <div class="panel-title">
                <el-icon><DataLine /></el-icon>
                {{ t('knowledge.advanced.advancedInformation') }}
              </div>
              <dl class="advanced-info-list">
                <div v-for="row in advancedInfoRows" :key="row.label" class="context-row">
                  <dt>{{ row.label }}</dt>
                  <dd :title="row.value">{{ row.value }}</dd>
                </div>
              </dl>
            </section>
          </div>
        </el-collapse-item>
      </el-collapse>
    </section>

    <el-drawer
      v-model="previewDrawerOpen"
      class="document-preview-drawer"
      :title="t('knowledge.drawer.previewTitle')"
      direction="rtl"
      size="420px"
    >
      <template v-if="previewDocument">
        <div class="drawer-stack">
          <div>
            <span class="drawer-label">{{ t('knowledge.drawer.documentName') }}</span>
            <strong>{{ previewDocument.title }}</strong>
          </div>
          <div>
            <span class="drawer-label">{{ t('knowledge.drawer.source') }}</span>
            <p>{{ previewDocument.source || t('knowledge.labels.manualSource') }}</p>
          </div>
          <div class="drawer-grid">
            <div>
              <span class="drawer-label">{{ t('knowledge.drawer.type') }}</span>
              <strong>{{ documentType(previewDocument) }}</strong>
            </div>
            <div>
              <span class="drawer-label">{{ t('knowledge.drawer.chunks') }}</span>
              <strong>{{ previewDocument.chunks }}</strong>
            </div>
            <div>
              <span class="drawer-label">{{ t('knowledge.drawer.size') }}</span>
              <strong>{{ documentSize(previewDocument) }}</strong>
            </div>
            <div>
              <span class="drawer-label">{{ t('knowledge.drawer.updated') }}</span>
              <strong>{{ formatDate(previewDocument.created_at) }}</strong>
            </div>
          </div>
          <div>
            <span class="drawer-label">{{ t('knowledge.drawer.reference') }}</span>
            <pre class="metadata-json">{{ prettyJson(previewDocument) }}</pre>
          </div>
        </div>
      </template>
    </el-drawer>

    <el-dialog v-model="metadataDialogOpen" :title="t('knowledge.drawer.metadataTitle')" width="560px">
      <pre class="metadata-json">{{ prettyJson(metadataDocument?.metadata || {}) }}</pre>
    </el-dialog>

    <el-dialog
      v-model="sourceReplacementDialogOpen"
      class="source-replacement-dialog"
      :title="t('knowledge.documents.replaceSource')"
      width="min(560px, calc(100vw - 24px))"
      @closed="resetSourceReplacement"
    >
      <template v-if="sourceReplacementDocument">
        <div class="source-replacement-form">
          <div class="source-replacement-target">
            <span>{{ t('knowledge.documents.currentSource') }}</span>
            <strong>{{ sourceReplacementDocument.title }}</strong>
            <em :title="sourceReplacementDocument.source">{{ sourceReplacementDocument.source || t('knowledge.labels.manualSource') }}</em>
          </div>
          <el-upload
            ref="sourceReplacementUploadRef"
            v-model:file-list="sourceReplacementFileList"
            drag
            :auto-upload="false"
            :limit="1"
            :accept="browserAccept"
            class="source-replacement-upload"
            :on-change="handleSourceReplacementFileChange"
            :on-remove="handleSourceReplacementFileRemove"
            :on-exceed="handleSourceReplacementFileExceed"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">
              {{ t('knowledge.upload.dropText') }} <em>{{ t('knowledge.upload.chooseFile') }}</em>
            </div>
            <template #tip>
              <div class="el-upload__tip">{{ t('knowledge.upload.supportedTypes') }}</div>
            </template>
          </el-upload>
          <label class="knowledge-field">
            <span>{{ t('knowledge.upload.sourceLabel') }}</span>
            <el-input v-model="sourceReplacementForm.source" :placeholder="sourceReplacementSourcePlaceholder" clearable />
          </label>
        </div>
      </template>
      <template #footer>
        <span class="source-replacement-footer">
          <el-button class="cursor-pointer" @click="sourceReplacementDialogOpen = false">{{ t('knowledge.actions.cancel') }}</el-button>
          <el-button
            type="primary"
            class="cursor-pointer"
            :disabled="!canSubmitSourceReplacement"
            :loading="replacingSourceDocId === sourceReplacementDocument?.id"
            @click="submitSourceReplacement"
          >
            <el-icon><UploadFilled /></el-icon>
            {{ t('knowledge.actions.replaceSource') }}
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue"
import { useI18n } from "vue-i18n"
import { ElMessage, ElMessageBox } from "element-plus"
import type { UploadFile, UploadFiles, UploadInstance, UploadUserFile } from "element-plus"
import {
  Check,
  DataLine,
  Delete,
  Document,
  DocumentAdd,
  FolderOpened,
  InfoFilled,
  Loading,
  Operation,
  Refresh,
  RefreshLeft,
  RefreshRight,
  Search,
  Setting,
  Tickets,
  UploadFilled,
  View,
} from "@element-plus/icons-vue"
import { useKnowledgeApi } from "../composables/useApi"
import { useAuthStore } from "../stores/auth"
import type { KnowledgeDocument, KnowledgeRagSettings, KnowledgeSearchResult, KnowledgeStatus, ResourceVisibility } from "../types"
import ResourceVisibilityTabs from "./common/ResourceVisibilityTabs.vue"

type IngestTab = "upload" | "text" | "path"
type IngestStage = "uploading" | "parsing" | "chunking" | "embedding" | "completed"
type IngestStatus = "idle" | "running" | "success" | "error"

const { t, locale } = useI18n()
const authStore = useAuthStore()

const activeIngestTab = ref<IngestTab>("upload")
const status = ref<KnowledgeStatus | null>(null)
const documents = ref<KnowledgeDocument[]>([])
const documentQuery = ref("")
const documentTypeFilter = ref("all")
const documentStatusFilter = ref("all")
const browserUploadRef = ref<UploadInstance>()
const browserFileList = ref<UploadUserFile[]>([])
const selectedBrowserFile = ref<File | null>(null)
const savingText = ref(false)
const savingPath = ref(false)
const uploadingBrowserFile = ref(false)
const deletingDocId = ref<string | null>(null)
const rebuildingDocId = ref<string | null>(null)
const clearing = ref(false)
const searching = ref(false)
const ragSaving = ref(false)
const searched = ref(false)
const searchResults = ref<KnowledgeSearchResult[]>([])
const advancedSections = ref<string[]>([])
const previewDrawerOpen = ref(false)
const metadataDialogOpen = ref(false)
const sourceReplacementDialogOpen = ref(false)
const previewDocument = ref<KnowledgeDocument | null>(null)
const metadataDocument = ref<KnowledgeDocument | null>(null)
const sourceReplacementDocument = ref<KnowledgeDocument | null>(null)
const sourceReplacementUploadRef = ref<UploadInstance>()
const sourceReplacementFileList = ref<UploadUserFile[]>([])
const selectedSourceReplacementFile = ref<File | null>(null)
const replacingSourceDocId = ref<string | null>(null)
const lastIngestRetry = ref<null | (() => Promise<void>)>(null)

const ingestTask = reactive<{
  status: IngestStatus
  stage: IngestStage
  message: string
}>({
  status: "idle",
  stage: "uploading",
  message: t("knowledge.upload.waiting"),
})

const browserForm = reactive({
  title: "",
  source: "upload",
  visibility: "private" as ResourceVisibility,
})

const textForm = reactive({
  title: "",
  source: "manual",
  content: "",
  visibility: "private" as ResourceVisibility,
})

const pathForm = reactive({
  path: "",
  title: "",
  visibility: "private" as ResourceVisibility,
})

const sourceReplacementForm = reactive({
  source: "",
})

const searchForm = reactive({
  query: "",
  limit: 5,
  searchType: "hybrid",
})

const ragSettings = reactive({
  topK: 5,
  candidateMultiplier: 3,
  minCandidates: 10,
  chunkSize: 1200,
  chunkOverlap: 160,
  codeChunkSize: 1800,
  semanticThreshold: 0.52,
  vectorWeight: 0.55,
  embeddingModel: "BAAI/bge-small-zh-v1.5",
  embeddingDimensions: 512,
  rerankModel: "BAAI/bge-reranker-base",
  queryPrompt: "为这个句子生成表示以用于检索相关文章：",
  reranker: true,
  prefixMatch: false,
  contentLanguage: "english",
  device: "auto",
  searchType: "hybrid",
})
const ragSettingsSnapshot = ref("")

const {
  loading,
  fetchKnowledge,
  addTextDocument,
  addFileDocument,
  updateKnowledgeDocumentVisibility,
  rebuildKnowledgeDocument,
  replaceKnowledgeDocumentSource,
  updateKnowledgeRagSettings,
  deleteKnowledgeDocument,
  clearKnowledge,
  searchKnowledge,
} = useKnowledgeApi()

const totalChunks = computed(() => documents.value.reduce((sum, item) => sum + Number(item.chunks || 0), 0))

const statisticsCards = computed(() => [
  { label: t("knowledge.stats.documents"), value: String(status.value?.documents ?? documents.value.length), hint: t("knowledge.stats.documentsHint") },
  { label: t("knowledge.stats.chunks"), value: String(status.value?.chunks ?? totalChunks.value), hint: t("knowledge.stats.chunksHint") },
  { label: t("knowledge.stats.embeddingModel"), value: status.value?.embedding || "unknown", hint: status.value?.embedding_dimensions ? `${status.value.embedding_dimensions} dimensions` : t("knowledge.stats.modelRuntime") },
  { label: t("knowledge.stats.vectorDatabase"), value: status.value?.collection || "-", hint: status.value?.search_type || "hybrid" },
])

const ragBm25Weight = computed(() => Number((1 - Number(ragSettings.vectorWeight || 0)).toFixed(2)))
const canWriteRagSettings = computed(() => authStore.hasScope("config:write"))

const effectiveCandidates = computed(() => {
  if (!ragSettings.reranker) return ragSettings.topK
  return Math.max(ragSettings.topK * ragSettings.candidateMultiplier, ragSettings.minCandidates)
})

const ragPayload = (): KnowledgeRagSettings => ({
  embedding_model: ragSettings.embeddingModel.trim(),
  embedding_dimensions: ragSettings.embeddingDimensions,
  rerank_model: ragSettings.rerankModel.trim(),
  query_prompt: ragSettings.queryPrompt,
  top_k: ragSettings.topK,
  chunk_size: ragSettings.chunkSize,
  chunk_overlap: ragSettings.chunkOverlap,
  code_chunk_size: ragSettings.codeChunkSize,
  semantic_threshold: ragSettings.semanticThreshold,
  vector_score_weight: ragSettings.vectorWeight,
  content_language: ragSettings.contentLanguage.trim() || "english",
  prefix_match: ragSettings.prefixMatch,
  rerank_enabled: ragSettings.reranker,
  rerank_candidate_multiplier: ragSettings.candidateMultiplier,
  rerank_min_candidates: ragSettings.minCandidates,
  device: ragSettings.device.trim() || "auto",
  search_type: ragSettings.searchType,
})

const ragSettingsDirty = computed(() => JSON.stringify(ragPayload()) !== ragSettingsSnapshot.value)

const ragSaveDisabled = computed(() => {
  return !canWriteRagSettings.value || ragSaving.value || !ragSettingsDirty.value || !ragSettings.embeddingModel.trim() || !ragSettings.rerankModel.trim()
})

const ingestStatusLabel = computed(() => {
  if (ingestTask.status === "running") {
    return ingestPipeline.value.find((item) => item.key === ingestTask.stage)?.label ?? ingestTask.stage
  }
  if (ingestTask.status === "success") return t("knowledge.status.completed")
  if (ingestTask.status === "error") return t("knowledge.status.failed")
  return t("knowledge.status.ready")
})

const ingestPipeline = computed<Array<{ key: IngestStage; label: string }>>(() => [
  { key: "uploading", label: t("knowledge.status.uploading") },
  { key: "parsing", label: t("knowledge.status.parsing") },
  { key: "chunking", label: t("knowledge.status.chunking") },
  { key: "embedding", label: t("knowledge.status.embedding") },
  { key: "completed", label: t("knowledge.status.completed") },
])

const ingestSteps = computed(() => {
  const currentIndex = ingestPipeline.value.findIndex((item) => item.key === ingestTask.stage)
  return ingestPipeline.value.map((item, index) => ({
    ...item,
    active: ingestTask.status === "running" && item.key === ingestTask.stage,
    done: ingestTask.status === "success" || currentIndex > index && ingestTask.status !== "error",
    failed: ingestTask.status === "error" && item.key === ingestTask.stage,
  }))
})

const browserAccept = [
  ".md",
  ".markdown",
  ".txt",
  ".log",
  ".csv",
  ".tsv",
  ".json",
  ".jsonl",
  ".yaml",
  ".yml",
  ".toml",
  ".py",
  ".js",
  ".jsx",
  ".ts",
  ".tsx",
  ".vue",
  ".go",
  ".rs",
  ".java",
  ".sh",
  ".sql",
  "text/plain",
  "text/markdown",
  "application/json",
  "text/csv",
].join(",")
const browserTextPattern = /\.(md|markdown|txt|log|csv|tsv|json|jsonl|ya?ml|toml|py|js|jsx|ts|tsx|vue|go|rs|java|c|cc|cpp|h|hpp|cs|php|rb|sh|sql)$/i

const chunkProfiles = computed(() => status.value?.chunk_profiles || [
  {
    label: "Markdown",
    strategy: "markdown",
    reader: "MarkdownReader",
    suffixes: [".md", ".markdown"],
    description: t("knowledge.chunkProfiles.markdown"),
  },
  {
    label: "CSV Row",
    strategy: "csv_row",
    reader: "CSVReader",
    suffixes: [".csv", ".tsv"],
    description: t("knowledge.chunkProfiles.csv"),
  },
  {
    label: "Code",
    strategy: "code",
    reader: "TextReader",
    suffixes: [".py", ".ts", ".vue"],
    description: t("knowledge.chunkProfiles.code"),
  },
])

const detectedReaderLabel = computed(() => {
  const file = selectedBrowserFile.value
  if (!file) return t("knowledge.reader.autoOnUpload")
  const suffix = file.name.match(/\.[^.]+$/)?.[0]?.toLowerCase() || ""
  const profile = chunkProfiles.value.find((item) => item.suffixes.includes(suffix))
  return profile ? `${profile.reader} · ${profile.label}` : t("knowledge.reader.textAuto")
})

const documentTypes = computed(() => {
  return [...new Set(documents.value.map((doc) => documentType(doc)).filter(Boolean))].sort()
})

const filteredDocuments = computed(() => {
  const query = documentQuery.value.trim().toLowerCase()
  return documents.value.filter((item) => {
    const metadataText = Object.values(item.metadata || {}).join(" ")
    const matchesQuery = !query || [item.id, item.title, item.source, metadataText].some((text) => String(text || "").toLowerCase().includes(query))
    const matchesType = documentTypeFilter.value === "all" || documentType(item) === documentTypeFilter.value
    const matchesStatus = documentStatusFilter.value === "all" || documentStatus(item).value === documentStatusFilter.value
    return matchesQuery && matchesType && matchesStatus
  })
})

const advancedInfoRows = computed(() => [
  { label: t("knowledge.labels.schema"), value: status.value?.postgres_schema || "-" },
  { label: t("knowledge.labels.dimension"), value: valueOrDash(status.value?.embedding_dimensions) },
  { label: t("knowledge.labels.runtime"), value: status.value?.torch_runtime_ok === false ? t("knowledge.status.degraded") : t("knowledge.status.ready") },
  { label: t("knowledge.labels.candidates"), value: valueOrDash(status.value?.retrieval_candidates) },
  { label: t("knowledge.labels.suffix"), value: status.value?.supported_suffixes?.join(" ") || "-" },
  { label: t("knowledge.labels.device"), value: status.value?.device || "-" },
  { label: t("knowledge.labels.database"), value: status.value?.database || "-" },
  { label: t("knowledge.labels.contents"), value: status.value?.contents_db || "-" },
  { label: t("knowledge.labels.collection"), value: status.value?.collection || "-" },
])

const retrievalAnswer = computed(() => {
  if (!searchResults.value.length) return t("knowledge.retrieval.answerFallback")
  const first = searchResults.value[0]
  return first.content.length > 180 ? `${first.content.slice(0, 180)}...` : first.content
})

const retrievalReferences = computed(() => {
  if (!searchResults.value.length) return "-"
  return searchResults.value
    .slice(0, 3)
    .map((item) => item.title || item.source || shortId(item.doc_id))
    .join(" / ")
})

const syncRagSettingsFromStatus = (nextStatus: KnowledgeStatus) => {
  const next = nextStatus.rag_settings || {}
  ragSettings.embeddingModel = next.embedding_model || nextStatus.embedding || ragSettings.embeddingModel
  ragSettings.embeddingDimensions = next.embedding_dimensions || nextStatus.embedding_dimensions || ragSettings.embeddingDimensions
  ragSettings.rerankModel = next.rerank_model || nextStatus.rerank || ragSettings.rerankModel
  ragSettings.queryPrompt = next.query_prompt ?? ragSettings.queryPrompt
  ragSettings.topK = next.top_k || nextStatus.top_k || ragSettings.topK
  ragSettings.candidateMultiplier = next.rerank_candidate_multiplier || nextStatus.rerank_candidate_multiplier || ragSettings.candidateMultiplier
  ragSettings.minCandidates = next.rerank_min_candidates || nextStatus.rerank_min_candidates || ragSettings.minCandidates
  ragSettings.chunkSize = next.chunk_size || nextStatus.chunk_size || ragSettings.chunkSize
  if (typeof next.chunk_overlap === "number") {
    ragSettings.chunkOverlap = next.chunk_overlap
  } else if (typeof nextStatus.chunk_overlap === "number") {
    ragSettings.chunkOverlap = nextStatus.chunk_overlap
  }
  ragSettings.codeChunkSize = next.code_chunk_size || nextStatus.code_chunk_size || ragSettings.codeChunkSize
  if (typeof next.semantic_threshold === "number") {
    ragSettings.semanticThreshold = next.semantic_threshold
  } else if (typeof nextStatus.semantic_threshold === "number") {
    ragSettings.semanticThreshold = nextStatus.semantic_threshold
  }
  if (typeof next.vector_score_weight === "number") {
    ragSettings.vectorWeight = next.vector_score_weight
  } else if (typeof nextStatus.vector_score_weight === "number") {
    ragSettings.vectorWeight = nextStatus.vector_score_weight
  }
  ragSettings.contentLanguage = next.content_language || nextStatus.content_language || ragSettings.contentLanguage
  if (typeof next.prefix_match === "boolean") {
    ragSettings.prefixMatch = next.prefix_match
  } else if (typeof nextStatus.prefix_match === "boolean") {
    ragSettings.prefixMatch = nextStatus.prefix_match
  }
  if (typeof next.rerank_enabled === "boolean") {
    ragSettings.reranker = next.rerank_enabled
  } else {
    ragSettings.reranker = nextStatus.rerank_enabled
  }
  ragSettings.device = next.device || nextStatus.device || ragSettings.device
  ragSettings.searchType = next.search_type || nextStatus.search_type || ragSettings.searchType
  searchForm.searchType = ragSettings.searchType
  ragSettingsSnapshot.value = JSON.stringify(ragPayload())
}

const loadKnowledge = async () => {
  try {
    const data = await fetchKnowledge()
    status.value = data.status
    documents.value = data.documents
    syncRagSettingsFromStatus(data.status)
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("knowledge.messages.loadFailed"))
  }
}

const stripExtension = (name: string) => name.replace(/\.[^.]+$/i, "")

const isSupportedTextFile = (file: File) => {
  return browserTextPattern.test(file.name)
}

const canSubmitBrowserUpload = computed(() => {
  const file = selectedBrowserFile.value
  return Boolean(file && isSupportedTextFile(file) && !uploadingBrowserFile.value)
})
const canSubmitTextDocument = computed(() => Boolean(textForm.title.trim() && textForm.content.trim() && !savingText.value))
const canSubmitPathDocument = computed(() => Boolean(pathForm.path.trim() && !savingPath.value))
const canSubmitSourceReplacement = computed(() => {
  const doc = sourceReplacementDocument.value
  const file = selectedSourceReplacementFile.value
  return Boolean(doc?.can_manage && file && isSupportedTextFile(file) && replacingSourceDocId.value !== doc.id)
})

const sourceReplacementSourcePlaceholder = computed(() => {
  const doc = sourceReplacementDocument.value
  if (!doc) return "upload"
  const fileName = selectedSourceReplacementFile.value?.name || doc.metadata?.file_name || doc.title
  return `upload:${fileName}`
})

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
  ElMessage.warning(t("knowledge.messages.singleFileOnly"))
}

const handleSourceReplacementFileChange = (uploadFile: UploadFile, uploadFiles: UploadFiles) => {
  sourceReplacementFileList.value = uploadFiles.slice(-1)
  selectedSourceReplacementFile.value = uploadFile.raw ?? null
  if (uploadFile.name) {
    sourceReplacementForm.source = `upload:${uploadFile.name}`
  }
}

const handleSourceReplacementFileRemove = () => {
  selectedSourceReplacementFile.value = null
}

const handleSourceReplacementFileExceed = () => {
  ElMessage.warning(t("knowledge.messages.singleFileOnly"))
}

const resetBrowserUpload = () => {
  browserForm.title = ""
  browserForm.source = "upload"
  browserForm.visibility = "private"
  selectedBrowserFile.value = null
  browserFileList.value = []
  browserUploadRef.value?.clearFiles()
}

const resetSourceReplacement = () => {
  sourceReplacementDocument.value = null
  sourceReplacementForm.source = ""
  selectedSourceReplacementFile.value = null
  sourceReplacementFileList.value = []
  sourceReplacementUploadRef.value?.clearFiles()
}

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

const runIngestTask = async (title: string, task: () => Promise<void>, retry: () => Promise<void>) => {
  lastIngestRetry.value = retry
  ingestTask.status = "running"
  ingestTask.stage = "uploading"
  ingestTask.message = `${title}: ${t("knowledge.status.uploading")}`
  try {
    await wait(80)
    ingestTask.stage = "parsing"
    ingestTask.message = `${title}: ${t("knowledge.status.parsing")}`
    await task()
    await wait(80)
    ingestTask.stage = "chunking"
    ingestTask.message = `${title}: ${t("knowledge.status.chunking")}`
    await wait(80)
    ingestTask.stage = "embedding"
    ingestTask.message = `${title}: ${t("knowledge.status.embedding")}`
    await loadKnowledge()
    ingestTask.stage = "completed"
    ingestTask.status = "success"
    ingestTask.message = `${title}: ${t("knowledge.status.completed")}`
    ElMessage.success(t("knowledge.messages.updated"))
  } catch (err) {
    ingestTask.status = "error"
    ingestTask.message = err instanceof Error ? err.message : t("knowledge.messages.taskFailed", { title })
    ElMessage.error(ingestTask.message)
  }
}

const retryIngestTask = async () => {
  if (!lastIngestRetry.value) return
  await lastIngestRetry.value()
}

const submitBrowserUpload = async () => {
  const file = selectedBrowserFile.value
  if (!file) {
    ElMessage.warning(t("knowledge.messages.selectFile"))
    return
  }
  if (!isSupportedTextFile(file)) {
    ElMessage.warning(t("knowledge.messages.selectTextFile"))
    return
  }

  uploadingBrowserFile.value = true
  const retry = async () => { await submitBrowserUpload() }
  try {
    await runIngestTask(t("knowledge.upload.fileUpload"), async () => {
      const content = (await file.text()).trim()
      if (!content) {
        throw new Error(t("knowledge.upload.emptyFile"))
      }
      await addTextDocument({
        title: browserForm.title.trim() || stripExtension(file.name),
        content,
        source: browserForm.source.trim() || `upload:${file.name}`,
        visibility: browserForm.visibility,
        metadata: {
          file_name: file.name,
          upload_mode: "browser",
          file_size: String(file.size),
          file_type: file.name.match(/\.[^.]+$/)?.[0]?.toLowerCase() || "text",
          mime_type: file.type || "text/plain",
        },
      })
      resetBrowserUpload()
    }, retry)
  } finally {
    uploadingBrowserFile.value = false
  }
}

const submitTextDocument = async () => {
  if (!textForm.title.trim() || !textForm.content.trim()) {
    ElMessage.warning(t("knowledge.messages.titleContentRequired"))
    return
  }
  savingText.value = true
  const retry = async () => { await submitTextDocument() }
  try {
    await runIngestTask(t("knowledge.upload.textImport"), async () => {
      await addTextDocument({
        title: textForm.title.trim(),
        content: textForm.content.trim(),
        source: textForm.source.trim() || "manual",
        visibility: textForm.visibility,
        metadata: { input_mode: "manual" },
      })
      textForm.title = ""
      textForm.source = "manual"
      textForm.content = ""
      textForm.visibility = "private"
    }, retry)
  } finally {
    savingText.value = false
  }
}

const submitPathDocument = async () => {
  if (!pathForm.path.trim()) {
    ElMessage.warning(t("knowledge.messages.pathRequired"))
    return
  }
  savingPath.value = true
  const retry = async () => { await submitPathDocument() }
  try {
    await runIngestTask(t("knowledge.upload.serverPath"), async () => {
      await addFileDocument({
        path: pathForm.path.trim(),
        title: pathForm.title.trim() || null,
        visibility: pathForm.visibility,
      })
      pathForm.path = ""
      pathForm.title = ""
      pathForm.visibility = "private"
    }, retry)
  } finally {
    savingPath.value = false
  }
}

const openSourceReplacement = (doc: KnowledgeDocument) => {
  if (!doc.can_manage || replacingSourceDocId.value === doc.id) return
  sourceReplacementDocument.value = doc
  sourceReplacementForm.source = doc.source || `upload:${doc.metadata?.file_name || doc.title}`
  selectedSourceReplacementFile.value = null
  sourceReplacementFileList.value = []
  sourceReplacementUploadRef.value?.clearFiles()
  sourceReplacementDialogOpen.value = true
}

const submitSourceReplacement = async () => {
  const doc = sourceReplacementDocument.value
  const file = selectedSourceReplacementFile.value
  if (!doc || !doc.can_manage) return
  if (!file) {
    ElMessage.warning(t("knowledge.messages.selectFile"))
    return
  }
  if (!isSupportedTextFile(file)) {
    ElMessage.warning(t("knowledge.messages.selectTextFile"))
    return
  }

  replacingSourceDocId.value = doc.id
  try {
    const content = (await file.text()).trim()
    if (!content) {
      throw new Error(t("knowledge.upload.emptyFile"))
    }
    const updated = await replaceKnowledgeDocumentSource(doc.id, {
      title: doc.title,
      content,
      file_name: file.name,
      source: sourceReplacementForm.source.trim() || `upload:${file.name}`,
      metadata: {
        file_name: file.name,
        upload_mode: "browser",
        file_size: String(file.size),
        file_type: file.name.match(/\.[^.]+$/)?.[0]?.toLowerCase() || "text",
        mime_type: file.type || "text/plain",
      },
    })
    const index = documents.value.findIndex((item) => item.id === doc.id || item.id === updated.id)
    if (index >= 0) {
      documents.value[index] = { ...documents.value[index], ...updated }
    } else {
      documents.value.unshift(updated)
    }
    await loadKnowledge()
    sourceReplacementDialogOpen.value = false
    ElMessage.success(t("knowledge.messages.sourceReplaced"))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("knowledge.messages.sourceReplaceFailed"))
  } finally {
    replacingSourceDocId.value = null
  }
}

const updateDocumentVisibility = async (doc: KnowledgeDocument, visibility: ResourceVisibility) => {
  if (!doc.can_manage) return
  const currentVisibility = doc.visibility || "private"
  if (visibility === currentVisibility) return
  try {
    const updated = await updateKnowledgeDocumentVisibility(doc.id, visibility)
    doc.visibility = updated.visibility || visibility
    doc.metadata = updated.metadata || doc.metadata
    ElMessage.success(t("visibility.updated"))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("visibility.updateFailed"))
  }
}

const rebuildDocument = async (doc: KnowledgeDocument) => {
  if (!doc.can_manage || rebuildingDocId.value) return
  rebuildingDocId.value = doc.id
  try {
    const updated = await rebuildKnowledgeDocument(doc.id)
    const index = documents.value.findIndex((item) => item.id === doc.id)
    if (index >= 0) {
      documents.value[index] = { ...documents.value[index], ...updated }
    }
    await loadKnowledge()
    ElMessage.success(t("knowledge.messages.rebuilt"))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("knowledge.messages.rebuildFailed"))
  } finally {
    rebuildingDocId.value = null
  }
}

const deleteDocument = async (doc: KnowledgeDocument) => {
  try {
    await ElMessageBox.confirm(t("knowledge.confirm.deleteMessage", { title: doc.title }), t("knowledge.confirm.deleteTitle"), {
      confirmButtonText: t("knowledge.actions.delete"),
      cancelButtonText: t("knowledge.actions.cancel"),
      type: "warning",
    })
    deletingDocId.value = doc.id
    await deleteKnowledgeDocument(doc.id)
    documents.value = documents.value.filter((item) => item.id !== doc.id)
    await loadKnowledge()
    ElMessage.success(t("knowledge.documents.deleted"))
  } catch (err) {
    if (err !== "cancel" && err !== "close") {
      ElMessage.error(err instanceof Error ? err.message : t("knowledge.messages.deleteFailed"))
    }
  } finally {
    deletingDocId.value = null
  }
}

const resetRagSettings = () => {
  if (!status.value) return
  syncRagSettingsFromStatus(status.value)
}

const saveRagSettings = async () => {
  if (!canWriteRagSettings.value) {
    ElMessage.error(t("knowledge.messages.configPermissionRequired"))
    return
  }
  if (ragSettings.chunkOverlap >= ragSettings.chunkSize) {
    ElMessage.error(t("knowledge.messages.chunkOverlapInvalid"))
    return
  }
  ragSaving.value = true
  try {
    const data = await updateKnowledgeRagSettings(ragPayload())
    status.value = data.status
    syncRagSettingsFromStatus(data.status)
    ElMessage.success(t("knowledge.messages.settingsSaved"))
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("knowledge.messages.settingsSaveFailed"))
  } finally {
    ragSaving.value = false
  }
}

const clearAllDocuments = async () => {
  if (documents.value.length === 0) return
  try {
    await ElMessageBox.confirm(t("knowledge.confirm.clearMessage"), t("knowledge.confirm.clearTitle"), {
      confirmButtonText: t("knowledge.actions.clear"),
      cancelButtonText: t("knowledge.actions.cancel"),
      type: "warning",
    })
    clearing.value = true
    await clearKnowledge()
    documents.value = []
    searchResults.value = []
    searched.value = false
    await loadKnowledge()
    ElMessage.success(t("knowledge.messages.cleared"))
  } catch (err) {
    if (err !== "cancel" && err !== "close") {
      ElMessage.error(err instanceof Error ? err.message : t("knowledge.messages.clearFailed"))
    }
  } finally {
    clearing.value = false
  }
}

const runSearch = async () => {
  const query = searchForm.query.trim()
  if (!query) {
    ElMessage.warning(t("knowledge.retrieval.questionRequired"))
    return
  }
  searching.value = true
  searched.value = true
  try {
    const data = await searchKnowledge(query, searchForm.limit, searchForm.searchType)
    searchResults.value = data.results
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : t("knowledge.messages.searchFailed"))
  } finally {
    searching.value = false
  }
}

const openPreview = (doc: KnowledgeDocument) => {
  previewDocument.value = doc
  previewDrawerOpen.value = true
}

const openMetadata = (doc: KnowledgeDocument) => {
  metadataDocument.value = doc
  metadataDialogOpen.value = true
}

const metadataValue = (doc: KnowledgeDocument, ...keys: string[]) => {
  for (const key of keys) {
    const value = doc.metadata?.[key]
    if (value) return value
  }
  return ""
}

const documentType = (doc: KnowledgeDocument) => {
  const metaType = String(doc.type || metadataValue(doc, "file_type", "mime_type") || "")
  if (metaType) return metaType.replace(/^\./, "").toUpperCase()
  const text = `${doc.title} ${doc.source} ${metadataValue(doc, "file_name")}`
  const suffix = text.match(/\.([a-z0-9]+)(?:\s|$)/i)?.[1]
  return (suffix || "TEXT").toUpperCase()
}

const documentSize = (doc: KnowledgeDocument) => {
  const size = Number(doc.size ?? metadataValue(doc, "file_size"))
  if (!Number.isFinite(size) || size <= 0) return "-"
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

const documentStatus = (doc: KnowledgeDocument) => {
  const raw = String(doc.status || metadataValue(doc, "status", "embedding_status")).toLowerCase()
  if (raw.includes("fail") || raw.includes("error")) return { label: t("knowledge.status.failed"), value: "failed", tone: "failed" }
  if (["completed", "complete", "ready", "done", "success", "succeeded"].some((item) => raw.includes(item))) {
    return { label: t("knowledge.status.ready"), value: "ready", tone: "ready" }
  }
  if (Number(doc.chunks || 0) > 0) return { label: t("knowledge.status.ready"), value: "ready", tone: "ready" }
  return { label: t("knowledge.status.parsing"), value: "parsing", tone: "parsing" }
}

const shortId = (value: string) => {
  if (!value) return "-"
  return value.length > 14 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value
}

const formatDate = (value: string) => {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(locale.value, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

const formatScore = (value: number) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return "-"
  return n <= 1 ? n.toFixed(3) : n.toFixed(2)
}

const valueOrDash = (value: unknown) => {
  if (value === null || value === undefined || value === "") return "-"
  return String(value)
}

const prettyJson = (value: unknown) => {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

onMounted(() => {
  loadKnowledge()
})
</script>

<style scoped>
.knowledge-console {
  --kn-bg: var(--ag-frame);
  --kn-panel: var(--ag-panel);
  --kn-panel-soft: var(--ag-panel-soft);
  --kn-border: var(--ag-border);
  --kn-border-strong: var(--ag-border-strong);
  --kn-text: var(--ag-text);
  --kn-heading: var(--ag-heading);
  --kn-muted: var(--ag-muted);
  --kn-ready: var(--ag-green);
  --kn-ready-soft: var(--ag-green-soft);
  --kn-embedding: var(--ag-blue);
  --kn-embedding-soft: var(--ag-blue-soft);
  --kn-parsing: var(--ag-yellow);
  --kn-parsing-soft: var(--ag-yellow-soft);
  --kn-failed: var(--ag-red);
  --kn-failed-soft: var(--ag-red-soft);
  color: var(--kn-text);
}

.knowledge-section-head,
.hit-toolbar,
.hit-meta,
.playground-controls,
.form-action-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.knowledge-section-head p {
  margin: 0;
  color: var(--kn-muted);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.knowledge-section-head h4 {
  margin: 2px 0 0;
  color: var(--kn-heading);
  font-size: 18px;
  font-weight: 820;
}

.knowledge-section-head h4 {
  font-size: 15px;
}

.knowledge-section-head span {
  display: block;
  min-width: 0;
  margin-top: 4px;
  color: var(--kn-muted);
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.retrieval-hit,
.answer-preview,
.advanced-card,
.reader-auto-note,
.empty-box {
  border: 1px solid var(--kn-border);
  border-radius: 12px;
  background: var(--kn-panel);
}

.knowledge-workspace-grid {
  display: grid;
  align-items: start;
  gap: 14px;
  grid-template-columns: minmax(0, 1.08fr) minmax(380px, 0.92fr);
  margin-bottom: 14px;
}

.knowledge-panel {
  min-width: 0;
}

.knowledge-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.knowledge-runtime-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}

.metadata-summary {
  margin-top: 12px;
}

.knowledge-runtime-chip {
  display: grid;
  min-width: 0;
  gap: 4px;
  border: 1px solid var(--kn-border);
  border-radius: var(--ag-radius-control);
  background: var(--kn-panel-soft);
  padding: 8px 10px;
}

.knowledge-runtime-chip span,
.knowledge-runtime-chip strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.knowledge-runtime-chip span {
  color: var(--kn-muted);
  font-size: 11px;
  font-weight: 760;
}

.knowledge-runtime-chip strong {
  color: var(--kn-heading);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 12px;
}

.knowledge-upload-pipeline {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  margin-bottom: 12px;
}

.pipeline-step {
  position: relative;
  border: 1px solid var(--kn-border);
  border-radius: 999px;
  background: var(--kn-panel-soft);
  padding: 6px 8px;
  color: var(--kn-muted);
  font-size: 10px;
  font-weight: 800;
  text-align: center;
}

.pipeline-step.done {
  border-color: color-mix(in srgb, var(--kn-ready) 45%, var(--kn-border));
  background: var(--kn-ready-soft);
  color: var(--kn-ready);
}

.pipeline-step.active {
  border-color: color-mix(in srgb, var(--kn-embedding) 52%, var(--kn-border));
  background: var(--kn-embedding-soft);
  color: var(--kn-embedding);
}

.pipeline-step.failed {
  border-color: color-mix(in srgb, var(--kn-failed) 52%, var(--kn-border));
  background: var(--kn-failed-soft);
  color: var(--kn-failed);
}

.task-feedback {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border-radius: 10px;
  margin-bottom: 12px;
  padding: 8px 10px;
  font-size: 12px;
}

.task-feedback.idle,
.task-feedback.running {
  background: var(--kn-embedding-soft);
  color: var(--kn-embedding);
}

.task-feedback.success {
  background: var(--kn-ready-soft);
  color: var(--kn-ready);
}

.task-feedback.error {
  background: var(--kn-failed-soft);
  color: var(--kn-failed);
}

.upload-mode-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: minmax(0, 1fr) 300px;
}

.upload-side-form,
.text-import-grid,
.path-import-grid,
.playground-question,
.playground-results,
.drawer-stack {
  display: grid;
  gap: 12px;
}

.text-import-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.text-import-content,
.path-action {
  grid-column: 1 / -1;
}

.path-import-grid {
  grid-template-columns: minmax(0, 1fr) 240px;
}

.knowledge-field {
  display: grid;
  gap: 7px;
  min-width: 0;
}

.knowledge-field > span,
.setting-label,
.drawer-label {
  color: var(--kn-muted);
  font-size: 12px;
  font-weight: 700;
}

.reader-auto-note {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  background: var(--kn-panel-soft);
  padding: 9px 10px;
}

.reader-auto-note.roomy {
  margin: 12px 0;
}

.reader-auto-note strong {
  min-width: 0;
  color: var(--kn-heading);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.reader-auto-note span {
  min-width: 0;
  color: var(--kn-muted);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.playground-controls {
  align-items: end;
}

.playground-controls .knowledge-field {
  flex: 1 1 160px;
}

.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--kn-muted);
  font-size: 12px;
}

.retrieval-hit {
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
  justify-content: flex-start;
  flex-wrap: wrap;
  margin-top: 10px;
}

.hit-meta span,
.score-badge,
.type-badge,
.status-badge {
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  border: 1px solid var(--kn-border);
  border-radius: 999px;
  background: var(--kn-panel-soft);
  color: var(--kn-muted);
  font-size: 10px;
  font-weight: 800;
  line-height: 1.3;
  padding: 3px 7px;
}

.score-badge {
  color: var(--kn-ready);
}

.status-badge.ready,
.status-badge.success {
  border-color: color-mix(in srgb, var(--kn-ready) 45%, var(--kn-border));
  background: var(--kn-ready-soft);
  color: var(--kn-ready);
}

.status-badge.embedding,
.status-badge.running {
  border-color: color-mix(in srgb, var(--kn-embedding) 45%, var(--kn-border));
  background: var(--kn-embedding-soft);
  color: var(--kn-embedding);
}

.status-badge.parsing,
.status-badge.idle {
  border-color: color-mix(in srgb, var(--kn-parsing) 45%, var(--kn-border));
  background: var(--kn-parsing-soft);
  color: var(--kn-parsing);
}

.status-badge.failed,
.status-badge.error {
  border-color: color-mix(in srgb, var(--kn-failed) 45%, var(--kn-border));
  background: var(--kn-failed-soft);
  color: var(--kn-failed);
}

.answer-preview {
  background: var(--kn-panel-soft);
  padding: 12px;
}

.answer-preview span {
  color: var(--kn-muted);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}

.answer-preview em {
  display: block;
  margin-top: 8px;
  color: var(--kn-muted);
  font-size: 11px;
  font-style: normal;
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
  min-width: 0;
  color: var(--kn-muted);
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.document-management-controls {
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.document-command-group,
.document-filter-group {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.document-command-group :deep(.el-button) {
  width: 32px;
  height: 32px;
  margin-left: 0;
  padding: 0;
}

.document-filter {
  width: min(100%, 340px);
}

.document-select {
  width: 140px;
}

.document-loading {
  display: grid;
  min-height: 180px;
  place-items: center;
  color: var(--kn-muted);
  font-size: 13px;
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
  grid-template-columns:
    minmax(160px, 1.35fr)
    minmax(46px, 0.28fr)
    minmax(58px, 0.32fr)
    minmax(44px, 0.24fr)
    minmax(82px, 0.42fr)
    minmax(98px, 0.5fr)
    minmax(72px, 0.52fr)
    minmax(88px, 0.44fr)
    132px;
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

.document-table-head > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.document-row {
  background: var(--kn-panel);
  transition: background 0.18s ease;
}

.document-row:hover {
  background: color-mix(in srgb, var(--kn-panel-soft) 48%, var(--kn-panel));
}

.document-row + .document-row {
  border-top: 1px solid var(--kn-border);
}

.document-main,
.document-primary {
  min-width: 0;
}

.document-primary {
  display: grid;
  align-items: start;
  gap: 5px;
}

.doc-title {
  display: block;
  min-width: 0;
  overflow: hidden;
  color: var(--kn-heading);
  font-size: 12px;
  font-weight: 760;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.document-number,
.source-text,
.context-row dd,
.metadata-json {
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
}

.document-number {
  color: var(--kn-heading);
  font-size: var(--document-table-font-size);
  font-weight: 760;
}

.document-time,
.source-text,
.document-time-value {
  min-width: 0;
  overflow: hidden;
  color: var(--kn-muted);
  font-size: var(--document-table-font-size);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-text,
.document-time-value {
  display: block;
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

.document-actions {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
}

.document-action-buttons {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
  max-width: 100%;
}

.document-action-buttons :deep(.el-button) {
  width: 24px;
  height: 24px;
  margin-left: 0;
  padding: 0;
}

.source-replacement-form {
  display: grid;
  gap: 12px;
}

.source-replacement-target {
  display: grid;
  min-width: 0;
  gap: 4px;
  border: 1px solid var(--kn-border);
  border-radius: var(--ag-radius-control);
  background: var(--kn-panel-soft);
  padding: 10px 12px;
}

.source-replacement-target span {
  color: var(--kn-muted);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}

.source-replacement-target strong,
.source-replacement-target em {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-replacement-target strong {
  color: var(--kn-heading);
  font-size: 13px;
  font-weight: 820;
}

.source-replacement-target em {
  color: var(--kn-muted);
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
  font-size: 11px;
  font-style: normal;
}

.source-replacement-upload {
  width: 100%;
}

.source-replacement-upload :deep(.el-upload),
.source-replacement-upload :deep(.el-upload-dragger) {
  width: 100%;
}

.source-replacement-upload :deep(.el-upload-dragger) {
  min-height: 138px;
  border-radius: var(--ag-radius-control);
  background: var(--kn-panel-soft);
}

.source-replacement-footer {
  display: inline-flex;
  width: 100%;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.source-replacement-footer :deep(.el-button) {
  margin-left: 0;
}

.advanced-configuration {
  margin-top: 14px;
}

.advanced-title {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
  color: var(--kn-heading);
  font-weight: 800;
}

.advanced-title em {
  color: var(--kn-muted);
  font-size: 12px;
  font-style: normal;
  font-weight: 500;
}

.advanced-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  padding-top: 8px;
}

.advanced-card {
  padding: 14px;
}

.panel-title {
  min-width: 0;
  color: var(--kn-heading);
  font-size: 12px;
  font-weight: 800;
  overflow-wrap: anywhere;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.panel-title-actions {
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.panel-title-actions > span:first-child,
.panel-button-row {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.panel-button-row {
  flex: 0 0 auto;
}

.panel-button-row :deep(.el-button) {
  margin-left: 0;
}

.strategy-card p {
  margin: 0;
  min-width: 0;
  color: var(--kn-muted);
  font-size: 11px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.strategy-card span,
.strategy-card em {
  display: inline-flex;
  min-width: 0;
  max-width: 100%;
  border: 1px solid var(--kn-border);
  border-radius: 999px;
  padding: 2px 7px;
  color: var(--kn-muted);
  font-size: 10px;
  font-style: normal;
  font-weight: 750;
  line-height: 1.35;
  overflow-wrap: anywhere;
  white-space: normal;
}

.reader-strategy-console {
  display: grid;
  gap: 8px;
}

.strategy-row {
  display: grid;
  grid-template-columns: minmax(96px, 0.8fr) minmax(120px, 0.9fr) minmax(0, 1.3fr) minmax(96px, 0.9fr);
  gap: 10px;
  align-items: center;
  border: 1px solid var(--kn-border);
  border-radius: 8px;
  background: var(--kn-panel-soft);
  padding: 10px;
}

.strategy-name {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.strategy-name strong {
  min-width: 0;
  overflow: hidden;
  color: var(--kn-heading);
  font-size: 12px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.strategy-name span {
  min-width: 0;
  overflow: hidden;
  color: var(--kn-muted);
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.strategy-reader,
.strategy-row em {
  display: inline-flex;
  min-width: 0;
  max-width: 100%;
  border: 1px solid var(--kn-border);
  border-radius: 999px;
  padding: 3px 7px;
  color: var(--kn-muted);
  font-size: 10px;
  font-style: normal;
  font-weight: 750;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.strategy-row p {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--kn-muted);
  font-size: 11px;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rag-settings-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-top: 12px;
}

.rag-wide-field {
  grid-column: 1 / -1;
}

.rag-static-metric {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border: 1px solid var(--kn-border);
  border-radius: 8px;
  background: var(--kn-panel-soft);
  padding: 9px 10px;
}

.rag-static-metric span {
  min-width: 0;
  overflow: hidden;
  color: var(--kn-muted);
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rag-static-metric strong {
  color: var(--kn-heading);
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
  font-size: 12px;
}

.toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid var(--kn-border);
  border-radius: 8px;
  background: var(--kn-panel-soft);
  padding: 9px 10px;
  color: var(--kn-muted);
  font-size: 12px;
  font-weight: 700;
}

.advanced-info-list {
  display: grid;
  gap: 10px;
  margin: 12px 0 0;
}

.context-row {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}

.context-row dt {
  color: var(--kn-muted);
  font-size: 12px;
}

.context-row dd {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--kn-heading);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-box {
  padding: 16px;
  color: var(--kn-muted);
  font-size: 12px;
  text-align: center;
}

.drawer-stack strong,
.drawer-stack p {
  display: block;
  margin: 5px 0 0;
  color: var(--kn-heading);
  overflow-wrap: anywhere;
}

.drawer-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.metadata-json {
  max-height: 360px;
  overflow: auto;
  border: 1px solid var(--kn-border);
  border-radius: 10px;
  background: var(--kn-panel-soft);
  padding: 12px;
  color: var(--kn-heading);
  font-size: 11px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.knowledge-upload :deep(.el-upload-dragger) {
  border-radius: 14px;
  background: var(--kn-panel-soft);
}

@media (max-width: 1320px) {
  .knowledge-workspace-grid,
  .advanced-grid {
    grid-template-columns: minmax(0, 1fr);
  }
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
    min-width: 0;
    overflow: hidden;
    color: var(--kn-muted);
    font-size: 10px;
    font-weight: 800;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .document-actions {
    justify-content: normal;
  }

  .document-action-buttons {
    justify-self: end;
    flex-wrap: wrap;
  }
}

@media (max-width: 760px) {
  .knowledge-console {
    padding: 12px;
  }

  .upload-mode-grid,
  .text-import-grid,
  .path-import-grid,
  .knowledge-upload-pipeline,
  .rag-settings-grid,
  .strategy-row,
  .document-row {
    grid-template-columns: minmax(0, 1fr);
  }

  .knowledge-section-head,
  .document-management-bar,
  .document-management-controls,
  .panel-title-actions,
  .playground-controls {
    flex-direction: column;
  }

  .document-management-controls,
  .document-command-group,
  .document-filter-group,
  .document-filter,
  .document-select,
  .panel-button-row,
  .document-visibility-tabs {
    width: 100%;
  }

  .document-command-group {
    justify-content: flex-start;
  }

  .document-cell:not(.document-main),
  .document-actions {
    grid-template-columns: minmax(64px, 84px) minmax(0, 1fr);
  }
}
</style>
