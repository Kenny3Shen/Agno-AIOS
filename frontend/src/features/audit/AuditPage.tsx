import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Button,
  Card,
  DatePicker,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Grid,
  Input,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  type DescriptionsProps,
  type TableProps,
} from 'antd'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { CopyableValue } from '@/shared/ui/MetadataDescriptions'
import { JsonValueCard } from '@/shared/ui/FormattedContentCard'
import { compactId, useFormatDate } from '@/shared/lib/format'
import { auditKeys, getAuditLogs } from './api'
import type { AuditFilterValues, AuditLog, AuditLogQuery } from './types'
import { auditFormToQuery, auditStatusColor, hasAuditMetadata, initialAuditUserId } from './utils'
import { useTranslation } from 'react-i18next'

const { RangePicker } = DatePicker
const DEFAULT_LIMIT = 25

const statusOptions = [
  { label: 'success', value: 'success' },
  { label: 'failed', value: 'failed' },
  { label: 'error', value: 'error' },
  { label: 'denied', value: 'denied' },
]

const emptyFilters: AuditFilterValues = {
  actor_user_id: '',
  actor_email: '',
  action: '',
  resource_type: '',
  resource_id: '',
  status: undefined,
  ip_address: '',
  time_range: null,
}

function StatusTag({ status }: { status?: string }) {
  const value = status?.trim() || '-'
  return <Tag color={auditStatusColor(value)}>{value}</Tag>
}

function ResourceCell({ row }: { row: AuditLog }) {
  const resourceType = row.resource_type || '-'
  return (
    <Space orientation="vertical" size={0} className="audit-resource-cell">
      <Typography.Text>{resourceType}</Typography.Text>
      <Typography.Text type="secondary">{compactId(row.resource_id)}</Typography.Text>
    </Space>
  )
}

function ActorCell({ row }: { row: AuditLog }) {
  return (
    <Space orientation="vertical" size={0} className="audit-actor-cell">
      <Typography.Text ellipsis>{row.actor_email || '-'}</Typography.Text>
      <Typography.Text type="secondary">{compactId(row.actor_user_id)}</Typography.Text>
    </Space>
  )
}

function detailItems(row: AuditLog, formatDate: (value?: string | number | null) => string): DescriptionsProps['items'] {
  return [
    { key: 'id', label: 'ID', children: <CopyableValue value={String(row.id)} /> },
    { key: 'user', label: 'User ID', children: <CopyableValue value={row.actor_user_id} /> },
    { key: 'email', label: 'Email', children: row.actor_email || '-' },
    { key: 'role', label: 'Role', children: row.actor_role || '-' },
    { key: 'action', label: 'Action', children: row.action || '-' },
    { key: 'resource_type', label: 'Resource Type', children: row.resource_type || '-' },
    { key: 'resource_id', label: 'Resource ID', children: <CopyableValue value={row.resource_id} /> },
    { key: 'status', label: 'Status', children: <StatusTag status={row.status} /> },
    { key: 'ip', label: 'IP', children: row.ip_address || '-' },
    { key: 'user_agent', label: 'User Agent', children: row.user_agent || '-' },
    { key: 'created', label: 'Created At', children: formatDate(row.created_at) },
  ]
}

export function AuditPage() {
  const { t } = useTranslation('audit')
  const formatDate = useFormatDate()
  const screens = Grid.useBreakpoint()
  const [form] = Form.useForm<AuditFilterValues>()
  const initialUserId = useMemo(() => initialAuditUserId(), [])
  const [query, setQuery] = useState<AuditLogQuery>(() => ({
    page: 1,
    limit: DEFAULT_LIMIT,
    ...(initialUserId ? { actor_user_id: initialUserId } : {}),
  }))
  const [selected, setSelected] = useState<AuditLog | null>(null)
  const logsQuery = useQuery({ queryKey: auditKeys.list(query), queryFn: () => getAuditLogs(query) })

  const columns: TableProps<AuditLog>['columns'] = [
    { title: t('colTime'), dataIndex: 'created_at', width: 190, render: formatDate },
    { title: t('colActor'), key: 'actor', width: 240, render: (_, row) => <ActorCell row={row} /> },
    { title: t('colAction'), dataIndex: 'action', width: 190, render: (value: string) => <Typography.Text code>{value || '-'}</Typography.Text> },
    { title: t('colResource'), key: 'resource', width: 220, render: (_, row) => <ResourceCell row={row} /> },
    { title: t('colStatus'), dataIndex: 'status', width: 110, render: (value: string) => <StatusTag status={value} /> },
    { title: t('colIp'), dataIndex: 'ip_address', width: 140, render: (value: string) => value || '-' },
    {
      title: t('colMetadata'),
      dataIndex: 'metadata',
      width: 110,
      render: (value: unknown) => (hasAuditMetadata(value) ? <Tag color="processing">JSON</Tag> : '-'),
    },
  ]

  const applyFilters = (values: AuditFilterValues) => {
    setSelected(null)
    setQuery(auditFormToQuery(values, 1, query.limit ?? DEFAULT_LIMIT))
  }

  const resetFilters = () => {
    form.setFieldsValue(emptyFilters)
    setSelected(null)
    setQuery({ page: 1, limit: query.limit ?? DEFAULT_LIMIT })
  }

  return (
    <main className="page audit-page">
      <PageHeader title={t('title')} description={t('description')} />
      <Card className="workbench-card audit-filter-card">
        <Form<AuditFilterValues> form={form} layout="vertical" initialValues={{ actor_user_id: initialUserId }} onFinish={applyFilters}>
          <div className="audit-filter-grid">
            <Form.Item name="actor_user_id" label="User ID">
              <Input allowClear placeholder="user id" />
            </Form.Item>
            <Form.Item name="actor_email" label="Email">
              <Input allowClear placeholder="user@example.com" />
            </Form.Item>
            <Form.Item name="action" label="Action">
              <Input allowClear placeholder="auth.login" />
            </Form.Item>
            <Form.Item name="resource_type" label="Resource">
              <Input allowClear placeholder="knowledge" />
            </Form.Item>
            <Form.Item name="resource_id" label="Resource ID">
              <Input allowClear placeholder="resource id" />
            </Form.Item>
            <Form.Item name="status" label="Status">
              <Select allowClear options={statusOptions} placeholder="status" />
            </Form.Item>
            <Form.Item name="ip_address" label="IP">
              <Input allowClear placeholder="10.0.0.8" />
            </Form.Item>
            <Form.Item name="time_range" label="Time range">
              <RangePicker showTime className="audit-range-picker" />
            </Form.Item>
          </div>
          <Space wrap>
            <Button type="primary" htmlType="submit" icon={<SearchOutlined />}>
              {t('common:query')}
            </Button>
            <Button onClick={resetFilters}>{t('common:reset')}</Button>
            <Button icon={<ReloadOutlined />} loading={logsQuery.isFetching} onClick={() => void logsQuery.refetch()}>
              {t('common:refresh')}
            </Button>
          </Space>
        </Form>
      </Card>
      <Card className="workbench-card audit-table-card" title="Audit events" extra={<Tag>{logsQuery.data?.meta.total_count ?? 0}</Tag>}>
        <Table<AuditLog>
          rowKey={(row) => String(row.id)}
          size="small"
          loading={logsQuery.isLoading}
          dataSource={logsQuery.data?.data ?? []}
          columns={columns}
          scroll={{ x: 1200 }}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={false} /> }}
          pagination={{
            current: query.page ?? logsQuery.data?.meta.page ?? 1,
            pageSize: query.limit ?? logsQuery.data?.meta.limit ?? DEFAULT_LIMIT,
            total: logsQuery.data?.meta.total_count ?? 0,
            showSizeChanger: true,
            showTotal: (total) => `${total} events`,
          }}
          onChange={(pagination) => {
            setQuery((previous) => ({
              ...previous,
              page: pagination.current ?? 1,
              limit: pagination.pageSize ?? previous.limit ?? DEFAULT_LIMIT,
            }))
          }}
          rowClassName={(row) => (row.id === selected?.id ? 'selected-table-row' : '')}
          onRow={(row) => ({
            role: 'button',
            tabIndex: 0,
            onClick: () => setSelected(row),
            onKeyDown: (event) => {
              if (event.key === 'Enter' || event.key === ' ') setSelected(row)
            },
          })}
        />
      </Card>
      <Drawer
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title="Audit detail"
        size={screens.lg ? 720 : 'calc(100vw - 32px)'}
        destroyOnHidden
      >
        {selected ? (
          <div className="audit-drawer-stack">
            <Descriptions column={1} size="small" bordered items={detailItems(selected, formatDate)} />
            <JsonValueCard value={selected.metadata ?? {}} title="Metadata" />
          </div>
        ) : null}
      </Drawer>
    </main>
  )
}
