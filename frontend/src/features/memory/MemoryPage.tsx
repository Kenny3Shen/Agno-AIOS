import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Empty, Form, Grid, Input, Modal, Popconfirm, Space, Splitter, Table, Tag, Tooltip, Typography } from 'antd'
import { DeleteOutlined, EditOutlined, SearchOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { CopyableValue, MetadataDescriptions } from '@/shared/ui/MetadataDescriptions'
import { JsonValueCard } from '@/shared/ui/FormattedContentCard'
import { deleteMemory, getMemories, updateMemory, type Memory } from './api'
import { compactId, formatDate } from '@/shared/lib/format'
import { parseMemoryInput } from './utils'

export function MemoryPage() {
  const { message } = App.useApp()
  const client = useQueryClient()
  const screens = Grid.useBreakpoint()
  const vertical = screens.md === false
  const [search, setSearch] = useState('')
  const [applied, setApplied] = useState('')
  const [selected, setSelected] = useState<Memory | null>(null)
  const [editing, setEditing] = useState<Memory | null>(null)
  const query = useQuery({ queryKey: ['memory', applied], queryFn: () => getMemories({ search: applied }) })
  const refresh = () => client.invalidateQueries({ queryKey: ['memory'] })
  const remove = useMutation({
    mutationFn: (row: Memory) => deleteMemory(row.id, row.user_id),
    onSuccess: async (_, row) => {
      if (selected?.id === row.id) setSelected(null)
      await refresh()
    },
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
      <PageHeader title="Memory" description="审阅、修订和删除 Agent 用户记忆" />
      <Card className="workbench-card memory-toolbar">
        <Space>
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onPressEnter={() => setApplied(search)}
            prefix={<SearchOutlined />}
            placeholder="搜索记忆、用户或主题"
          />
          <Button type="primary" onClick={() => setApplied(search)}>
            查询
          </Button>
        </Space>
      </Card>
      <Splitter className="workbench-splitter memory-splitter" orientation={vertical ? 'vertical' : 'horizontal'}>
        <Splitter.Panel defaultSize="70%" min={vertical ? 280 : '45%'}>
          <Card className="workbench-card splitter-panel-card" title="Memories" extra={<Tag>{query.data?.total ?? 0}</Tag>}>
            <Table<Memory>
              rowKey="id"
              dataSource={query.data?.items ?? []}
              loading={query.isLoading}
              pagination={{ pageSize: 12 }}
              rowClassName={(row) => (row.id === selected?.id ? 'selected-table-row' : '')}
              onRow={(row) => ({
                tabIndex: 0,
                role: 'button',
                'aria-label': `查看记忆 ${row.id}`,
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
                { title: 'Updated', dataIndex: 'updated_at', width: 170, render: formatDate },
                {
                  title: 'Actions',
                  key: 'actions',
                  width: 88,
                  render: (_, row) => (
                    <Space size={2} onClick={(event) => event.stopPropagation()}>
                      <Tooltip title="编辑">
                        <Button
                          aria-label={`编辑 ${row.id}`}
                          type="text"
                          size="small"
                          icon={<EditOutlined />}
                          onClick={(event) => {
                            event.stopPropagation()
                            setEditing(row)
                          }}
                        />
                      </Tooltip>
                      <Tooltip title="删除">
                        <Popconfirm
                          title="删除这条记忆？"
                          onConfirm={(event) => {
                            event?.stopPropagation()
                            remove.mutate(row)
                          }}
                        >
                          <Button
                            aria-label={`删除 ${row.id}`}
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
        </Splitter.Panel>
        <Splitter.Panel defaultSize="30%" min={vertical ? 220 : '20%'}>
          <Card className="workbench-card splitter-panel-card" title="Metadata">
            {selected ? (
              <MetadataDescriptions items={metadata} />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择一条记忆查看详情" />
            )}
          </Card>
        </Splitter.Panel>
      </Splitter>
      <Modal open={Boolean(editing)} footer={null} onCancel={() => setEditing(null)} title="编辑记忆" destroyOnHidden>
        {editing && (
          <Form
            layout="vertical"
            initialValues={{ memory: editing.memory, topics: editing.topics?.join(', ') }}
            onFinish={async ({ memory, topics }: { memory: string; topics: string }) => {
              await updateMemory(
                editing.id,
                memory,
                topics
                  .split(',')
                  .map((value) => value.trim())
                  .filter(Boolean)
              )
              message.success('记忆已更新')
              setEditing(null)
              setSelected(null)
              await refresh()
            }}
          >
            <Form.Item name="memory" label="Memory" rules={[{ required: true }]}>
              <Input.TextArea rows={8} />
            </Form.Item>
            <Form.Item name="topics" label="Topics">
              <Input />
            </Form.Item>
            <Button type="primary" htmlType="submit">
              保存
            </Button>
          </Form>
        )}
      </Modal>
    </main>
  )
}
