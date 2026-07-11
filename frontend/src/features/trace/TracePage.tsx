import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useRouter, useRouterState } from '@tanstack/react-router'
import { Button, Card, Empty, Grid, Input, Pagination, Select, Space, Splitter, Tabs, Tag, Tree, Typography, type TreeDataNode, type TreeProps } from 'antd'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { CopyableValue, MetadataDescriptions } from '@/shared/ui/MetadataDescriptions'
import { FormattedContentCard } from '@/shared/ui/FormattedContentCard'
import { formatDate } from '@/shared/lib/format'
import { sessionsQuery } from '@/features/chat'
import { traceQuery, tracesQuery } from './queries'
import { filterSessionsByArchive, firstSpanId, groupRuns, groupSessions, previewSpanValue, type SessionArchiveFilter } from './utils'
import type { Span, SpanTreeNode, TraceRun } from './types'

interface RunSpanTreeNode extends TreeDataNode {
  kind: 'run' | 'span'
  runId: string
  spanId?: string
  children?: RunSpanTreeNode[]
}

const SESSION_PAGE_SIZE = 8
const RUN_PAGE_SIZE = 6

function spanNodes(nodes: SpanTreeNode[], runId: string): RunSpanTreeNode[] {
  return nodes.map((node) => {
    const input = previewSpanValue(node.span.parsed?.input)
    return {
      key: `span:${runId}:${node.span.span_id}`,
      kind: 'span',
      runId,
      spanId: node.span.span_id,
      title: <div className="span-tree-node">
        <div className="span-tree-copy"><strong>{node.span.name || 'Span'}</strong>{input && <small>{input}</small>}</div>
        <span><Tag color={node.span.status_code === 'ERROR' ? 'error' : 'success'}>{node.span.status_code}</Tag>{Number(node.span.duration_ms).toFixed(1)} ms</span>
      </div>,
      children: spanNodes(node.children ?? [], runId),
    }
  })
}

function runSpanTree(runs: TraceRun[], selectedRun: string, spans: SpanTreeNode[]): RunSpanTreeNode[] {
  return runs.map((run) => ({
    key: `run:${run.runId}`,
    kind: 'run',
    runId: run.runId,
    title: <div className="run-tree-node">
      <div><strong>{run.name || 'Run'}</strong><small>{formatDate(run.startTime)}</small></div>
      <span><Tag color={run.status === 'ERROR' ? 'error' : 'success'}>{run.status}</Tag>{run.durationMs.toFixed(1)} ms</span>
    </div>,
    children: run.runId === selectedRun ? spanNodes(spans, run.runId) : undefined,
    isLeaf: false,
  }))
}

export function TracePage() {
  const router = useRouter()
  const screens = Grid.useBreakpoint()
  const vertical = screens.lg === false
  const searchStr = useRouterState({ select: (state) => state.location.searchStr })
  const initial = useMemo(() => new URLSearchParams(searchStr), [searchStr])
  const [sessionInput, setSessionInput] = useState(initial.get('session') ?? '')
  const [runInput, setRunInput] = useState(initial.get('run') ?? '')
  const [status, setStatus] = useState('')
  const [archiveFilter, setArchiveFilter] = useState<SessionArchiveFilter>('all')
  const [filters, setFilters] = useState({ session_id: sessionInput, run_id: runInput, status, page: 1, limit: 100 })
  const [selectedSession, setSelectedSession] = useState(initial.get('session') ?? '')
  const [selectedRun, setSelectedRun] = useState(initial.get('run') ?? '')
  const [selectedSpanId, setSelectedSpanId] = useState('')
  const [expandedTreeKeys, setExpandedTreeKeys] = useState<string[]>([])
  const [sessionPage, setSessionPage] = useState(1)
  const [runPage, setRunPage] = useState(1)
  const list = useQuery(tracesQuery(filters))
  const chatSessions = useQuery(sessionsQuery(true))
  const sessionPreviews = useMemo(() => Object.fromEntries((chatSessions.data ?? []).map((session) => [session.session_id, session.preview])), [chatSessions.data])
  const archivedSessions = useMemo(() => Object.fromEntries((chatSessions.data ?? []).map((session) => [session.session_id, session.archived === true])), [chatSessions.data])
  const sessions = useMemo(() => filterSessionsByArchive(groupSessions(list.data?.items ?? [], sessionPreviews, archivedSessions, chatSessions.isSuccess), archiveFilter), [archiveFilter, archivedSessions, chatSessions.isSuccess, list.data?.items, sessionPreviews])
  const visibleSessions = useMemo(() => sessions.slice((sessionPage - 1) * SESSION_PAGE_SIZE, sessionPage * SESSION_PAGE_SIZE), [sessionPage, sessions])
  const runs = useMemo(() => groupRuns(list.data?.items ?? [], selectedSession), [list.data?.items, selectedSession])
  const visibleRuns = useMemo(() => runs.slice((runPage - 1) * RUN_PAGE_SIZE, runPage * RUN_PAGE_SIZE), [runPage, runs])
  const run = runs.find((item) => item.runId === selectedRun) ?? null
  const detail = useQuery(traceQuery(run?.traceId ?? ''))
  const treeData = useMemo(() => runSpanTree(visibleRuns, selectedRun, detail.data?.tree ?? []), [detail.data?.tree, selectedRun, visibleRuns])
  const selectedSpan = detail.data?.spans.find((span) => span.span_id === selectedSpanId) ?? null

  useEffect(() => {
    if (sessions.some((item) => item.sessionId === selectedSession)) return
    setSelectedSession(sessions[0]?.sessionId ?? '')
  }, [selectedSession, sessions])
  useEffect(() => setSessionPage(1), [archiveFilter])
  useEffect(() => {
    const lastPage = Math.max(1, Math.ceil(sessions.length / SESSION_PAGE_SIZE))
    setSessionPage((page) => Math.min(page, lastPage))
  }, [sessions.length])
  useEffect(() => {
    if (runs.some((item) => item.runId === selectedRun)) return
    setSelectedRun(runs[0]?.runId ?? '')
  }, [runs, selectedRun])
  useEffect(() => {
    const lastPage = Math.max(1, Math.ceil(runs.length / RUN_PAGE_SIZE))
    setRunPage((page) => Math.min(page, lastPage))
  }, [runs.length])
  useEffect(() => {
    setExpandedTreeKeys(selectedRun ? [`run:${selectedRun}`] : [])
  }, [selectedRun])
  useEffect(() => {
    if (detail.data?.spans.some((span) => span.span_id === selectedSpanId)) return
    setSelectedSpanId(firstSpanId(detail.data?.tree ?? []))
  }, [detail.data, selectedSpanId])

  const selectSession = (sessionId: string) => {
    setSelectedSession(sessionId)
    setSelectedRun('')
    setSelectedSpanId('')
    setExpandedTreeKeys([])
    setRunPage(1)
    void router.history.push(`/trace?session=${encodeURIComponent(sessionId)}`)
  }
  const selectRun = (runId: string) => {
    setSelectedRun(runId)
    setSelectedSpanId('')
    setExpandedTreeKeys([`run:${runId}`])
    void router.history.push(`/trace?session=${encodeURIComponent(selectedSession)}&run=${encodeURIComponent(runId)}`)
  }
  const apply = () => {
    setSelectedSession(sessionInput)
    setSelectedRun(runInput)
    setSelectedSpanId('')
    setExpandedTreeKeys(runInput ? [`run:${runInput}`] : [])
    setSessionPage(1)
    setRunPage(1)
    setFilters({ session_id: sessionInput, run_id: runInput, status, page: 1, limit: 100 })
  }
  const changeSessionPage = (page: number) => {
    setSessionPage(page)
    const firstSession = sessions[(page - 1) * SESSION_PAGE_SIZE]
    if (firstSession) selectSession(firstSession.sessionId)
  }
  const changeRunPage = (page: number) => {
    setRunPage(page)
    const firstRun = runs[(page - 1) * RUN_PAGE_SIZE]
    if (firstRun) selectRun(firstRun.runId)
  }
  const selectTreeNode: TreeProps<RunSpanTreeNode>['onSelect'] = (_, info) => {
    if (info.node.kind === 'run') selectRun(info.node.runId)
    if (info.node.kind === 'span' && info.node.spanId) {
      if (info.node.runId !== selectedRun) selectRun(info.node.runId)
      setSelectedSpanId(info.node.spanId)
    }
  }
  const expandTreeNode: TreeProps<RunSpanTreeNode>['onExpand'] = (keys, info) => {
    setExpandedTreeKeys(keys.map(String))
    if (info.node.kind === 'run' && info.expanded && info.node.runId !== selectedRun) selectRun(info.node.runId)
  }

  return <main className="page trace-page">
    <PageHeader title="Trace Observability" description="从 Session、Run 到 Span 的端到端观测与调试" actions={<Button icon={<ReloadOutlined />} loading={list.isFetching} onClick={() => void list.refetch()}>刷新</Button>} />
    <Card className="workbench-card trace-toolbar"><Space wrap>
      <Input value={sessionInput} onChange={(event) => setSessionInput(event.target.value)} placeholder="Session ID" allowClear />
      <Input value={runInput} onChange={(event) => setRunInput(event.target.value)} placeholder="Run ID" allowClear />
      <Select value={status} onChange={setStatus} style={{ width: 130 }} options={[{ value: '', label: 'All status' }, { value: 'OK' }, { value: 'ERROR' }, { value: 'UNSET' }]} />
      <Select<SessionArchiveFilter> aria-label="Session archive filter" value={archiveFilter} onChange={setArchiveFilter} style={{ width: 150 }} options={[{ value: 'all', label: '全部 Session' }, { value: 'active', label: '活跃 Session' }, { value: 'archived', label: '已归档 Session' }]} />
      <Button type="primary" icon={<SearchOutlined />} onClick={apply}>查询</Button>
    </Space></Card>
    <Splitter className="trace-workbench-splitter" orientation={vertical ? 'vertical' : 'horizontal'}>
      <Splitter.Panel defaultSize={vertical ? '28%' : '24%'} min={vertical ? 180 : 220}>
        <Card className="workbench-card splitter-panel-card" title="Sessions" extra={<Tag>{sessions.length}</Tag>}>
          <div className="trace-paginated-list">
            <div className="trace-choice-list">{visibleSessions.length > 0 ? visibleSessions.map((session) => <button key={session.sessionId} type="button" className={`trace-choice ${session.sessionId === selectedSession ? 'selected' : ''}`} aria-pressed={session.sessionId === selectedSession} onClick={() => selectSession(session.sessionId)}>
              <strong>{session.name}</strong>
              <span>{session.archived && <Tag>Archived</Tag>}{session.runCount} runs{session.context ? ` · ${session.context}` : ''}</span>
              <small>{formatDate(session.latestAt)}</small>
            </button>) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={false} />}</div>
            <Pagination size="small" align="center" current={sessionPage} pageSize={SESSION_PAGE_SIZE} total={sessions.length} showSizeChanger={false} onChange={changeSessionPage} />
          </div>
        </Card>
      </Splitter.Panel>
      <Splitter.Panel defaultSize={vertical ? '34%' : '32%'} min={vertical ? 240 : 340}>
        <Card className="workbench-card splitter-panel-card" title="Runs & Spans" extra={<Tag>{runs.length}</Tag>}>
          <div className="trace-paginated-list">
            <Tree<RunSpanTreeNode>
              className="run-span-tree"
              blockNode
              showLine
              treeData={treeData}
              expandedKeys={expandedTreeKeys}
              selectedKeys={selectedSpanId ? [`span:${selectedRun}:${selectedSpanId}`] : selectedRun ? [`run:${selectedRun}`] : []}
              onExpand={expandTreeNode}
              onSelect={selectTreeNode}
            />
            <Pagination size="small" align="center" current={runPage} pageSize={RUN_PAGE_SIZE} total={runs.length} showSizeChanger={false} onChange={changeRunPage} />
          </div>
        </Card>
      </Splitter.Panel>
      <Splitter.Panel defaultSize={vertical ? '38%' : '44%'} min={vertical ? 300 : 420}>
        <Card className="workbench-card splitter-panel-card" title="Detail" extra={selectedSpan && <Space><Typography.Text type="secondary">{selectedSpan.name}</Typography.Text><Tag color={selectedSpan.status_code === 'ERROR' ? 'error' : 'success'}>{selectedSpan.status_code}</Tag></Space>}>
          {selectedSpan ? <SpanDetailTabs span={selectedSpan} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={false} />}
        </Card>
      </Splitter.Panel>
    </Splitter>
  </main>
}

function SpanDetailTabs({ span }: { span: Span }) {
  const metadata = Object.fromEntries(Object.entries({ metadata: span.parsed?.metadata, attributes: span.attributes, events: span.events }).filter(([, value]) => value != null && (!(Array.isArray(value)) || value.length > 0)))
  return <Tabs className="trace-detail-tabs" size="small" destroyOnHidden items={[
    { key: 'info', label: 'Info', children: <Splitter className="trace-info-splitter" orientation="vertical">
      <Splitter.Panel defaultSize="50%" min="20%">
        <FormattedContentCard title="Input" value={span.parsed?.input} />
      </Splitter.Panel>
      <Splitter.Panel defaultSize="50%" min="30%">
        <FormattedContentCard title="Output" value={span.parsed?.output} />
      </Splitter.Panel>
    </Splitter> },
    { key: 'metadata', label: 'Metadata', children: <MetadataDescriptions items={[
      { key: 'span-id', label: 'Span ID', children: <CopyableValue value={span.span_id} /> },
      { key: 'parent-span-id', label: 'Parent Span ID', children: <CopyableValue value={span.parent_span_id} /> },
      { key: 'operation', label: 'Operation', children: span.name || '-' },
      { key: 'status', label: 'Status', children: <Tag color={span.status_code === 'ERROR' ? 'error' : 'success'}>{span.status_code}</Tag> },
      { key: 'duration', label: 'Duration', children: `${Number(span.duration_ms).toFixed(1)} ms` },
      { key: 'started', label: 'Started', children: formatDate(span.start_time) },
    ]} value={metadata} /> },
  ]} />
}
