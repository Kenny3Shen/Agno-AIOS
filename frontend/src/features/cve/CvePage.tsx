import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Button, Card, Input, Select, Space, Table, Tag, message } from 'antd'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { searchCves, updateCves, type Cve } from './api'
import { formatDate } from '@/shared/lib/format'

export function CvePage() {
  const [query, setQuery] = useState('')
  const [source, setSource] = useState<string>()
  const search = useMutation({ mutationFn: () => searchCves({ query, source, page: 1, size: 100 }) })
  const update = useMutation({ mutationFn: updateCves, onSuccess: () => message.success('CVE 数据库已更新') })
  return <main className="page"><PageHeader title="CVE Intelligence" description="搜索本地漏洞情报并维护数据索引" actions={<><Button icon={<ReloadOutlined />} loading={update.isPending} onClick={() => update.mutate()}>更新数据库</Button><Button type="primary" icon={<SearchOutlined />} loading={search.isPending} onClick={() => search.mutate()}>搜索</Button></>} />
    <Card className="workbench-card"><Space wrap><Input.Search value={query} onChange={(event) => setQuery(event.target.value)} onSearch={() => search.mutate()} placeholder="CVE ID、产品或关键词" style={{ width: 320 }} /><Select allowClear value={source} onChange={setSource} placeholder="全部来源" options={[{ value: 'github', label: 'GitHub' }, { value: 'exploit-db', label: 'Exploit-DB' }]} style={{ width: 150 }} /></Space>
      <Table<Cve> rowKey="id" dataSource={search.data?.items ?? []} loading={search.isPending} pagination={{ pageSize: 20, total: search.data?.total }} style={{ marginTop: 12 }} expandable={{ expandedRowRender: (row) => <p>{row.description}</p> }} columns={[
        { title: 'CVE', dataIndex: 'cve_id', width: 150, render: (value, row) => <a href={row.github_url} target="_blank" rel="noreferrer">{value}</a> },
        { title: 'Description', dataIndex: 'description', ellipsis: true },
        { title: 'Source', dataIndex: 'source', width: 130, render: (value) => <Tag>{value}</Tag> },
        { title: 'Indexed', dataIndex: 'create_time', width: 190, render: (value) => formatDate(value) },
      ]} />
    </Card>
  </main>
}
