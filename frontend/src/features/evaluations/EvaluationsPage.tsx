import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Select, Table, Tabs, Tag } from 'antd'
import { PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { listCases, listFailures, listRuns, listSuites, replay, runCase, runSuite, type EvalCase, type EvalRun } from './api'
import { compactId, compareTimestamp, formatDate } from '@/shared/lib/format'
import { useTranslation } from 'react-i18next'

const RunTable = ({
  rows,
  loading,
  pagination,
  onReplay,
}: {
  rows: EvalRun[]
  loading?: boolean
  pagination?: false | {
    current: number
    pageSize: number
    total: number
    onChange: (page: number) => void
  }
  onReplay?: (id: string) => void
}) => (
  <Table<EvalRun>
    rowKey="id"
    dataSource={rows}
    loading={loading}
    pagination={pagination === undefined ? false : pagination}
    columns={[
      { title: 'Run', dataIndex: 'id', render: compactId },
      { title: 'Name', dataIndex: 'name' },
      { title: 'Type', dataIndex: 'eval_type', render: (v) => <Tag>{v}</Tag> },
      {
        title: 'Result',
        dataIndex: 'passed',
        filters: [
          { text: 'passed', value: 'true' },
          { text: 'failed', value: 'false' },
          { text: 'unknown', value: 'unknown' },
        ],
        onFilter: (value, row) => {
          if (value === 'true') return row.passed === true
          if (value === 'false') return row.passed === false
          return row.passed !== true && row.passed !== false
        },
        render: (v) => (
          <Tag color={v === true ? 'success' : v === false ? 'error' : 'default'}>
            {v === true ? 'passed' : v === false ? 'failed' : 'unknown'}
          </Tag>
        ),
      },
      { title: 'Score', dataIndex: 'score' },
      { title: 'Created', dataIndex: 'created_at', defaultSortOrder: 'descend' as const, sorter: (a: EvalRun, b: EvalRun) => compareTimestamp(a.created_at, b.created_at), render: (value) => formatDate(value) },
      ...(onReplay
        ? [
            {
              title: 'Actions',
              render: (_: unknown, row: EvalRun) => (
                <Button icon={<ReloadOutlined />} onClick={() => onReplay(row.id)}>
                  Replay
                </Button>
              ),
            },
          ]
        : []),
    ]}
  />
)

export function EvaluationsPage() {
  const { t } = useTranslation('evaluations')
  const { message } = App.useApp()
  const client = useQueryClient()
  const suites = useQuery({ queryKey: ['evals', 'suites'], queryFn: listSuites })
  const [suite, setSuite] = useState('')
  const [runsPage, setRunsPage] = useState(1)
  const runsPageSize = 20
  const cases = useQuery({ queryKey: ['evals', 'cases', suite], queryFn: () => listCases(suite) })
  const runs = useQuery({
    queryKey: ['evals', 'runs', runsPage, runsPageSize],
    queryFn: () => listRuns({ page: runsPage, limit: runsPageSize }),
  })
  const failures = useQuery({
    queryKey: ['evals', 'failures'],
    queryFn: () => listFailures({ limit: 50 }),
  })
  const refresh = () => client.invalidateQueries({ queryKey: ['evals'] })
  return (
    <main className="page">
      <PageHeader
        title={t('title')}
        description={t('description')}
        actions={
          <>
            <Select
              allowClear
              value={suite || undefined}
              onChange={(v) => setSuite(v ?? '')}
              placeholder={t('allSuites')}
              options={(suites.data ?? []).map((item) => ({ value: item.id, label: item.name }))}
              style={{ width: 220 }}
            />
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              disabled={!suite}
              onClick={async () => {
                await runSuite(suite)
                message.success(t('suiteSubmitted'))
                await refresh()
              }}
            >
              {t('runSuite')}
            </Button>
          </>
        }
      />
      <Card className="workbench-card">
        <Tabs
          items={[
            {
              key: 'cases',
              label: 'Cases',
              children: (
                <Table<EvalCase>
                  rowKey="id"
                  dataSource={cases.data ?? []}
                  loading={cases.isLoading}
                  columns={[
                    { title: 'Case', dataIndex: 'name' },
                    { title: 'Input', dataIndex: 'input', ellipsis: true },
                    { title: 'Criteria', dataIndex: 'criteria', ellipsis: true },
                    { title: 'Enabled', dataIndex: 'enabled', render: (v) => <Tag color={v ? 'success' : 'default'}>{String(v)}</Tag> },
                    {
                      title: 'Actions',
                      render: (_, row) => (
                        <Button
                          icon={<PlayCircleOutlined />}
                          onClick={async () => {
                            await runCase(row.id)
                            message.success(t('evalSubmitted'))
                            await refresh()
                          }}
                        >
                          Run
                        </Button>
                      ),
                    },
                  ]}
                />
              ),
            },
            { key: 'runs', label: 'Runs', children: (
                <RunTable
                  rows={runs.data?.data ?? []}
                  loading={runs.isLoading}
                  pagination={{
                    current: runsPage,
                    pageSize: runsPageSize,
                    total: runs.data?.meta.total_count ?? 0,
                    onChange: setRunsPage,
                  }}
                />
              ) },
            {
              key: 'failures',
              label: `Failures (${failures.data?.length ?? 0})`,
              children: (
                <RunTable
                  rows={failures.data ?? []}
                  loading={failures.isLoading}
                  pagination={false}
                  onReplay={async (id) => {
                    await replay(id)
                    message.success(t('replaySubmitted'))
                    await refresh()
                  }}
                />
              ),
            },
          ]}
        />
      </Card>
    </main>
  )
}
