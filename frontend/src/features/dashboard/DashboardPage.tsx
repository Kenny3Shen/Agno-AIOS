import { useQuery } from '@tanstack/react-query'
import { Card, Col, Row, Statistic, Table, Tag } from 'antd'
import { CheckCircleOutlined, ClockCircleOutlined, DatabaseOutlined, WarningOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { requestJson } from '@/shared/api/client'
import { asArray, asRecord, compactId, formatDate } from '@/shared/lib/format'

const load = async () => {
  const [health, traces, sessions] = await Promise.all([
    requestJson<unknown>('/health').catch(() => ({ status: 'degraded' })),
    requestJson<unknown>('/traces?page=1&limit=8').catch(() => ({ items: [], total_count: 0 })),
    requestJson<unknown>('/chat/sessions').catch(() => []),
  ])
  return { health: asRecord(health), traces: asRecord(traces), sessions: asArray(sessions) }
}

export function DashboardPage() {
  const query = useQuery({ queryKey: ['dashboard'], queryFn: load, refetchInterval: 30_000 })
  const traces = asArray<Record<string, unknown>>(query.data?.traces.items)
  const errors = traces.filter((item) => item.status === 'ERROR').length
  return <main className="page"><PageHeader title="运行概览" description="Agent 运行面、会话与 Trace 的实时健康视图" />
    <Row gutter={[12, 12]}>
      <Col xs={12} lg={6}><Card><Statistic title="Runtime" value={String(query.data?.health.status ?? 'checking')} prefix={<CheckCircleOutlined />} /></Card></Col>
      <Col xs={12} lg={6}><Card><Statistic title="Sessions" value={query.data?.sessions.length ?? 0} prefix={<DatabaseOutlined />} /></Card></Col>
      <Col xs={12} lg={6}><Card><Statistic title="Traces" value={Number(query.data?.traces.total_count ?? traces.length)} prefix={<ClockCircleOutlined />} /></Card></Col>
      <Col xs={12} lg={6}><Card><Statistic title="Errors sampled" value={errors} valueStyle={{ color: errors ? '#df3f36' : undefined }} prefix={<WarningOutlined />} /></Card></Col>
    </Row>
    <Card className="workbench-card" title="Recent traces" style={{ marginTop: 12 }} loading={query.isLoading}>
      <Table rowKey={(row) => String(row.trace_id)} dataSource={traces} pagination={false} size="small" columns={[
        { title: 'Trace', dataIndex: 'trace_id', render: (value) => compactId(String(value)) },
        { title: 'Name', dataIndex: 'name', ellipsis: true },
        { title: 'Status', dataIndex: 'status', render: (value) => <Tag color={value === 'ERROR' ? 'error' : 'success'}>{String(value)}</Tag> },
        { title: 'Duration', dataIndex: 'duration_ms', render: (value) => `${Number(value ?? 0).toFixed(0)} ms` },
        { title: 'Started', dataIndex: 'start_time', render: (value) => formatDate(String(value)) },
      ]} />
    </Card>
  </main>
}
