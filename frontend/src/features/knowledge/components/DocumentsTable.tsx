import { useMemo } from 'react'
import { Button, Card, Input, Popconfirm, Space, Table, Tag, Tooltip } from 'antd'
import { DeleteOutlined, EditOutlined } from '@ant-design/icons'
import type { ResourceVisibility } from '@/shared/types/common'
import { VisibilitySelect } from '@/shared/ui/VisibilitySelect'
import { useFormatDate } from '@/shared/lib/format'
import type { Document } from '../types'
import { useTranslation } from 'react-i18next'

export function DocumentsTable({
  documents,
  filter,
  loading,
  selectedId,
  onFilterChange,
  onSelect,
  onUpdate,
  onDelete,
  onVisibilityChange,
  deletingId,
  paginationTotal = 0,
  paginationPage = 1,
  paginationPageSize = 12,
  onPaginationChange,
  sortBy = 'updated_at',
  sortOrder = 'desc',
  onSortChange,
}: {
  documents: Document[]
  filter: string
  loading: boolean
  selectedId: string
  onFilterChange: (value: string) => void
  onSelect: (document: Document) => void
  onUpdate: (document: Document) => void
  onDelete: (document: Document) => void
  onVisibilityChange: (document: Document, visibility: ResourceVisibility) => void
  deletingId?: string
  paginationTotal?: number
  paginationPage?: number
  paginationPageSize?: number
  onPaginationChange?: (page: number) => void
  sortBy?: 'updated_at' | 'created_at' | 'name' | 'status'
  sortOrder?: 'asc' | 'desc'
  onSortChange?: (
    sortBy: 'updated_at' | 'created_at' | 'name' | 'status',
    sortOrder: 'asc' | 'desc'
  ) => void
}) {
  const { t } = useTranslation('knowledge')
  const formatDate = useFormatDate()
  const sourceFilters = useMemo(() => {
    const values = Array.from(
      new Set(documents.map((document) => (document.source || '').trim()).filter(Boolean))
    ).sort((a, b) => a.localeCompare(b))
    return values.map((value) => ({ text: value, value }))
  }, [documents])

  return (
    <Card
      className="workbench-card splitter-panel-card"
      title={t('documents')}
      extra={
        <Input.Search
          value={filter}
          allowClear
          placeholder={t('filterDocuments')}
          onChange={(event) => onFilterChange(event.target.value)}
          onSearch={(value) => onFilterChange(value)}
        />
      }
    >
      <Table<Document>
        rowKey="id"
        dataSource={documents}
        loading={loading}
        pagination={{
          current: paginationPage,
          pageSize: paginationPageSize,
          total: paginationTotal,
          showSizeChanger: false,
          onChange: (nextPage) => onPaginationChange?.(nextPage),
        }}
        onChange={(_pagination, _filters, sorter) => {
          if (!onSortChange) return
          const active = Array.isArray(sorter) ? sorter[0] : sorter
          if (!active || !active.order) return
          const field = String(active.field || active.columnKey || '')
          const mapped =
            field === 'title'
              ? 'name'
              : field === 'created_at'
                ? 'created_at'
                : field === 'updated_at'
                  ? 'updated_at'
                  : field === 'status'
                    ? 'status'
                    : null
          if (!mapped) return
          onSortChange(mapped, active.order === 'ascend' ? 'asc' : 'desc')
        }}
        scroll={{ x: 1100 }}
        rowClassName={(row) => (row.id === selectedId ? 'selected-table-row' : '')}
        onRow={(row) => ({ onClick: () => onSelect(row) })}
        columns={[
          {
            title: t('columns.title'),
            dataIndex: 'title',
            ellipsis: true,
            sorter: true,
            sortOrder: sortBy === 'name' ? (sortOrder === 'asc' ? 'ascend' : 'descend') : null,
          },
          {
            title: t('columns.source'),
            dataIndex: 'source',
            width: 140,
            ellipsis: true,
            filters: sourceFilters,
            onFilter: (value, row) => (row.source || '') === value,
            render: (value?: string) => (value ? <Tag>{value}</Tag> : '-'),
          },
          {
            title: t('columns.chunks'),
            dataIndex: 'chunks',
            width: 96,
            onHeaderCell: () => ({ style: { whiteSpace: 'nowrap' } }),
          },
          {
            title: t('columns.status'),
            dataIndex: 'status',
            width: 110,
            filters: [
              { text: 'ready', value: 'ready' },
              { text: 'completed', value: 'completed' },
              { text: 'processing', value: 'processing' },
            ],
            onFilter: (value, row) => (row.status ?? 'ready') === value,
            render: (value) => <Tag color={value === 'ready' || value === 'completed' ? 'success' : 'processing'}>{value ?? 'ready'}</Tag>,
          },
          {
            title: t('columns.created'),
            dataIndex: 'created_at',
            width: 168,
            sorter: true,
            sortOrder: sortBy === 'created_at' ? (sortOrder === 'asc' ? 'ascend' : 'descend') : null,
            render: (value?: string) => formatDate(value),
          },
          {
            title: t('columns.updated'),
            dataIndex: 'updated_at',
            width: 168,
            sorter: true,
            sortOrder: sortBy === 'updated_at' ? (sortOrder === 'asc' ? 'ascend' : 'descend') : null,
            render: (_value, row) => formatDate(row.updated_at || row.created_at),
          },
          {
            title: t('columns.visibility'),
            dataIndex: 'visibility',
            width: 130,
            render: (value, row) => (
              <VisibilitySelect
                size="small"
                value={value ?? 'private'}
                disabled={!row.can_manage}
                onClick={(event) => event.stopPropagation()}
                onChange={(visibility) => onVisibilityChange(row, visibility)}
              />
            ),
          },
          {
            title: t('columns.actions'),
            key: 'actions',
            width: 96,
            render: (_, row) =>
              row.can_manage ? (
                <Space size={2} onClick={(event) => event.stopPropagation()}>
                  <Tooltip title={t('update')}>
                    <Button
                      aria-label={t('updateNamed', { title: row.title })}
                      type="text"
                      size="small"
                      icon={<EditOutlined />}
                      onClick={(event) => {
                        event.stopPropagation()
                        onUpdate(row)
                      }}
                    />
                  </Tooltip>
                  <Tooltip title={t('common:delete')}>
                    <Popconfirm
                      title={t('deleteConfirm')}
                      onConfirm={(event) => {
                        event?.stopPropagation()
                        onDelete(row)
                      }}
                    >
                      <Button
                        aria-label={t('deleteNamed', { title: row.title })}
                        danger
                        type="text"
                        size="small"
                        icon={<DeleteOutlined />}
                        loading={deletingId === row.id}
                        onClick={(event) => event.stopPropagation()}
                      />
                    </Popconfirm>
                  </Tooltip>
                </Space>
              ) : null,
          },
        ]}
      />
    </Card>
  )
}
