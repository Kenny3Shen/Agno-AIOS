import { Card, Input, Table, Tag } from 'antd'
import type { ResourceVisibility } from '@/shared/types/common'
import { VisibilitySelect } from '@/shared/ui/VisibilitySelect'
import type { Document } from '../types'

export function DocumentsTable({
  documents,
  filter,
  loading,
  selectedId,
  vertical,
  onFilterChange,
  onSelect,
  onVisibilityChange,
}: {
  documents: Document[]
  filter: string
  loading: boolean
  selectedId: string
  vertical: boolean
  onFilterChange: (value: string) => void
  onSelect: (document: Document) => void
  onVisibilityChange: (document: Document, visibility: ResourceVisibility) => void
}) {
  return <Card className="workbench-card splitter-panel-card" title="Documents" extra={<Input.Search value={filter} onChange={(event) => onFilterChange(event.target.value)} allowClear placeholder="筛选文档" />}>
    <Table<Document>
      rowKey="id"
      dataSource={documents}
      loading={loading}
      pagination={{ pageSize: 12 }}
      scroll={vertical ? { x: 680 } : undefined}
      rowClassName={(row) => row.id === selectedId ? 'selected-table-row' : ''}
      onRow={(row) => ({ onClick: () => onSelect(row) })}
      columns={[
        { title: 'Title', dataIndex: 'title', ellipsis: true },
        { title: 'Chunks', dataIndex: 'chunks', width: 96, onHeaderCell: () => ({ style: { whiteSpace: 'nowrap' } }) },
        { title: 'Status', dataIndex: 'status', width: 110, render: (value) => <Tag color={value === 'ready' || value === 'completed' ? 'success' : 'processing'}>{value ?? 'ready'}</Tag> },
        { title: 'Visibility', dataIndex: 'visibility', width: 130, render: (value, row) => <VisibilitySelect size="small" value={value ?? 'private'} disabled={!row.can_manage} onClick={(event) => event.stopPropagation()} onChange={(visibility) => onVisibilityChange(row, visibility)} /> },
      ]}
    />
  </Card>
}
