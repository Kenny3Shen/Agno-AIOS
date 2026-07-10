import { Button, Card, Popconfirm, Space, Typography } from 'antd'
import { DeleteOutlined, EditOutlined, SyncOutlined } from '@ant-design/icons'
import { CopyableValue, MetadataDescriptions } from '@/shared/ui/MetadataDescriptions'
import { formatDate } from '@/shared/lib/format'
import type { Document } from '../types'

export function MetadataPanel({
  document,
  rebuilding,
  deleting,
  onUpdate,
  onRebuild,
  onDelete,
}: {
  document: Document | null
  rebuilding: boolean
  deleting: boolean
  onUpdate: () => void
  onRebuild: () => void
  onDelete: () => void
}) {
  const metadata = Object.fromEntries(Object.entries(document?.metadata ?? {}).filter(([key]) => !['title', 'source', 'owner_user_id', 'user_id', 'file_path'].includes(key)))
  const actions = document?.can_manage ? <Space className="knowledge-document-actions" size={4}>
    <Button size="small" icon={<EditOutlined />} onClick={onUpdate}>更新</Button>
    <Button size="small" icon={<SyncOutlined />} loading={rebuilding} onClick={onRebuild}>重建</Button>
    <Popconfirm title="删除该文档？" onConfirm={onDelete}>
      <Button size="small" danger icon={<DeleteOutlined />} loading={deleting}>删除</Button>
    </Popconfirm>
  </Space> : undefined

  return <Card className="workbench-card splitter-panel-card" title="Metadata" extra={actions}>
    {document ? <MetadataDescriptions items={[
      { key: 'title', label: 'Title', children: <Typography.Text strong>{document.title}</Typography.Text> },
      { key: 'id', label: 'ID', children: <CopyableValue value={document.id} /> },
      { key: 'source', label: 'Source', children: document.source || '-' },
      { key: 'created', label: 'Created', children: formatDate(document.created_at) },
      { key: 'owner', label: 'Owner', children: <CopyableValue value={document.owner_user_id} /> },
    ]} value={metadata} /> : <div className="empty-panel">选择文档查看元数据</div>}
  </Card>
}
