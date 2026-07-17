/**
 * CVE intelligence library: search, source filter, admin DB update stream.
 * Supports Collect deep-links via ``?q=CVE-…``.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useRouterState } from '@tanstack/react-router'
import { useMutation, useQuery } from '@tanstack/react-query'
import { App, Button, Card, Input, Progress, Select, Space, Table, Tag, Typography } from 'antd'
import { ReloadOutlined, SearchOutlined, StopOutlined } from '@ant-design/icons'
import { currentUserQuery } from '@/features/auth'
import { roleOf } from '@/shared/auth/permissions'
import { PageHeader } from '@/shared/ui/PageHeader'
import {
  searchCves,
  updateCvesStream,
  type Cve,
  type CveUpdateProgress,
} from './api'
import { compareTimestamp, useFormatDate } from '@/shared/lib/format'
import { useTranslation } from 'react-i18next'
import { useDebouncedValue } from '@/shared/lib/useDebouncedValue'

function progressPercent(event: CveUpdateProgress | null): number {
  if (!event) return 0
  if (event.stage === 'done' && event.status === 'completed') return 100
  if (event.stage === 'database' || event.stage === 'cache') return 80
  if (event.stage === 'source' && event.source_total) {
    const index = Math.max(0, Number(event.source_index || 0))
    const total = Math.max(1, Number(event.source_total || 1))
    const base = event.status === 'completed' ? index : Math.max(0, index - 1)
    return Math.min(70, Math.round((base / total) * 70) + 10)
  }
  if (event.stage === 'start') return 5
  return 15
}

function formatCveProgressMessage(
  event: CveUpdateProgress | null,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (!event) return t('updateStarting')
  if (event.status === 'cancelled') {
    return event.message || t('updateCancelled')
  }
  if (event.status === 'failed') {
    return event.error || event.message || t('updateFailed')
  }
  const stage = event.stage || ''
  if (stage === 'start') return t('updateStageStart')
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
  if (stage === 'database') {
    return t('updateStageDatabase', {
      add: event.pending_add ?? event.add_count ?? 0,
      del: event.pending_del ?? event.del_count ?? 0,
    })
  }
  if (stage === 'cache') return t('updateStageCache')
  if (stage === 'done' && event.status === 'completed') {
    return t('updatedDetail', { add: event.add_count ?? 0, del: event.del_count ?? 0 })
  }
  return event.message || t('updateStarting')
}

export function CvePage() {
  const { t } = useTranslation('cve')
  const formatDate = useFormatDate()
  const { message } = App.useApp()
  const searchStr = useRouterState({ select: (state) => state.location.searchStr })
  const initialQuery = useMemo(() => {
    try {
      return (new URLSearchParams(searchStr).get('q') || '').trim()
    } catch {
      return ''
    }
  }, [searchStr])
  const currentUser = useQuery(currentUserQuery())
  const canUpdateDatabase = roleOf(currentUser.data) === 'admin'
  const [query, setQuery] = useState(initialQuery)
  const [source, setSource] = useState<string>()
  const [pagination, setPagination] = useState({ page: 1, size: 20 })
  const [updateProgress, setUpdateProgress] = useState<CveUpdateProgress | null>(null)
  const updateAbortRef = useRef<AbortController | null>(null)
  // Deep-link from Collect CVE tags (/cve?q=CVE-…) keeps search box in sync.
  useEffect(() => {
    if (initialQuery) {
      setQuery(initialQuery)
      setPagination((prev) => ({ ...prev, page: 1 }))
    }
  }, [initialQuery])
  const debouncedQuery = useDebouncedValue(query, 300)

  const search = useQuery({
    queryKey: ['cve', 'search', debouncedQuery, source, pagination.page, pagination.size],
    queryFn: () =>
      searchCves({
        query: debouncedQuery,
        source,
        page: pagination.page,
        size: pagination.size,
      }),
  })

  useEffect(() => {
    if (search.isError) {
      const err = search.error
      message.error(err instanceof Error ? err.message : t('searchFailed'))
    }
  }, [search.isError, search.error, message, t])

  useEffect(() => {
    return () => {
      updateAbortRef.current?.abort()
    }
  }, [])

  const update = useMutation({
    mutationFn: async () => {
      updateAbortRef.current?.abort()
      const controller = new AbortController()
      updateAbortRef.current = controller
      setUpdateProgress({ stage: 'start', status: 'running', message: t('updateStarting') })
      try {
        return await updateCvesStream((event) => {
          setUpdateProgress(event)
        }, controller.signal)
      } finally {
        if (updateAbortRef.current === controller) {
          updateAbortRef.current = null
        }
      }
    },
    onSuccess: (data) => {
      message.success(
        t('updatedDetail', {
          add: data.add_count ?? 0,
          del: data.del_count ?? 0,
        }),
      )
      setUpdateProgress((prev) =>
        prev
          ? {
              ...prev,
              stage: 'done',
              status: 'completed',
              add_count: data.add_count,
              del_count: data.del_count,
            }
          : prev,
      )
      void search.refetch()
    },
    onError: (error) => {
      if (error instanceof Error && error.name === 'AbortError') {
        message.info(t('updateCancelled'))
        setUpdateProgress((prev) =>
          prev
            ? { ...prev, stage: 'done', status: 'cancelled', message: t('updateCancelled') }
            : { stage: 'done', status: 'cancelled', message: t('updateCancelled') },
        )
        void search.refetch()
        return
      }
      message.error(error instanceof Error ? error.message : t('updateFailed'))
      setUpdateProgress((prev) =>
        prev
          ? { ...prev, stage: 'done', status: 'failed', message: error instanceof Error ? error.message : t('updateFailed') }
          : { stage: 'done', status: 'failed', message: t('updateFailed') },
      )
    },
  })

  const stopUpdate = () => {
    updateAbortRef.current?.abort()
  }

  const percent = progressPercent(updateProgress)
  const updating = update.isPending

  return (
    <main className="page">
      <PageHeader title={t('title')} description={t('description')} />
      <Card className="workbench-card">
        <Space className="cve-toolbar" wrap>
          <Space.Compact className="cve-search-control">
            <Input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value)
                setPagination((prev) => ({ ...prev, page: 1 }))
              }}
              onPressEnter={() => setPagination((prev) => ({ ...prev, page: 1 }))}
              placeholder={t('searchPlaceholder')}
              allowClear
            />
            <Button
              type="primary"
              icon={<SearchOutlined />}
              loading={search.isFetching}
              onClick={() => {
                setPagination((prev) => ({ ...prev, page: 1 }))
                void search.refetch()
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
            options={[
              { value: 'github', label: 'GitHub' },
              { value: 'exploit-db', label: 'Exploit-DB' },
            ]}
          />
          {updating && canUpdateDatabase ? (
            <Button danger icon={<StopOutlined />} title={t('updateStopHint')} onClick={stopUpdate}>
              {t('updateStop')}
            </Button>
          ) : (
            <Button
              icon={<ReloadOutlined />}
              loading={updating}
              disabled={!canUpdateDatabase || updating}
              onClick={() => update.mutate()}
            >
              {t('updateDb')}
            </Button>
          )}
        </Space>

        {updateProgress ? (
          <div style={{ marginTop: 12, maxWidth: 640 }}>
            <Progress
              percent={percent}
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
              size="small"
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {formatCveProgressMessage(updateProgress, t)}
            </Typography.Text>
          </div>
        ) : null}

        <Table<Cve>
          rowKey="id"
          dataSource={search.data?.data ?? []}
          loading={search.isFetching}
          locale={{ emptyText: search.isFetching ? t('loading') : t('noResults') }}
          pagination={{
            current: pagination.page,
            pageSize: pagination.size,
            total: search.data?.meta.total_count,
            showSizeChanger: true,
            showTotal: (total) => t('total', { total }),
          }}
          onChange={(next) =>
            setPagination({
              page: next.current ?? 1,
              size: next.pageSize ?? pagination.size,
            })
          }
          style={{ marginTop: 12 }}
          expandable={{ expandedRowRender: (row) => <p>{row.description}</p> }}
          columns={[
            {
              title: t('colCve'),
              dataIndex: 'cve_id',
              width: 150,
              render: (value, row) => (
                <a href={row.github_url} target="_blank" rel="noreferrer">
                  {value}
                </a>
              ),
            },
            { title: t('colDescription'), dataIndex: 'description', ellipsis: true },
            {
              title: t('colSource'),
              dataIndex: 'source',
              width: 130,
              render: (value) => <Tag>{value}</Tag>,
            },
            {
              title: t('colIndexed'),
              dataIndex: 'create_time',
              width: 190,
              defaultSortOrder: 'descend' as const,
              sorter: (a, b) => compareTimestamp(a.create_time, b.create_time),
              render: (value) => formatDate(value),
            },
          ]}
        />
      </Card>
    </main>
  )
}
