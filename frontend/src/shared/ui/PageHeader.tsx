import type { ReactNode } from 'react'
import { Space, Typography } from 'antd'

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <header className="page-header">
      <div className="page-header-copy">
        <Typography.Title level={3}>{title}</Typography.Title>
        {description && <Typography.Text type="secondary">{description}</Typography.Text>}
      </div>
      {actions && <Space wrap>{actions}</Space>}
    </header>
  )
}
