/**
 * IP blacklist threat-intel library: search indicators and admin feed update.
 */
import { useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { App, Button, Card, Input, Progress, Space, Table, Tag, Typography } from 'antd'
import { ReloadOutlined, SearchOutlined, StopOutlined } from '@ant-design/icons'
import { currentUserQuery } from '@/features/auth'
import { roleOf } from '@/shared/auth/permissions'
import { PageHeader } from '@/shared/ui/PageHeader'
import { useFormatDate } from '@/shared/lib/format'
import { useDebouncedValue } from '@/shared/lib/useDebouncedValue'
import { useTranslation } from 'react-i18next'
import {
  searchIpBlacklist,
  updateIpBlacklistStream,
  type IpBlacklistEntry,
  type IpBlacklistUpdateProgress,
} from './api'

function progressPercent(event: IpBlacklistUpdateProgress | null): number {
  if (!event) return 0
  if (event.stage === 'done' && event.status === 'completed') return 100
  if (event.stage === 'source' && event.source_total) {
    const index = Math.max(0, Number(event.source_index || 0))
    const total = Math.max(1, Number(event.source_total || 1))
    const base = event.status === 'completed' ? index : Math.max(0, index - 1)
    return Math.min(90, Math.round((base / total) * 80) + 10)
  }
  if (event.stage === 'start') return 5
  return 15
}

export function IpBlacklistPage() {
  const { t } = useTranslation('ipBlacklist')
  const formatDate = useFormatDate()
  const { message } = App.useApp()
  const currentUser = useQuery(currentUserQuery())
  const canUpdate = roleOf(currentUser.data) === 'admin'
  const [query, setQuery] = useState('')
  const debouncedQuery = useDebouncedValue(query, 300)
  const [pagination, setPagination] = useState({ page: 1, size: 20 })
  const [updateProgress, setUpdateProgress] = useState<IpBlacklistUpdateProgress | null>(null)
  const updateAbortRef = useRef<AbortController | null>(null)

  const listQuery = useQuery({
    queryKey: ['ip-blacklist', 'search', debouncedQuery, pagination.page, pagination.size],
    queryFn: () =>
      searchIpBlacklist({
        query: debouncedQuery.trim(),
        page: pagination.page,
        size: pagination.size,
      }),
  })

  const updateMutation = useMutation({
    mutationFn: async () => {
      const controller = new AbortController()
      updateAbortRef.current = controller
      setUpdateProgress({ stage: 'start', status: 'running' })
      await updateIpBlacklistStream((event) => {
        setUpdateProgress(event)
      }, controller.signal)
    },
    onSuccess: () => {
      message.success(t('updated'))
      void listQuery.refetch()
    },
    onError: (error: Error) => {
      if (error.name === 'AbortError') {
        message.info(t('updateCancelled'))
        return
      }
      message.error(error.message || t('updateFailed'))
    },
    onSettled: () => {
      updateAbortRef.current = null
    },
  })

  const columns = [
    {
      title: t('columns.indicator'),
      dataIndex: 'indicator',
      key: 'indicator',
      render: (value: string, row: IpBlacklistEntry) => (
        <Space direction="vertical" size={0}>
          <Typography.Text code>{value}</Typography.Text>
          <Tag>{row.indicator_type}</Tag>
        </Space>
      ),
    },
    {
      title: t('columns.source'),
      dataIndex: 'source',
      key: 'source',
      width: 160,
    },
    {
      title: t('columns.listName'),
      dataIndex: 'list_name',
      key: 'list_name',
      ellipsis: true,
    },
    {
      title: t('columns.description'),
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: t('columns.updatedAt'),
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (value: string | null | undefined) =>
        value ? formatDate(value) : t('common:empty'),
    },
  ]

  return (
    <div className="page-stack">
      <PageHeader
        title={t('title')}
        description={t('description')}
        actions={
          canUpdate ? (
            <Space>
              {updateMutation.isPending ? (
                <Button
                  icon={<StopOutlined />}
                  onClick={() => updateAbortRef.current?.abort()}
                >
                  {t('stopUpdate')}
                </Button>
              ) : null}
              <Button
                type="primary"
                icon={<ReloadOutlined />}
                loading={updateMutation.isPending}
                onClick={() => updateMutation.mutate()}
              >
                {t('updateDatabase')}
              </Button>
            </Space>
          ) : null
        }
      />

      {updateMutation.isPending || updateProgress ? (
        <Card size="small" className="page-card">
          <Typography.Text type="secondary">
            {updateProgress?.message ||
              (updateProgress?.status === 'failed'
                ? updateProgress.error || t('updateFailed')
                : t('updateStarting'))}
          </Typography.Text>
          <Progress
            percent={progressPercent(updateProgress)}
            status={
              updateProgress?.status === 'failed'
                ? 'exception'
                : updateProgress?.stage === 'done'
                  ? 'success'
                  : 'active'
            }
            style={{ marginTop: 8 }}
          />
        </Card>
      ) : null}

      <Card size="small" className="page-card">
        <Space wrap style={{ marginBottom: 16 }}>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder={t('searchPlaceholder')}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value)
              setPagination((current) => ({ ...current, page: 1 }))
            }}
            style={{ width: 320 }}
          />
        </Space>
        <Table<IpBlacklistEntry>
          rowKey="id"
          loading={listQuery.isFetching}
          dataSource={listQuery.data?.data ?? []}
          columns={columns}
          pagination={{
            current: pagination.page,
            pageSize: pagination.size,
            total: listQuery.data?.meta.total_count ?? 0,
            showSizeChanger: true,
            onChange: (page, size) => setPagination({ page, size }),
          }}
        />
      </Card>
    </div>
  )
}
