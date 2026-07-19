/**
 * Memory workbench: search, user filter, edit/delete, and scoped clear.
 * List uses Agno-style data/meta; clear requires memories:delete (all_users admin).
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Drawer, Empty, Form, Input, Modal, Popconfirm, Space, Table, Tag, Tooltip, Typography } from 'antd'
import { DeleteOutlined, EditOutlined, SearchOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { CopyableValue, MetadataDescriptions } from '@/shared/ui/MetadataDescriptions'
import { JsonValueCard } from '@/shared/ui/FormattedContentCard'
import { clearMemories, deleteMemory, getMemories, updateMemory, type Memory } from './api'
import { compactId, compareTimestamp, useFormatDate } from '@/shared/lib/format'
import { parseMemoryInput } from './utils'
import { useTranslation } from 'react-i18next'
import { useDebouncedValue } from '@/shared/lib/useDebouncedValue'
import { currentUserQuery } from '@/features/auth'
import { hasScope, roleOf } from '@/shared/auth/permissions'

export function MemoryPage() {
  const { t } = useTranslation('memory')
  const formatDate = useFormatDate()
  const { message } = App.useApp()
  const client = useQueryClient()
  const [search, setSearch] = useState('')
  const [applied, setApplied] = useState('')
  const debouncedSearch = useDebouncedValue(search, 300)
  const [userFilter, setUserFilter] = useState('')
  const [appliedUser, setAppliedUser] = useState('')
  const debouncedUser = useDebouncedValue(userFilter, 300)
  const [page, setPage] = useState(1)
  const currentUser = useQuery(currentUserQuery())
  const isAdmin = roleOf(currentUser.data) === 'admin'
  const canDelete = hasScope(currentUser.data, 'memories:delete')
  const pageSize = 12
  const [selected, setSelected] = useState<Memory | null>(null)
  const [editing, setEditing] = useState<Memory | null>(null)
  // Apply debounced typing; explicit Query button still sets applied immediately.
  useEffect(() => {
    setApplied(debouncedSearch)
    setPage(1)
  }, [debouncedSearch])
  useEffect(() => {
    setAppliedUser(debouncedUser.trim())
    setPage(1)
  }, [debouncedUser])
  const query = useQuery({
    queryKey: ['memory', applied, appliedUser, page, pageSize],
    queryFn: () =>
      getMemories({
        search_content: applied || undefined,
        user_id: appliedUser || undefined,
        page,
        limit: pageSize,
      }),
  })
  const refresh = () => client.invalidateQueries({ queryKey: ['memory'] })
  const remove = useMutation({
    mutationFn: (row: Memory) => deleteMemory(row.memory_id, row.user_id),
    onSuccess: async (_, row) => {
      if (selected?.memory_id === row.memory_id) setSelected(null)
      await refresh()
    },
    onError: (error) =>
      message.error(error instanceof Error ? error.message : t('deleteFailed')),
  })
  const clearMutation = useMutation({
    mutationFn: (payload: { user_id?: string; all_users?: boolean }) => clearMemories(payload),
    onSuccess: async (result) => {
      setSelected(null)
      if (result.all_users || result.deleted < 0) {
        message.success(t('clearAllOk'))
      } else {
        message.success(t('clearOk', { count: result.deleted ?? 0 }))
      }
      await refresh()
    },
    onError: (error) =>
      message.error(error instanceof Error ? error.message : t('clearFailed')),
  })

  const memoryInput = parseMemoryInput(selected?.input)
  const metadata = selected
    ? [
        {
          key: 'memory',
          label: t('labelMemory'),
          children: <Typography.Paragraph className="memory-metadata-text">{selected.memory || '-'}</Typography.Paragraph>,
        },
        { key: 'user', label: t('labelUser'), children: <CopyableValue value={selected.user_id} /> },
        { key: 'agent', label: t('labelAgent'), children: <CopyableValue value={selected.agent_id} /> },
        { key: 'team', label: t('labelTeam'), children: <CopyableValue value={selected.team_id} /> },
        { key: 'status', label: t('labelStatus'), children: <Tag>{selected.status || t('statusStored')}</Tag> },
        {
          key: 'topics',
          label: t('labelTopics'),
          children: <Space wrap>{selected.topics?.length ? selected.topics.map((topic) => <Tag key={topic}>{topic}</Tag>) : '-'}</Space>,
        },
        {
          key: 'input',
          label: t('labelInput'),
          children: <Typography.Paragraph className="memory-metadata-text">{memoryInput.text || '-'}</Typography.Paragraph>,
        },
        ...(Object.keys(memoryInput.context).length > 0
          ? [{ key: 'context', label: t('labelContext'), children: <JsonValueCard value={memoryInput.context} title={t('additionalContext')} /> }]
          : []),
        { key: 'feedback', label: t('labelFeedback'), children: selected.feedback || '-' },
        { key: 'created', label: t('labelCreated'), children: formatDate(selected.created_at) },
        { key: 'updated', label: t('labelUpdated'), children: formatDate(selected.updated_at) },
        { key: 'id', label: t('labelMemoryId'), children: <CopyableValue value={selected.memory_id} /> },
      ]
    : []

  return (
    <main className="page">
      <PageHeader title={t('title')} description={t('description')} />
      <Card className="workbench-card memory-toolbar">
        <Space wrap>
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onPressEnter={() => {
              setApplied(search)
              setPage(1)
            }}
            prefix={<SearchOutlined />}
            placeholder={t('searchPlaceholder')}
            allowClear
          />
          {isAdmin ? (
            <Input
              value={userFilter}
              onChange={(event) => setUserFilter(event.target.value)}
              onPressEnter={() => {
                setAppliedUser(userFilter.trim())
                setPage(1)
              }}
              placeholder={t('userFilterPlaceholder')}
              allowClear
              style={{ minWidth: 200 }}
              aria-label={t('filterUser')}
            />
          ) : null}
          <Button
            type="primary"
            onClick={() => {
              setApplied(search)
              setAppliedUser(userFilter.trim())
              setPage(1)
            }}
          >
            {t('common:query')}
          </Button>
          {canDelete ? (
            <Popconfirm
              title={
                appliedUser
                  ? t('clearUserConfirm', { user: appliedUser })
                  : t('clearMineConfirm')
              }
              onConfirm={() =>
                clearMutation.mutate(
                  appliedUser ? { user_id: appliedUser } : {},
                )
              }
            >
              <Button danger loading={clearMutation.isPending} title={t('clearHint')}>
                {appliedUser ? t('clearUser') : t('clearMine')}
              </Button>
            </Popconfirm>
          ) : null}
          {canDelete && isAdmin ? (
            <Popconfirm
              title={t('clearAllConfirm')}
              onConfirm={() => clearMutation.mutate({ all_users: true })}
            >
              <Button danger type="primary" loading={clearMutation.isPending}>
                {t('clearAll')}
              </Button>
            </Popconfirm>
          ) : null}
        </Space>
      </Card>
      <Card className="workbench-card" title={t('listTitle')} extra={<Tag>{query.data?.meta.total_count ?? 0}</Tag>}>
        <Table<Memory>
          rowKey="memory_id"
          dataSource={query.data?.data ?? []}
          loading={query.isLoading}
          pagination={{
            current: page,
            pageSize,
            total: query.data?.meta.total_count ?? 0,
            showSizeChanger: false,
            onChange: setPage,
          }}
          rowClassName={(row) => (row.memory_id === selected?.memory_id ? 'selected-table-row' : '')}
          onRow={(row) => ({
            tabIndex: 0,
            role: 'button',
            'aria-label': t('viewMemory', { id: row.memory_id }),
            onClick: () => setSelected(row),
            onKeyDown: (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                setSelected(row)
              }
            },
          })}
          columns={[
            { title: t('colMemory'), dataIndex: 'memory', ellipsis: true },
            {
              title: t('colTopics'),
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
            { title: t('colUser'), dataIndex: 'user_id', width: 130, render: compactId },
            {
              title: t('colUpdated'),
              dataIndex: 'updated_at',
              width: 170,
              defaultSortOrder: 'descend' as const,
              sorter: (a: Memory, b: Memory) => compareTimestamp(a.updated_at, b.updated_at),
              render: formatDate,
            },
            {
              title: t('colActions'),
              key: 'actions',
              width: 88,
              render: (_, row) => (
                <Space size={2} onClick={(event) => event.stopPropagation()}>
                  <Tooltip title={t('common:edit')}>
                    <Button
                      aria-label={t('editNamed', { id: row.memory_id })}
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
                        aria-label={t('deleteNamed', { id: row.memory_id })}
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
        title={t('metadataTitle')}
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
                  editing.memory_id,
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
