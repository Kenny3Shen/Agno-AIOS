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
  t,
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
  t: (key: string, options?: Record<string, unknown>) => string
}) => (
  <Table<EvalRun>
    rowKey="id"
    dataSource={rows}
    loading={loading}
    pagination={pagination === undefined ? false : pagination}
    columns={[
      { title: t('colRun'), dataIndex: 'id', render: compactId },
      { title: t('colName'), dataIndex: 'name' },
      { title: t('colType'), dataIndex: 'eval_type', render: (v) => <Tag>{v}</Tag> },
      {
        title: t('colResult'),
        dataIndex: 'passed',
        filters: [
          { text: t('resultPassed'), value: 'true' },
          { text: t('resultFailed'), value: 'false' },
          { text: t('resultUnknown'), value: 'unknown' },
        ],
        onFilter: (value, row) => {
          if (value === 'true') return row.passed === true
          if (value === 'false') return row.passed === false
          return row.passed !== true && row.passed !== false
        },
        render: (v) => (
          <Tag color={v === true ? 'success' : v === false ? 'error' : 'default'}>
            {v === true ? t('resultPassed') : v === false ? t('resultFailed') : t('resultUnknown')}
          </Tag>
        ),
      },
      { title: t('colScore'), dataIndex: 'score' },
      { title: t('colCreated'), dataIndex: 'created_at', defaultSortOrder: 'descend' as const, sorter: (a: EvalRun, b: EvalRun) => compareTimestamp(a.created_at, b.created_at), render: (value) => formatDate(value) },
      ...(onReplay
        ? [
            {
              title: t('colActions'),
              render: (_: unknown, row: EvalRun) => (
                <Button icon={<ReloadOutlined />} onClick={() => onReplay(row.id)}>
                  {t('replay')}
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
                try {
                  await runSuite(suite)
                  message.success(t('suiteSubmitted'))
                  await refresh()
                } catch (error) {
                  message.error(error instanceof Error ? error.message : t('suiteFailed'))
                }
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
              label: t('tabCases'),
              children: (
                <Table<EvalCase>
                  rowKey="id"
                  dataSource={cases.data ?? []}
                  loading={cases.isLoading}
                  columns={[
                    { title: t('colCase'), dataIndex: 'name' },
                    { title: t('colInput'), dataIndex: 'input', ellipsis: true },
                    { title: t('colCriteria'), dataIndex: 'criteria', ellipsis: true },
                    { title: t('colEnabled'), dataIndex: 'enabled', render: (v) => <Tag color={v ? 'success' : 'default'}>{String(v)}</Tag> },
                    {
                      title: t('colActions'),
                      render: (_, row) => (
                        <Button
                          icon={<PlayCircleOutlined />}
                          onClick={async () => {
                            try {
                              await runCase(row.id)
                              message.success(t('evalSubmitted'))
                              await refresh()
                            } catch (error) {
                              message.error(error instanceof Error ? error.message : t('evalFailed'))
                            }
                          }}
                        >
                          {t('runCase')}
                        </Button>
                      ),
                    },
                  ]}
                />
              ),
            },
            { key: 'runs', label: t('tabRuns'), children: (
                <RunTable
                  t={t}
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
              label: t('tabFailures', { count: failures.data?.length ?? 0 }),
              children: (
                <RunTable
                  t={t}
                  rows={failures.data ?? []}
                  loading={failures.isLoading}
                  pagination={false}
                  onReplay={async (id) => {
                    try {
                      await replay(id)
                      message.success(t('replaySubmitted'))
                      await refresh()
                    } catch (error) {
                      message.error(error instanceof Error ? error.message : t('replayFailed'))
                    }
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
