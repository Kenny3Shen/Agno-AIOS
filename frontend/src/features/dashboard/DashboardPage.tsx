import { useMemo, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useRouter } from '@tanstack/react-router'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import { Alert, Button, Card, Col, Empty, Flex, Row, Segmented, Space, Statistic, Table, Tag, Tooltip, Typography, theme } from 'antd'
import { CheckCircleOutlined, ClockCircleOutlined, DatabaseOutlined, ExperimentOutlined, ReloadOutlined, SafetyCertificateOutlined, WarningOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { formatDate } from '@/shared/lib/format'
import { getRuntimeOverview, dashboardKeys } from './api'
import type { OverviewRange, OverviewTrace } from './types'
import { runtimeRanges, timelineChartData } from './utils'

const duration = (value: number | null | undefined) => value == null ? '—' : `${value.toFixed(0)} ms`
const percent = (value: number | null | undefined) => value == null ? '—' : `${(value * 100).toFixed(1)}%`
const integer = (value: number | null | undefined) => value == null ? '—' : Intl.NumberFormat().format(value)

function bucketEnd(value: string, range: OverviewRange) {
  const date = new Date(value)
  if (range === '1h') date.setMinutes(date.getMinutes() + 1)
  if (range === '24h') date.setHours(date.getHours() + 1)
  if (range === '7d') date.setDate(date.getDate() + 1)
  return date.toISOString()
}

export function DashboardPage() {
  const router = useRouter()
  const { token } = theme.useToken()
  const [range, setRange] = useState<OverviewRange>('24h')
  const query = useQuery({
    queryKey: dashboardKeys.detail(range),
    queryFn: () => getRuntimeOverview(range),
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  })
  const data = query.data
  const timeline = useMemo(() => timelineChartData(data?.series ?? []), [data?.series])
  const distribution = useMemo(() => {
    const source = data?.distributions ?? {}
    const [dimension, items] = Object.entries(source).find(([, values]) => values.length > 0) ?? ['agent', []]
    return { dimension, items }
  }, [data?.distributions])
  const common = { textStyle: { color: token.colorTextSecondary }, backgroundColor: 'transparent' }

  const volumeOption = useMemo<EChartsOption>(() => ({
    ...common,
    color: [token.colorPrimary, token.colorError],
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    grid: { top: 24, right: 48, bottom: 26, left: 40 },
    xAxis: { type: 'category', data: timeline.map((item) => item.time), axisLabel: { formatter: (value: string) => formatDate(value) } },
    yAxis: [{ type: 'value', name: 'Runs', minInterval: 1 }, { type: 'value', name: 'Error %', axisLabel: { formatter: '{value}%' } }],
    series: [
      { name: 'Runs', type: 'bar', data: timeline.map((item) => item.runs), barMaxWidth: 22, itemStyle: { borderRadius: [3, 3, 0, 0] } },
      { name: 'Error rate', type: 'line', yAxisIndex: 1, data: timeline.map((item) => item.errorRate), smooth: true, symbol: 'none' },
    ],
  }), [common, timeline, token.colorError, token.colorPrimary])

  const latencyOption = useMemo<EChartsOption>(() => ({
    ...common,
    color: [token.colorInfo, token.colorWarning],
    tooltip: { trigger: 'axis' },
    grid: { top: 24, right: 24, bottom: 26, left: 52 },
    xAxis: { type: 'category', data: timeline.map((item) => item.time), axisLabel: { formatter: (value: string) => formatDate(value) } },
    yAxis: { type: 'value', name: 'ms' },
    series: [
      { name: 'P50', type: 'line', data: timeline.map((item) => item.p50), smooth: true, symbol: 'none' },
      { name: 'P95', type: 'line', data: timeline.map((item) => item.p95), smooth: true, symbol: 'none', lineStyle: { width: 3 } },
    ],
  }), [common, timeline, token.colorInfo, token.colorWarning])

  const distributionOption = useMemo<EChartsOption>(() => ({
    ...common,
    color: [token.colorPrimary, token.colorSuccess, token.colorWarning, token.colorError, token.colorInfo],
    tooltip: { trigger: 'item' },
    series: [{
      name: distribution.dimension,
      type: 'pie',
      radius: ['46%', '76%'],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: token.colorBgContainer, borderWidth: 2 },
      label: { formatter: '{b}  {d}%' },
      data: distribution.items.map((item) => ({ name: item.name, value: item.value })),
    }],
  }), [common, distribution.dimension, distribution.items, token.colorBgContainer, token.colorError, token.colorInfo, token.colorPrimary, token.colorSuccess, token.colorWarning])

  const openTrace = (trace: OverviewTrace) => {
    const search = new URLSearchParams()
    if (trace.session_id) search.set('session', trace.session_id)
    if (trace.run_id) search.set('run', trace.run_id)
    void router.history.push(`/trace${search.size ? `?${search}` : ''}`)
  }
  const openBucket = (timestamp: string) => {
    const search = new URLSearchParams({ start_time: timestamp, end_time: bucketEnd(timestamp, range) })
    void router.history.push(`/trace?${search}`)
  }
  const hasTimeline = timeline.some((item) => item.runs > 0)

  return <main className="page dashboard-page">
    <PageHeader
      title="运行概览"
      description="以运行时间轴聚合 Trace、质量与治理信号"
      actions={<Space wrap><Segmented value={range} options={[...runtimeRanges]} onChange={(value) => setRange(value as OverviewRange)} /><Tooltip title="刷新"><Button aria-label="刷新运行概览" icon={<ReloadOutlined />} loading={query.isFetching} onClick={() => void query.refetch()} /></Tooltip></Space>}
    />
    {query.isError && <Alert className="dashboard-error" type="error" showIcon message="无法加载运行概览" description="请检查运行服务和当前访问权限后重试。" />}
    <section className="dashboard-signal-rail" aria-label="运行状态">
      <span><i className={data?.health.status === 'ok' || data?.health.status === 'ready' ? 'healthy' : 'degraded'} />Runtime <b>{data?.health.status ?? 'checking'}</b></span>
      <span>观察窗口 <b>{range}</b></span>
      <span>更新于 <b>{data?.generated_at ? formatDate(data.generated_at) : '—'}</b></span>
    </section>
    <Row gutter={[12, 12]} className="dashboard-kpis">
      <Col xs={12} md={6}><Card className="workbench-card dashboard-kpi" loading={query.isLoading}><Statistic title="运行总量" value={data?.metrics.total_runs ?? 0} prefix={<CheckCircleOutlined />} /></Card></Col>
      <Col xs={12} md={6}><Card className="workbench-card dashboard-kpi" loading={query.isLoading}><Statistic title="失败率" value={data?.metrics.failure_rate == null ? 0 : data.metrics.failure_rate * 100} precision={1} suffix="%" valueStyle={{ color: data?.metrics.failure_rate ? token.colorError : undefined }} prefix={<WarningOutlined />} /></Card></Col>
      <Col xs={12} md={6}><Card className="workbench-card dashboard-kpi" loading={query.isLoading}><Statistic title="P95 时延" value={data?.metrics.p95_duration_ms ?? 0} suffix="ms" prefix={<ClockCircleOutlined />} /></Card></Col>
      <Col xs={12} md={6}><Card className="workbench-card dashboard-kpi" loading={query.isLoading}><Statistic title="已上报 Token" value={data?.metrics.total_tokens ?? 0} prefix={<DatabaseOutlined />} /></Card></Col>
    </Row>
    <section className="dashboard-grid dashboard-primary-grid">
      <Card className="workbench-card dashboard-chart-card" title="运行时间轴" extra={<Typography.Text type="secondary">点击时间桶查看 Trace</Typography.Text>} loading={query.isLoading}>
        {hasTimeline ? <ReactECharts option={volumeOption} style={{ height: 300 }} opts={{ renderer: 'canvas' }} onEvents={{ click: (params: { dataIndex?: number }) => { const item = timeline[params.dataIndex ?? -1]; if (item) openBucket(item.time) } }} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前窗口暂无运行记录" />}
      </Card>
      <Card className="workbench-card dashboard-chart-card" title={`${distribution.dimension} 分布`} loading={query.isLoading}>
        {distribution.items.length > 0 ? <ReactECharts option={distributionOption} style={{ height: 300 }} opts={{ renderer: 'canvas' }} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可聚合主体" />}
      </Card>
    </section>
    <section className="dashboard-grid dashboard-secondary-grid">
      <Card className="workbench-card dashboard-chart-card" title="时延趋势" loading={query.isLoading}>
        {hasTimeline ? <ReactECharts option={latencyOption} style={{ height: 260 }} opts={{ renderer: 'canvas' }} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无时延数据" />}
      </Card>
      <Card className="workbench-card dashboard-summary-card" title="质量与治理" loading={query.isLoading}>
        <div className="dashboard-summary-list">
          <SummaryMetric icon={<ExperimentOutlined />} label="评估通过率" value={percent(data?.snapshots?.evaluation?.pass_rate)} note={data?.snapshots?.evaluation ? `${data.snapshots.evaluation.passed} passed · ${data.snapshots.evaluation.failed} failed` : '暂无评估数据'} />
          <SummaryMetric icon={<SafetyCertificateOutlined />} label="待审批" value={integer(data?.snapshots?.pending_approvals)} note="需要人工决策的运行请求" />
          <SummaryMetric icon={<DatabaseOutlined />} label="知识文档 / 记忆" value={`${integer(data?.snapshots?.knowledge_documents)} / ${integer(data?.snapshots?.memories)}`} note="当前可用的运行上下文资产" />
        </div>
      </Card>
    </section>
    <section className="dashboard-grid dashboard-detail-grid">
      <Card className="workbench-card" title="最近失败运行" loading={query.isLoading}>
        <Table<OverviewTrace> size="small" rowKey="trace_id" dataSource={data?.recent_failures ?? []} pagination={false} locale={{ emptyText: '当前窗口没有失败运行' }} onRow={(record) => ({ onClick: () => openTrace(record), className: 'dashboard-trace-row' })} columns={[
          { title: '运行', dataIndex: 'name', ellipsis: true, render: (value) => value || 'Unnamed run' },
          { title: '主体', render: (_, item) => item.agent_id || item.workflow_id || '—', ellipsis: true },
          { title: '时延', dataIndex: 'duration_ms', width: 106, render: duration },
          { title: '开始时间', dataIndex: 'start_time', width: 164, render: formatDate },
          { title: '状态', dataIndex: 'status', width: 92, render: (value) => <Tag color="error">{value}</Tag> },
        ]} />
      </Card>
      {data?.audit && <Card className="workbench-card" title="近期审计活动" loading={query.isLoading}>
        <div className="dashboard-audit-list">{data.audit.recent.length ? data.audit.recent.map((event) => <Flex key={String(event.id)} className="dashboard-audit-row" justify="space-between" gap={12}><div><Typography.Text strong>{event.action}</Typography.Text><br /><Typography.Text type="secondary">{event.actor_email || event.resource_type}</Typography.Text></div><div><Tag color={event.status === 'error' ? 'error' : 'success'}>{event.status}</Tag><Typography.Text type="secondary" className="dashboard-audit-time">{formatDate(event.created_at)}</Typography.Text></div></Flex>) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无审计活动" />}</div>
      </Card>}
    </section>
  </main>
}

function SummaryMetric({ icon, label, value, note }: { icon: ReactNode; label: string; value: string; note: string }) {
  return <div className="dashboard-summary-metric"><span className="dashboard-summary-icon">{icon}</span><div><Typography.Text type="secondary">{label}</Typography.Text><Typography.Title level={4}>{value}</Typography.Title><Typography.Text type="secondary">{note}</Typography.Text></div></div>
}
