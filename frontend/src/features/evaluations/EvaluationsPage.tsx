import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Select, Table, Tabs, Tag } from 'antd'
import { PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { listCases, listFailures, listRuns, listSuites, replay, runCase, runSuite, type EvalCase, type EvalRun } from './api'
import { compactId, formatDate } from '@/shared/lib/format'

const RunTable = ({ rows, onReplay }: { rows: EvalRun[]; onReplay?: (id: string) => void }) => <Table<EvalRun> rowKey="id" dataSource={rows} columns={[{ title: 'Run', dataIndex: 'run_id', render: compactId }, { title: 'Name', dataIndex: 'name' }, { title: 'Type', dataIndex: 'eval_type', render: (v) => <Tag>{v}</Tag> }, { title: 'Result', dataIndex: 'passed', render: (v) => <Tag color={v === true ? 'success' : v === false ? 'error' : 'default'}>{v === true ? 'passed' : v === false ? 'failed' : 'unknown'}</Tag> }, { title: 'Score', dataIndex: 'score' }, { title: 'Created', dataIndex: 'created_at', render: formatDate }, ...(onReplay ? [{ title: 'Actions', render: (_: unknown, row: EvalRun) => <Button icon={<ReloadOutlined />} onClick={() => onReplay(row.id)}>Replay</Button> }] : [])]} />

export function EvaluationsPage() {
  const { message } = App.useApp()
  const client = useQueryClient(); const suites = useQuery({ queryKey: ['evals', 'suites'], queryFn: listSuites }); const [suite, setSuite] = useState(''); const cases = useQuery({ queryKey: ['evals', 'cases', suite], queryFn: () => listCases(suite) }); const runs = useQuery({ queryKey: ['evals', 'runs'], queryFn: listRuns }); const failures = useQuery({ queryKey: ['evals', 'failures'], queryFn: listFailures }); const refresh = () => client.invalidateQueries({ queryKey: ['evals'] })
  return <main className="page"><PageHeader title="Agent Evaluations" description="运行评估套件、检查失败样本和质量趋势" actions={<><Select allowClear value={suite || undefined} onChange={(v) => setSuite(v ?? '')} placeholder="全部套件" options={(suites.data ?? []).map((item) => ({ value: item.id, label: item.name }))} style={{ width: 220 }} /><Button type="primary" icon={<PlayCircleOutlined />} disabled={!suite} onClick={async () => { await runSuite(suite); message.success('评估套件已提交'); await refresh() }}>运行套件</Button></>} />
    <Card className="workbench-card"><Tabs items={[{ key: 'cases', label: 'Cases', children: <Table<EvalCase> rowKey="id" dataSource={cases.data ?? []} loading={cases.isLoading} columns={[{ title: 'Case', dataIndex: 'name' }, { title: 'Input', dataIndex: 'input', ellipsis: true }, { title: 'Criteria', dataIndex: 'criteria', ellipsis: true }, { title: 'Enabled', dataIndex: 'enabled', render: (v) => <Tag color={v ? 'success' : 'default'}>{String(v)}</Tag> }, { title: 'Actions', render: (_, row) => <Button icon={<PlayCircleOutlined />} onClick={async () => { await runCase(row.id); message.success('评估已提交'); await refresh() }}>Run</Button> }]} /> }, { key: 'runs', label: 'Runs', children: <RunTable rows={runs.data ?? []} /> }, { key: 'failures', label: `Failures (${failures.data?.length ?? 0})`, children: <RunTable rows={failures.data ?? []} onReplay={async (id) => { await replay(id); message.success('Replay 已提交'); await refresh() }} /> }]} /></Card>
  </main>
}
