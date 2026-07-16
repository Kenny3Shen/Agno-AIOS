import { useMemo } from 'react'
import { Button, Card, Input, Popconfirm, Space, Table, Tag, Tooltip } from 'antd'
import { DeleteOutlined, EditOutlined } from '@ant-design/icons'
import type { ResourceVisibility } from '@/shared/types/common'
import { VisibilitySelect } from '@/shared/ui/VisibilitySelect'
import { compareTimestamp, useFormatDate } from '@/shared/lib/format'
import type { Document } from '../types'
import { useTranslation } from 'react-i18next'

export function DocumentsTable({
  documents,
  filter,
  loading,
  selectedId,
  vertical,
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
}: {
  documents: Document[]
  filter: string
  loading: boolean
  selectedId: string
  vertical: boolean
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
      extra={<Input.Search value={filter} onChange={(event) => onFilterChange(event.target.value)} allowClear placeholder={t('filterDocuments')} />}
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
        scroll={vertical ? { x: 1100 } : { x: 1100 }}
        rowClassName={(row) => (row.id === selectedId ? 'selected-table-row' : '')}
        onRow={(row) => ({ onClick: () => onSelect(row) })}
        columns={[
          {
            title: t('columns.title'),
            dataIndex: 'title',
            ellipsis: true,
            sorter: (a, b) => (a.title ?? '').localeCompare(b.title ?? ''),
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
            sorter: (a, b) => (a.chunks ?? 0) - (b.chunks ?? 0),
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
            sorter: (a, b) => compareTimestamp(a.created_at, b.created_at),
            render: (value?: string) => formatDate(value),
          },
          {
            title: t('columns.updated'),
            dataIndex: 'updated_at',
            width: 168,
            sorter: (a, b) => compareTimestamp(a.updated_at ?? a.created_at, b.updated_at ?? b.created_at),
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
