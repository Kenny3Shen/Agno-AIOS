import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { App, Button, Card, Input, Select, Space, Table, Tag } from 'antd'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { currentUserQuery } from '@/features/auth'
import { roleOf } from '@/shared/auth/permissions'
import { PageHeader } from '@/shared/ui/PageHeader'
import { searchCves, updateCves, type Cve } from './api'
import { compareTimestamp, useFormatDate } from '@/shared/lib/format'
import { useTranslation } from 'react-i18next'

export function CvePage() {
  const { t } = useTranslation('cve')
  const formatDate = useFormatDate()
  const { message } = App.useApp()
  const currentUser = useQuery(currentUserQuery())
  const canUpdateDatabase = roleOf(currentUser.data) === 'admin'
  const [query, setQuery] = useState('')
  const [source, setSource] = useState<string>()
  const [pagination, setPagination] = useState({ page: 1, size: 20 })
  const search = useMutation({
    mutationFn: searchCves,
    onError: (error) =>
      message.error(error instanceof Error ? error.message : t('searchFailed')),
  })
  const update = useMutation({
    mutationFn: updateCves,
    onSuccess: () => message.success(t('updated')),
    onError: (error) =>
      message.error(error instanceof Error ? error.message : t('updateFailed')),
  })
  const runSearch = (page = 1, size = pagination.size) => {
    setPagination({ page, size })
    search.mutate({ query, source, page, size })
  }
  return (
    <main className="page">
      <PageHeader title={t('title')} description={t('description')} />
      <Card className="workbench-card">
        <Space className="cve-toolbar" wrap>
          <Space.Compact className="cve-search-control">
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onPressEnter={() => runSearch()}
              placeholder={t('searchPlaceholder')}
            />
            <Button type="primary" icon={<SearchOutlined />} loading={search.isPending} onClick={() => runSearch()}>
              {t('common:search')}
            </Button>
          </Space.Compact>
          <Select
            allowClear
            value={source}
            onChange={setSource}
            placeholder={t('allSources')}
            options={[
              { value: 'github', label: 'GitHub' },
              { value: 'exploit-db', label: 'Exploit-DB' },
            ]}
          />
          <Button icon={<ReloadOutlined />} loading={update.isPending} disabled={!canUpdateDatabase} onClick={() => update.mutate()}>
            {t('updateDb')}
          </Button>
        </Space>
        <Table<Cve>
          rowKey="id"
          dataSource={search.data?.data ?? []}
          loading={search.isPending}
          pagination={{
            current: pagination.page,
            pageSize: pagination.size,
            total: search.data?.meta.total_count,
            showSizeChanger: true,
            showTotal: (total) => t('total', { total }),
          }}
          onChange={(next) => runSearch(next.current ?? 1, next.pageSize ?? pagination.size)}
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
            { title: t('colSource'), dataIndex: 'source', width: 130, render: (value) => <Tag>{value}</Tag> },
            { title: t('colIndexed'), dataIndex: 'create_time', width: 190, defaultSortOrder: 'descend' as const, sorter: (a, b) => compareTimestamp(a.create_time, b.create_time), render: (value) => formatDate(value) },
          ]}
        />
      </Card>
    </main>
  )
}
