import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Descriptions, Form, Grid, Input, InputNumber, Select, Space, Splitter, Tabs, Tag, Typography } from 'antd'
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import XMarkdown from '@ant-design/x-markdown'
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

const renderModeOptions: Array<{ value: RetrievalRenderMode; label: string }> = [
  { value: 'auto', label: 'Auto' },
  { value: 'markdown', label: 'Markdown' },
  { value: 'json', label: 'JSON' },
  { value: 'text', label: 'Text' },
]

const searchTypeOptions = SEARCH_TYPE_OPTIONS.map((value) => ({ value, label: value }))

function RetrievalResultCard({ result }: { result: SearchResult }) {
  const [renderMode, setRenderMode] = useState<RetrievalRenderMode>('auto')
  const content = resolveRetrievalContent(result, renderMode)
  return (
    <Card
      size="small"
      key={`${result.doc_id}-${result.chunk_index}`}
      title={result.title}
      extra={
        <Space size={6} wrap>
          <Select
            aria-label={`Render ${result.title}`}
            size="small"
            value={renderMode}
            options={renderModeOptions}
            onChange={setRenderMode}
            style={{ width: 118 }}
          />
          <Tag>{content.kind}</Tag>
          <Tag>{result.score.toFixed(3)}</Tag>
        </Space>
      }
    >
      <Descriptions
        className="retrieval-result-meta"
        bordered
        size="small"
        column={1}
        items={[
          { key: 'source', label: 'Source', children: result.source || '-' },
          { key: 'chunk', label: 'Chunk', children: result.chunk_index },
          {
            key: 'document',
            label: 'Document',
            children: <Typography.Text copyable={{ text: result.doc_id }}>{result.doc_id}</Typography.Text>,
          },
        ]}
      />
      <div className="retrieval-result-content">
        {content.kind === 'json' ? (
          <JsonValueCard value={content.value} title="Content" />
        ) : content.kind === 'markdown' ? (
          <XMarkdown content={String(content.value)} openLinksInNewTab escapeRawHtml />
        ) : (
          <Typography.Paragraph className="formatted-text">{String(content.value)}</Typography.Paragraph>
        )}
      </div>
    </Card>
  )
}

export function KnowledgePage() {
  const { t } = useTranslation('knowledge')
  const { message } = App.useApp()
  const screens = Grid.useBreakpoint()
  const vertical = screens.md === false
  const client = useQueryClient()
  const [filter, setFilter] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [updateOpen, setUpdateOpen] = useState(false)
  const [results, setResults] = useState<SearchResult[]>([])
  const query = useQuery({ queryKey: ['knowledge', filter], queryFn: () => getKnowledge(filter) })
  const documents = query.data?.documents ?? []
  const ingestDefaults = useMemo(() => effectiveKnowledgeIngestDefaults(query.data?.status.rag_settings), [query.data?.status.rag_settings])
  const selected = documents.find((document) => document.id === selectedId) ?? null
  const refresh = () => client.invalidateQueries({ queryKey: ['knowledge'] })

  const syncUpdatedDocument = async (document: Document, previousId = selectedId, selectDocument = true) => {
    const currentKey = ['knowledge', filter]
    client.setQueryData<KnowledgeResponse>(currentKey, (current) =>
      current
        ? {
            ...current,
            documents: previousId
              ? current.documents.map((item) => (item.id === previousId ? document : item))
              : [document, ...current.documents],
          }
        : current
    )
    if (selectDocument) setSelectedId(document.id)
    await refresh()
  }

  const remove = useMutation({
    mutationFn: deleteDocument,
    onSuccess: async () => {
      setSelectedId('')
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
            label: 'Documents',
            children: (
              <Splitter className="workbench-splitter knowledge-splitter" orientation={vertical ? 'vertical' : 'horizontal'}>
                <Splitter.Panel defaultSize="70%" min={vertical ? 260 : '45%'}>
                  <DocumentsTable
                    documents={documents}
                    filter={filter}
                    loading={query.isLoading}
                    selectedId={selectedId}
                    vertical={vertical}
                    onFilterChange={setFilter}
                    onSelect={(document) => setSelectedId(document.id)}
                    onUpdate={openUpdate}
                    onDelete={(document) => remove.mutate(document.id)}
                    onVisibilityChange={(document, value) => visibility.mutate({ id: document.id, value })}
                    deletingId={remove.isPending ? remove.variables : undefined}
                  />
                </Splitter.Panel>
                <Splitter.Panel defaultSize="30%" min={vertical ? 180 : '20%'}>
                  <MetadataPanel document={selected} />
                </Splitter.Panel>
              </Splitter>
            ),
          },
          {
            key: 'retrieval',
            label: 'Retrieval playground',
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
                    }) => setResults(await searchKnowledge(text, limit, search_type))}
                    initialValues={{ limit: 5, search_type: ingestDefaults.search_type }}
                  >
                    <Form.Item name="query" rules={[{ required: true }]} style={{ flex: 1 }}>
                      <Input prefix={<SearchOutlined />} placeholder={t('searchPlaceholder')} />
                    </Form.Item>
                    <Form.Item name="search_type" label="Search type">
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
                <div className="retrieval-results">
                  {results.map((item) => (
                    <RetrievalResultCard key={`${item.doc_id}-${item.chunk_index}`} result={item} />
                  ))}
                </div>
              </Card>
            ),
          },
        ]}
      />
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
          onUpdated={syncUpdatedDocument}
          ingestDefaults={ingestDefaults}
        />
      )}
    </main>
  )
}
