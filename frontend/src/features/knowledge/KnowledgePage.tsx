import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Descriptions, Form, Input, InputNumber, Select, Space, Tabs, Tag, Typography } from 'antd'
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { Markdown } from '@/shared/ui/Markdown'
import { PageHeader } from '@/shared/ui/PageHeader'
import { JsonValueCard } from '@/shared/ui/FormattedContentCard'
import type { ResourceVisibility } from '@/shared/types/common'
import { deleteDocument, getKnowledge, searchKnowledge, updateDocumentAction } from './api'
import type { Document, KnowledgeResponse, KnowledgeSearchType, RetrievalRenderMode, SearchResult } from './types'
import { DocumentsTable } from './components/DocumentsTable'
import { MetadataPanel } from './components/MetadataPanel'
import { DocumentDrawer } from './components/DocumentDrawer'
import { UpdateDocumentDrawer } from './components/UpdateDocumentDrawer'
import { effectiveKnowledgeIngestDefaults, resolveRetrievalContent, SEARCH_TYPE_OPTIONS } from './utils'
import { useTranslation } from 'react-i18next'
import { useDebouncedValue } from '@/shared/lib/useDebouncedValue'

function scoreKind(result: SearchResult): 'rerank' | 'similarity' | 'score' {
  const meta = result.metadata ?? {}
  if (meta.rerank_score != null || meta.reranking_score != null) return 'rerank'
  if (meta.similarity_score != null) return 'similarity'
  return 'score'
}

function RetrievalResultCard({ result }: { result: SearchResult }) {
  const { t } = useTranslation('knowledge')
  const [renderMode, setRenderMode] = useState<RetrievalRenderMode>('auto')
  const content = resolveRetrievalContent(result, renderMode)
  const kind = scoreKind(result)
  const scoreLabel =
    kind === 'rerank' ? t('resultScoreRerank') : kind === 'similarity' ? t('resultScoreSimilarity') : t('resultScore')
  const renderModeOptions: Array<{ value: RetrievalRenderMode; label: string }> = [
    { value: 'auto', label: t('renderModeAuto') },
    { value: 'markdown', label: t('renderModeMarkdown') },
    { value: 'json', label: t('renderModeJson') },
    { value: 'text', label: t('renderModeText') },
  ]
  return (
    <Card
      size="small"
      key={`${result.doc_id}-${result.chunk_index}`}
      title={result.title}
      extra={
        <Space size={6} wrap>
          <Select
            aria-label={t('renderAria', { title: result.title })}
            size="small"
            value={renderMode}
            options={renderModeOptions}
            onChange={setRenderMode}
            style={{ width: 118 }}
          />
          <Tag>{content.kind}</Tag>
          <Tag color={kind === 'rerank' ? 'purple' : kind === 'similarity' ? 'blue' : 'default'}>
            {scoreLabel} {Number(result.score || 0).toFixed(4)}
          </Tag>
        </Space>
      }
    >
      <Descriptions
        className="retrieval-result-meta"
        bordered
        size="small"
        column={1}
        items={[
          { key: 'score', label: t('resultScore'), children: Number(result.score || 0).toFixed(4) },
          { key: 'source', label: t('resultSource'), children: result.source || '-' },
          { key: 'chunk', label: t('resultChunk'), children: result.chunk_index },
          {
            key: 'document',
            label: t('resultDocument'),
            children: <Typography.Text copyable={{ text: result.doc_id }}>{result.doc_id}</Typography.Text>,
          },
        ]}
      />
      <div className="retrieval-result-content">
        {content.kind === 'json' ? (
          <JsonValueCard value={content.value} title={t('resultContent')} />
        ) : content.kind === 'markdown' ? (
          <Markdown content={String(content.value)} openLinksInNewTab escapeRawHtml />
        ) : (
          <Typography.Paragraph className="formatted-text">{String(content.value)}</Typography.Paragraph>
        )}
      </div>
    </Card>
  )
}

function isProcessingDocument(document: Document) {
  return document.status === 'processing' || document.id.startsWith('processing:')
}

export function KnowledgePage() {
  const { t } = useTranslation('knowledge')
  const searchTypeOptions = SEARCH_TYPE_OPTIONS.map((value) => ({ value, label: value }))
  const { message } = App.useApp()
  const client = useQueryClient()
  const [filter, setFilter] = useState('')
  const debouncedFilter = useDebouncedValue(filter, 300)
  const [page, setPage] = useState(1)
  const pageSize = 12
  const [sortBy, setSortBy] = useState<'updated_at' | 'created_at' | 'name' | 'status'>('updated_at')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [selectedId, setSelectedId] = useState('')
  const [metaOpen, setMetaOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [updateOpen, setUpdateOpen] = useState(false)
  const [results, setResults] = useState<SearchResult[]>([])
  useEffect(() => {
    setPage(1)
  }, [debouncedFilter])
  const query = useQuery({
    queryKey: ['knowledge', debouncedFilter, page, pageSize, sortBy, sortOrder],
    queryFn: () =>
      getKnowledge({
        query: debouncedFilter,
        page,
        limit: pageSize,
        sortBy,
        sortOrder,
      }),
  })
  const documents = query.data?.data ?? []
  const ingestDefaults = useMemo(
    () => effectiveKnowledgeIngestDefaults(query.data?.meta.ingest_defaults),
    [query.data?.meta.ingest_defaults],
  )
  const selected = documents.find((document) => document.id === selectedId) ?? null
  const refresh = () => client.invalidateQueries({ queryKey: ['knowledge'] })

  const syncUpdatedDocument = async (document: Document, previousId = selectedId, selectDocument = true) => {
    const processing = isProcessingDocument(document)
    const visibleDocument = processing && previousId ? { ...document, id: previousId } : document
    const currentKey = ['knowledge', debouncedFilter, page, pageSize, sortBy, sortOrder]
    client.setQueryData<KnowledgeResponse>(currentKey, (current) =>
      current
        ? {
            ...current,
            data: previousId
              ? current.data.map((item) => (item.id === previousId ? visibleDocument : item))
              : [visibleDocument, ...current.data],
          }
        : current
    )
    if (selectDocument) setSelectedId(visibleDocument.id)
    if (!processing) await refresh()
  }

  const remove = useMutation({
    mutationFn: deleteDocument,
    onSuccess: async () => {
      setSelectedId('')
      setMetaOpen(false)
      await refresh()
      message.success(t('deleted'))
    },
    onError: (error) => message.error(error.message),
  })
  const visibility = useMutation({
    mutationFn: ({ id, value }: { id: string; value: ResourceVisibility }) =>
      updateDocumentAction(id, { mode: 'metadata', metadata: { visibility: value } }),
    onSuccess: (document, variables) => syncUpdatedDocument(document, variables.id, selectedId === variables.id),
    onError: (error) => message.error(error.message),
  })
  const openMetadata = (document: Document) => {
    setSelectedId(document.id)
    setMetaOpen(true)
  }
  const openUpdate = (document: Document) => {
    setSelectedId(document.id)
    setUpdateOpen(true)
  }

  return (
    <main className="page knowledge-page">
      <PageHeader title={t('title')}
        description={t('description')}
        actions={
          <>
            <Button icon={<ReloadOutlined />} onClick={() => void refresh()}>
              {t('common:refresh')}
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              {t('addDocShort')}
            </Button>
          </>
        }
      />
      <Tabs
        className="knowledge-tabs"
        items={[
          {
            key: 'documents',
            label: t('documents'),
            children: (
              <DocumentsTable
                documents={documents}
                filter={filter}
                loading={query.isLoading}
                selectedId={selectedId}
                onFilterChange={setFilter}
                onSelect={openMetadata}
                onUpdate={openUpdate}
                onDelete={(document) => remove.mutate(document.id)}
                onVisibilityChange={(document, value) => visibility.mutate({ id: document.id, value })}
                deletingId={remove.isPending ? remove.variables : undefined}
                paginationTotal={query.data?.meta.total_count ?? 0}
                paginationPage={page}
                paginationPageSize={pageSize}
                onPaginationChange={setPage}
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSortChange={(nextSortBy, nextSortOrder) => {
                  setSortBy(nextSortBy)
                  setSortOrder(nextSortOrder)
                  setPage(1)
                }}
              />
            ),
          },
          {
            key: 'retrieval',
            label: t('tabRetrieval'),
            children: (
              <Card className="workbench-card retrieval-playground">
                <Space className="retrieval-toolbar" align="start" wrap>
                  <Form
                    key={ingestDefaults.search_type}
                    layout="inline"
                    onFinish={async ({
                      query: text,
                      limit,
                      search_type,
                    }: {
                      query: string
                      limit: number
                      search_type: KnowledgeSearchType
                    }) => {
                      try {
                        setResults(await searchKnowledge(text, limit, search_type))
                      } catch (error) {
                        message.error(error instanceof Error ? error.message : t('searchFailed'))
                      }
                    }}
                    initialValues={{ limit: 5, search_type: ingestDefaults.search_type }}
                  >
                    <Form.Item name="query" rules={[{ required: true }]} style={{ flex: 1 }}>
                      <Input prefix={<SearchOutlined />} placeholder={t('searchPlaceholder')} />
                    </Form.Item>
                    <Form.Item name="search_type" label={t('searchType')}>
                      <Select options={searchTypeOptions} style={{ width: 120 }} />
                    </Form.Item>
                    <Form.Item name="limit">
                      <InputNumber min={1} max={20} />
                    </Form.Item>
                    <Button htmlType="submit" type="primary">
                      {t('retrieve')}
                    </Button>
                  </Form>
                </Space>
                {(() => {
                  const threshold = query.data?.meta.retrieval_settings?.similarity_threshold
                  return (
                    <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>
                      {threshold == null || threshold <= 0
                        ? t('retrievalThresholdOff')
                        : t('retrievalThresholdHint', { threshold: Number(threshold).toFixed(2) })}
                    </Typography.Paragraph>
                  )
                })()}
                <div className="retrieval-results">
                  {results.length === 0 ? (
                    <Typography.Text type="secondary">{t('noRetrievalHits')}</Typography.Text>
                  ) : (
                    results.map((item) => (
                      <RetrievalResultCard key={`${item.doc_id}-${item.chunk_index}`} result={item} />
                    ))
                  )}
                </div>
              </Card>
            ),
          },
        ]}
      />
      <MetadataPanel document={selected} open={metaOpen && Boolean(selected)} onClose={() => setMetaOpen(false)} />
      <DocumentDrawer
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(document) => syncUpdatedDocument(document, '')}
        ingestDefaults={ingestDefaults}
      />
      {updateOpen && selected && (
        <UpdateDocumentDrawer
          document={selected}
          open
          onClose={() => setUpdateOpen(false)}
          onUpdated={(document) => syncUpdatedDocument(document, selectedId)}
          ingestDefaults={ingestDefaults}
        />
      )}
    </main>
  )
}
