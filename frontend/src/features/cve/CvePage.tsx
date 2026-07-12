import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { App, Button, Card, Input, Select, Space, Table, Tag } from 'antd'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { searchCves, updateCves, type Cve } from './api'
import { formatDate } from '@/shared/lib/format'

export function CvePage() {
  const { message } = App.useApp()
  const [query, setQuery] = useState('')
  const [source, setSource] = useState<string>()
  const [pagination, setPagination] = useState({ page: 1, size: 20 })
  const search = useMutation({ mutationFn: searchCves })
  const update = useMutation({ mutationFn: updateCves, onSuccess: () => message.success('CVE 数据库已更新') })
  const runSearch = (page = 1, size = pagination.size) => {
    setPagination({ page, size })
    search.mutate({ query, source, page, size })
  }
  return (
    <main className="page">
      <PageHeader title="CVE Intelligence" description="搜索本地漏洞情报并维护数据索引" />
      <Card className="workbench-card">
        <Space className="cve-toolbar" wrap>
          <Space.Compact className="cve-search-control">
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onPressEnter={() => runSearch()}
              placeholder="CVE ID、产品或关键词；留空查看最近入库"
            />
            <Button type="primary" icon={<SearchOutlined />} loading={search.isPending} onClick={() => runSearch()}>
              搜索
            </Button>
          </Space.Compact>
          <Select
            allowClear
            value={source}
            onChange={setSource}
            placeholder="全部来源"
            options={[
              { value: 'github', label: 'GitHub' },
              { value: 'exploit-db', label: 'Exploit-DB' },
            ]}
          />
          <Button icon={<ReloadOutlined />} loading={update.isPending} onClick={() => update.mutate()}>
            更新数据库
          </Button>
        </Space>
        <Table<Cve>
          rowKey="id"
          dataSource={search.data?.items ?? []}
          loading={search.isPending}
          pagination={{
            current: pagination.page,
            pageSize: pagination.size,
            total: search.data?.total,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
          }}
          onChange={(next) => runSearch(next.current ?? 1, next.pageSize ?? pagination.size)}
          style={{ marginTop: 12 }}
          expandable={{ expandedRowRender: (row) => <p>{row.description}</p> }}
          columns={[
            {
              title: 'CVE',
              dataIndex: 'cve_id',
              width: 150,
              render: (value, row) => (
                <a href={row.github_url} target="_blank" rel="noreferrer">
                  {value}
                </a>
              ),
            },
            { title: 'Description', dataIndex: 'description', ellipsis: true },
            { title: 'Source', dataIndex: 'source', width: 130, render: (value) => <Tag>{value}</Tag> },
            { title: 'Indexed', dataIndex: 'create_time', width: 190, render: (value) => formatDate(value) },
          ]}
        />
      </Card>
    </main>
  )
}
