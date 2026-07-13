import { Button, Card, Input, Popconfirm, Space, Table, Tag, Tooltip } from 'antd'
import { DeleteOutlined, EditOutlined } from '@ant-design/icons'
import type { ResourceVisibility } from '@/shared/types/common'
import { VisibilitySelect } from '@/shared/ui/VisibilitySelect'
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
}) {
  const { t } = useTranslation('knowledge')
  return (
    <Card
      className="workbench-card splitter-panel-card"
      title="Documents"
      extra={<Input.Search value={filter} onChange={(event) => onFilterChange(event.target.value)} allowClear placeholder={t('filterDocuments')} />}
    >
      <Table<Document>
        rowKey="id"
        dataSource={documents}
        loading={loading}
        pagination={{ pageSize: 12 }}
        scroll={vertical ? { x: 680 } : undefined}
        rowClassName={(row) => (row.id === selectedId ? 'selected-table-row' : '')}
        onRow={(row) => ({ onClick: () => onSelect(row) })}
        columns={[
          { title: 'Title', dataIndex: 'title', ellipsis: true, sorter: (a, b) => (a.title ?? '').localeCompare(b.title ?? '') },
          { title: 'Chunks', dataIndex: 'chunks', width: 96, sorter: (a, b) => (a.chunks ?? 0) - (b.chunks ?? 0), onHeaderCell: () => ({ style: { whiteSpace: 'nowrap' } }) },
          {
            title: 'Status',
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
            title: 'Visibility',
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
            title: 'Actions',
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
