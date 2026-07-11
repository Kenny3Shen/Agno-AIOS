import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Form, Grid, Input, InputNumber, Splitter, Tabs, Tag } from 'antd'
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import XMarkdown from '@ant-design/x-markdown'
import { PageHeader } from '@/shared/ui/PageHeader'
import type { ResourceVisibility } from '@/shared/types/common'
import { deleteDocument, getKnowledge, searchKnowledge, updateDocumentAction } from './api'
import type { Document, KnowledgeResponse, SearchResult } from './types'
import { DocumentsTable } from './components/DocumentsTable'
import { MetadataPanel } from './components/MetadataPanel'
import { DocumentDrawer } from './components/DocumentDrawer'
import { UpdateDocumentDrawer } from './components/UpdateDocumentDrawer'

export function KnowledgePage() {
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
  const selected = documents.find((document) => document.id === selectedId) ?? null
  const refresh = () => client.invalidateQueries({ queryKey: ['knowledge'] })

  const syncUpdatedDocument = async (document: Document, previousId = selectedId, selectDocument = true) => {
    const currentKey = ['knowledge', filter]
    client.setQueryData<KnowledgeResponse>(currentKey, (current) => current ? {
      ...current,
      documents: previousId
        ? current.documents.map((item) => item.id === previousId ? document : item)
        : [document, ...current.documents],
    } : current)
    if (selectDocument) setSelectedId(document.id)
    await refresh()
  }

  const remove = useMutation({
    mutationFn: deleteDocument,
    onSuccess: async () => {
      setSelectedId('')
      await refresh()
      message.success('文档已删除')
    },
    onError: (error) => message.error(error.message),
  })
  const visibility = useMutation({
    mutationFn: ({ id, value }: { id: string; value: ResourceVisibility }) => updateDocumentAction(id, { mode: 'metadata', metadata: { visibility: value } }),
    onSuccess: (document, variables) => syncUpdatedDocument(document, variables.id, selectedId === variables.id),
    onError: (error) => message.error(error.message),
  })
  const openUpdate = (document: Document) => {
    setSelectedId(document.id)
    setUpdateOpen(true)
  }

  return <main className="page knowledge-page">
    <PageHeader title="Knowledge" description="管理 Agent 检索知识、入库状态和资源可见性" actions={<><Button icon={<ReloadOutlined />} onClick={() => void refresh()}>刷新</Button><Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>添加文档</Button></>} />
    <Tabs className="knowledge-tabs" items={[
      { key: 'documents', label: 'Documents', children: <Splitter className="workbench-splitter knowledge-splitter" orientation={vertical ? 'vertical' : 'horizontal'}>
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
      </Splitter> },
      { key: 'retrieval', label: 'Retrieval playground', children: <Card className="workbench-card retrieval-playground">
        <Form layout="inline" onFinish={async ({ query: text, limit }: { query: string; limit: number }) => setResults(await searchKnowledge(text, limit))} initialValues={{ limit: 5 }}>
          <Form.Item name="query" rules={[{ required: true }]} style={{ flex: 1 }}><Input prefix={<SearchOutlined />} placeholder="测试检索查询" /></Form.Item>
          <Form.Item name="limit"><InputNumber min={1} max={20} /></Form.Item>
          <Button htmlType="submit" type="primary">检索</Button>
        </Form>
        <div className="retrieval-results">{results.map((item) => <Card size="small" key={`${item.doc_id}-${item.chunk_index}`} title={item.title} extra={<Tag>{item.score.toFixed(3)}</Tag>}><XMarkdown content={item.content} escapeRawHtml /></Card>)}</div>
      </Card> },
    ]} />
    <DocumentDrawer open={createOpen} onClose={() => setCreateOpen(false)} onCreated={(document) => syncUpdatedDocument(document, '')} />
    {updateOpen && selected && <UpdateDocumentDrawer document={selected} open onClose={() => setUpdateOpen(false)} onUpdated={syncUpdatedDocument} />}
  </main>
}
