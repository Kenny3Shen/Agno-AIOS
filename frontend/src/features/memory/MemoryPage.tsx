import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Drawer, Empty, Form, Input, Modal, Popconfirm, Space, Table, Tag, Tooltip, Typography } from 'antd'
import { DeleteOutlined, EditOutlined, SearchOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { CopyableValue, MetadataDescriptions } from '@/shared/ui/MetadataDescriptions'
import { JsonValueCard } from '@/shared/ui/FormattedContentCard'
import { deleteMemory, getMemories, updateMemory, type Memory } from './api'
import { compactId, compareTimestamp, useFormatDate } from '@/shared/lib/format'
import { parseMemoryInput } from './utils'
import { useTranslation } from 'react-i18next'
import { useDebouncedValue } from '@/shared/lib/useDebouncedValue'

export function MemoryPage() {
  const { t } = useTranslation('memory')
  const formatDate = useFormatDate()
  const { message } = App.useApp()
  const client = useQueryClient()
  const [search, setSearch] = useState('')
  const [applied, setApplied] = useState('')
  const debouncedSearch = useDebouncedValue(search, 300)
  const [page, setPage] = useState(1)
  const pageSize = 12
  const [selected, setSelected] = useState<Memory | null>(null)
  const [editing, setEditing] = useState<Memory | null>(null)
  // Apply debounced typing; explicit Query button still sets applied immediately.
  useEffect(() => {
    setApplied(debouncedSearch)
    setPage(1)
  }, [debouncedSearch])
  const query = useQuery({
    queryKey: ['memory', applied, page, pageSize],
    queryFn: () =>
      getMemories({
        search_content: applied || undefined,
        page,
        limit: pageSize,
      }),
  })
  const refresh = () => client.invalidateQueries({ queryKey: ['memory'] })
  const remove = useMutation({
    mutationFn: (row: Memory) => deleteMemory(row.id, row.user_id),
    onSuccess: async (_, row) => {
      if (selected?.id === row.id) setSelected(null)
      await refresh()
    },
    onError: (error) =>
      message.error(error instanceof Error ? error.message : t('deleteFailed')),
  })

  const memoryInput = parseMemoryInput(selected?.input)
  const metadata = selected
    ? [
        {
          key: 'memory',
          label: 'Memory',
          children: <Typography.Paragraph className="memory-metadata-text">{selected.memory || '-'}</Typography.Paragraph>,
        },
        { key: 'user', label: 'User', children: <CopyableValue value={selected.user_id} /> },
        { key: 'agent', label: 'Agent', children: <CopyableValue value={selected.agent_id} /> },
        { key: 'team', label: 'Team', children: <CopyableValue value={selected.team_id} /> },
        { key: 'status', label: 'Status', children: <Tag>{selected.status || 'stored'}</Tag> },
        {
          key: 'topics',
          label: 'Topics',
          children: <Space wrap>{selected.topics?.length ? selected.topics.map((topic) => <Tag key={topic}>{topic}</Tag>) : '-'}</Space>,
        },
        {
          key: 'input',
          label: 'Input',
          children: <Typography.Paragraph className="memory-metadata-text">{memoryInput.text || '-'}</Typography.Paragraph>,
        },
        ...(Object.keys(memoryInput.context).length > 0
          ? [{ key: 'context', label: 'Context', children: <JsonValueCard value={memoryInput.context} title="Additional context" /> }]
          : []),
        { key: 'feedback', label: 'Feedback', children: selected.feedback || '-' },
        { key: 'created', label: 'Created', children: formatDate(selected.created_at) },
        { key: 'updated', label: 'Updated', children: formatDate(selected.updated_at) },
        { key: 'id', label: 'Memory ID', children: <CopyableValue value={selected.id} /> },
      ]
    : []

  return (
    <main className="page">
      <PageHeader title={t('title')} description={t('description')} />
      <Card className="workbench-card memory-toolbar">
        <Space>
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onPressEnter={() => {
              setApplied(search)
              setPage(1)
            }}
            prefix={<SearchOutlined />}
            placeholder={t('searchPlaceholder')}
          />
          <Button
            type="primary"
            onClick={() => {
              setApplied(search)
              setPage(1)
            }}
          >
            {t('common:query')}
          </Button>
        </Space>
      </Card>
      <Card className="workbench-card" title="Memories" extra={<Tag>{query.data?.meta.total_count ?? 0}</Tag>}>
        <Table<Memory>
          rowKey="id"
          dataSource={query.data?.data ?? []}
          loading={query.isLoading}
          pagination={{
            current: page,
            pageSize,
            total: query.data?.meta.total_count ?? 0,
            showSizeChanger: false,
            onChange: setPage,
          }}
          rowClassName={(row) => (row.id === selected?.id ? 'selected-table-row' : '')}
          onRow={(row) => ({
            tabIndex: 0,
            role: 'button',
            'aria-label': t('viewMemory', { id: row.id }),
            onClick: () => setSelected(row),
            onKeyDown: (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                setSelected(row)
              }
            },
          })}
          columns={[
            { title: 'Memory', dataIndex: 'memory', ellipsis: true },
            {
              title: 'Topics',
              dataIndex: 'topics',
              width: 220,
              render: (topics: string[]) => (
                <Space wrap>
                  {(topics ?? []).map((topic) => (
                    <Tag key={topic}>{topic}</Tag>
                  ))}
                </Space>
              ),
            },
            { title: 'User', dataIndex: 'user_id', width: 130, render: compactId },
            {
              title: 'Updated',
              dataIndex: 'updated_at',
              width: 170,
              defaultSortOrder: 'descend' as const,
              sorter: (a: Memory, b: Memory) => compareTimestamp(a.updated_at, b.updated_at),
              render: formatDate,
            },
            {
              title: 'Actions',
              key: 'actions',
              width: 88,
              render: (_, row) => (
                <Space size={2} onClick={(event) => event.stopPropagation()}>
                  <Tooltip title={t('common:edit')}>
                    <Button
                      aria-label={t('editNamed', { id: row.id })}
                      type="text"
                      size="small"
                      icon={<EditOutlined />}
                      onClick={(event) => {
                        event.stopPropagation()
                        setEditing(row)
                      }}
                    />
                  </Tooltip>
                  <Tooltip title={t('common:delete')}>
                    <Popconfirm
                      title={t('deleteConfirm')}
                      onConfirm={(event) => {
                        event?.stopPropagation()
                        remove.mutate(row)
                      }}
                    >
                      <Button
                        aria-label={t('deleteNamed', { id: row.id })}
                        danger
                        type="text"
                        size="small"
                        icon={<DeleteOutlined />}
                        onClick={(event) => event.stopPropagation()}
                      />
                    </Popconfirm>
                  </Tooltip>
                </Space>
              ),
            },
          ]}
        />
      </Card>
      <Drawer
        size={520}
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title="Metadata"
        destroyOnHidden
      >
        {selected ? (
          <MetadataDescriptions items={metadata} />
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('selectForDetails')} />
        )}
      </Drawer>
      <Modal open={Boolean(editing)} footer={null} onCancel={() => setEditing(null)} title={t('editMemory')} destroyOnHidden>
        {editing && (
          <Form
            layout="vertical"
            initialValues={{ memory: editing.memory, topics: editing.topics?.join(', ') }}
            onFinish={async ({ memory, topics }: { memory: string; topics: string }) => {
              try {
                await updateMemory(
                  editing.id,
                  memory,
                  topics
                    .split(',')
                    .map((value) => value.trim())
                    .filter(Boolean)
                )
                message.success(t('updated'))
                setEditing(null)
                setSelected(null)
                await refresh()
              } catch (error) {
                message.error(error instanceof Error ? error.message : t('updateFailed'))
              }
            }}
          >
            <Form.Item name="memory" label="Memory" rules={[{ required: true }]}>
              <Input.TextArea rows={8} />
            </Form.Item>
            <Form.Item name="topics" label="Topics">
              <Input />
            </Form.Item>
            <Button type="primary" htmlType="submit">
              {t('common:save')}
            </Button>
          </Form>
        )}
      </Modal>
    </main>
  )
}
