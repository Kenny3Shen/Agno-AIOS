/**
 * IP blacklist threat-intel library: search indicators and admin feed update.
 * Layout mirrors CVE page (workbench-card + toolbar + table).
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { App, Button, Card, Flex, Input, Progress, Select, Space, Table, Tag, Typography } from 'antd'
import { ReloadOutlined, SearchOutlined, StopOutlined } from '@ant-design/icons'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { currentUserQuery } from '@/features/auth'
import { roleOf } from '@/shared/auth/permissions'
import { PageHeader } from '@/shared/ui/PageHeader'
import { compareTimestamp, useFormatDate } from '@/shared/lib/format'
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

function formatUpdateMessage(
  event: IpBlacklistUpdateProgress | null,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (!event) return t('updateStarting')
  if (event.status === 'cancelled') return event.message || t('updateCancelled')
  if (event.status === 'failed') return event.error || event.message || t('updateFailed')
  const stage = event.stage || ''
  if (stage === 'start') return t('updateStarting')
  if (stage === 'source') {
    if (event.source) {
      if (event.status === 'completed') {
        return t('updateStageSourceDone', {
          source: event.source,
          add: event.add_count ?? 0,
          del: event.del_count ?? 0,
          index: event.source_index ?? 0,
          total: event.source_total ?? 0,
        })
      }
      return t('updateStageSource', {
        source: event.source,
        index: event.source_index ?? 0,
        total: event.source_total ?? 0,
      })
    }
    return t('updateStarting')
  }
  if (stage === 'done' && event.status === 'completed') {
    return t('updatedDetail', { add: event.add_count ?? 0, del: event.del_count ?? 0 })
  }
  return event.message || t('updateStarting')
}

export function IpBlacklistPage() {
  const { t } = useTranslation('ipBlacklist')
  const formatDate = useFormatDate()
  const { message } = App.useApp()
  const currentUser = useQuery(currentUserQuery())
  const canUpdate = roleOf(currentUser.data) === 'admin'
  const [query, setQuery] = useState('')
  const [source, setSource] = useState<string>()
  const debouncedQuery = useDebouncedValue(query, 300)
  const [pagination, setPagination] = useState({ page: 1, size: 20 })
  const [updateProgress, setUpdateProgress] = useState<IpBlacklistUpdateProgress | null>(null)
  const updateAbortRef = useRef<AbortController | null>(null)

  const listQuery = useQuery({
    queryKey: ['ip-blacklist', 'search', debouncedQuery, source, pagination.page, pagination.size],
    queryFn: () =>
      searchIpBlacklist({
        query: debouncedQuery.trim(),
        source,
        page: pagination.page,
        size: pagination.size,
      }),
  })

  useEffect(() => {
    if (listQuery.isError) {
      const err = listQuery.error
      message.error(err instanceof Error ? err.message : t('searchFailed'))
    }
  }, [listQuery.isError, listQuery.error, message, t])

  useEffect(() => {
    return () => {
      updateAbortRef.current?.abort()
    }
  }, [])

  const updateMutation = useMutation({
    mutationFn: async () => {
      updateAbortRef.current?.abort()
      const controller = new AbortController()
      updateAbortRef.current = controller
      setUpdateProgress({ stage: 'start', status: 'running', message: t('updateStarting') })
      try {
        await updateIpBlacklistStream((event) => {
          setUpdateProgress(event)
        }, controller.signal)
      } finally {
        if (updateAbortRef.current === controller) {
          updateAbortRef.current = null
        }
      }
    },
    onSuccess: () => {
      message.success(t('updated'))
      setUpdateProgress((prev) =>
        prev ? { ...prev, stage: 'done', status: 'completed' } : prev,
      )
      void listQuery.refetch()
    },
    onError: (error: Error) => {
      if (error.name === 'AbortError') {
        message.info(t('updateCancelled'))
        setUpdateProgress((prev) =>
          prev
            ? { ...prev, stage: 'done', status: 'cancelled', message: t('updateCancelled') }
            : { stage: 'done', status: 'cancelled', message: t('updateCancelled') },
        )
        void listQuery.refetch()
        return
      }
      message.error(error.message || t('updateFailed'))
      setUpdateProgress((prev) =>
        prev
          ? { ...prev, stage: 'done', status: 'failed', error: error.message }
          : { stage: 'done', status: 'failed', error: error.message },
      )
    },
  })

  const updating = updateMutation.isPending
  const percent = progressPercent(updateProgress)

  const columns: ColumnsType<IpBlacklistEntry> = useMemo(
    () => [
      {
        title: t('columns.indicator'),
        dataIndex: 'indicator',
        key: 'indicator',
        width: 200,
        render: (value: string, row) => (
          <Flex vertical gap={4}>
            <Typography.Text code copyable={{ text: value }}>
              {value}
            </Typography.Text>
            <Tag style={{ width: 'fit-content', marginInlineEnd: 0 }}>{row.indicator_type}</Tag>
          </Flex>
        ),
      },
      {
        title: t('columns.source'),
        dataIndex: 'source',
        key: 'source',
        width: 140,
        render: (value: string) => <Tag color="blue">{value}</Tag>,
      },
      {
        title: t('columns.listName'),
        dataIndex: 'list_name',
        key: 'list_name',
        width: 140,
        ellipsis: true,
        render: (value: string) => value || '—',
      },
      {
        title: t('columns.description'),
        dataIndex: 'description',
        key: 'description',
        ellipsis: true,
        render: (value: string) => value || '—',
      },
      {
        title: t('columns.updatedAt'),
        dataIndex: 'updated_at',
        key: 'updated_at',
        width: 190,
        defaultSortOrder: 'descend',
        sorter: (a, b) => compareTimestamp(a.updated_at, b.updated_at),
        render: (value: string | null | undefined) => (value ? formatDate(value) : '—'),
      },
    ],
    [formatDate, t],
  )

  const onTableChange = (next: TablePaginationConfig) => {
    setPagination({
      page: next.current ?? 1,
      size: next.pageSize ?? pagination.size,
    })
  }

  return (
    <main className="page">
      <PageHeader title={t('title')} description={t('description')} />
      <Card className="workbench-card">
        <Space className="cve-toolbar" wrap>
          <Space.Compact className="cve-search-control">
            <Input
              allowClear
              value={query}
              placeholder={t('searchPlaceholder')}
              onChange={(event) => {
                setQuery(event.target.value)
                setPagination((prev) => ({ ...prev, page: 1 }))
              }}
              onPressEnter={() => {
                setPagination((prev) => ({ ...prev, page: 1 }))
                void listQuery.refetch()
              }}
            />
            <Button
              type="primary"
              icon={<SearchOutlined />}
              loading={listQuery.isFetching}
              onClick={() => {
                setPagination((prev) => ({ ...prev, page: 1 }))
                void listQuery.refetch()
              }}
            >
              {t('common:search')}
            </Button>
          </Space.Compact>
          <Select
            allowClear
            value={source}
            onChange={(value) => {
              setSource(value)
              setPagination((prev) => ({ ...prev, page: 1 }))
            }}
            placeholder={t('allSources')}
            options={[{ value: 'firehol-level1', label: 'FireHOL level1' }]}
            style={{ minWidth: 160 }}
          />
          {updating && canUpdate ? (
            <Button
              danger
              icon={<StopOutlined />}
              title={t('stopUpdateHint')}
              onClick={() => updateAbortRef.current?.abort()}
            >
              {t('stopUpdate')}
            </Button>
          ) : (
            <Button
              icon={<ReloadOutlined />}
              loading={updating}
              disabled={!canUpdate || updating}
              onClick={() => updateMutation.mutate()}
            >
              {t('updateDatabase')}
            </Button>
          )}
        </Space>

        {updateProgress ? (
          <div style={{ marginTop: 12, maxWidth: 640 }}>
            <Progress
              percent={percent}
              size="small"
              status={
                updateProgress.status === 'failed'
                  ? 'exception'
                  : updateProgress.status === 'cancelled'
                    ? 'normal'
                    : updateProgress.status === 'completed' && updateProgress.stage === 'done'
                      ? 'success'
                      : updating
                        ? 'active'
                        : 'normal'
              }
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {formatUpdateMessage(updateProgress, t)}
            </Typography.Text>
          </div>
        ) : null}

        <Table<IpBlacklistEntry>
          rowKey="id"
          style={{ marginTop: 12 }}
          loading={listQuery.isFetching}
          dataSource={listQuery.data?.data ?? []}
          columns={columns}
          locale={{
            emptyText: listQuery.isFetching ? t('loading') : t('noResults'),
          }}
          pagination={{
            current: pagination.page,
            pageSize: pagination.size,
            total: listQuery.data?.meta.total_count ?? 0,
            showSizeChanger: true,
            showTotal: (total) => t('total', { total }),
          }}
          onChange={onTableChange}
          scroll={{ x: 900 }}
        />
      </Card>
    </main>
  )
}
