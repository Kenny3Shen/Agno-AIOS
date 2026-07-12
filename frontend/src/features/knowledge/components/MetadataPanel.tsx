import { Card, Typography } from 'antd'
import { CopyableValue, MetadataDescriptions } from '@/shared/ui/MetadataDescriptions'
import { formatDate } from '@/shared/lib/format'
import type { Document } from '../types'

export function MetadataPanel({ document }: { document: Document | null }) {
  const metadata = Object.fromEntries(
    Object.entries(document?.metadata ?? {}).filter(([key]) => !['title', 'source', 'owner_user_id', 'user_id', 'file_path'].includes(key))
  )

  return (
    <Card className="workbench-card splitter-panel-card" title="Metadata">
      {document ? (
        <MetadataDescriptions
          items={[
            { key: 'title', label: 'Title', children: <Typography.Text strong>{document.title}</Typography.Text> },
            { key: 'id', label: 'ID', children: <CopyableValue value={document.id} /> },
            { key: 'source', label: 'Source', children: document.source || '-' },
            { key: 'created', label: 'Created', children: formatDate(document.created_at) },
            { key: 'owner', label: 'Owner', children: <CopyableValue value={document.owner_user_id} /> },
          ]}
          value={metadata}
        />
      ) : (
        <div className="empty-panel">选择文档查看元数据</div>
      )}
    </Card>
  )
}
