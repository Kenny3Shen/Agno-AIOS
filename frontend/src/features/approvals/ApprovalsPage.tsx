import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Descriptions, Drawer, Select, Space, Table, Tag } from 'antd'
import { CheckOutlined, CloseOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { PayloadViewer } from '@/shared/ui/PayloadViewer'
import { getApprovals, resolveApproval, type Approval } from './api'
import { compactId, formatDate } from '@/shared/lib/format'

export function ApprovalsPage() {
  const { message } = App.useApp()
  const client = useQueryClient()
  const [status, setStatus] = useState('pending')
  const [selected, setSelected] = useState<Approval | null>(null)
  const query = useQuery({ queryKey: ['approvals', status], queryFn: () => getApprovals(status) })
  const refresh = () => client.invalidateQueries({ queryKey: ['approvals'] })
  const resolve = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: 'approved' | 'rejected' }) => resolveApproval(id, decision),
    onSuccess: async (row) => {
      setSelected(row)
      message.success(`审批已${row.status}`)
      await refresh()
    },
  })
  return (
    <main className="page">
      <PageHeader
        title="Approvals"
        description="处理暂停的 Agent 操作与人工确认请求"
        actions={
          <Select
            value={status}
            onChange={setStatus}
            options={['pending', 'approved', 'rejected', 'expired'].map((value) => ({ value, label: value }))}
          />
        }
      />
      <Card className="workbench-card">
        <Table<Approval>
          rowKey="id"
          dataSource={query.data ?? []}
          loading={query.isLoading}
          rowClassName={(row) => (row.id === selected?.id ? 'selected-table-row' : '')}
          onRow={(row) => ({
            tabIndex: 0,
            role: 'button',
            'aria-label': `查看审批 ${row.id}`,
            onClick: () => setSelected(row),
            onKeyDown: (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                setSelected(row)
              }
            },
          })}
          columns={[
            { title: 'Request', dataIndex: 'id', render: compactId },
            { title: 'Tool', dataIndex: 'tool_name' },
            { title: 'Type', dataIndex: 'approval_type' },
            {
              title: 'Status',
              dataIndex: 'status',
              render: (value) => <Tag color={value === 'pending' ? 'warning' : value === 'approved' ? 'success' : 'error'}>{value}</Tag>,
            },
            { title: 'Created', dataIndex: 'created_at', render: formatDate },
          ]}
        />
      </Card>
      <Drawer size={600} open={Boolean(selected)} onClose={() => setSelected(null)} title="Approval detail">
        {selected && (
          <>
            <Descriptions
              bordered
              column={1}
              items={[
                { key: 'id', label: 'ID', children: selected.id },
                { key: 'run', label: 'Run', children: selected.run_id ?? '-' },
                { key: 'session', label: 'Session', children: selected.session_id ?? '-' },
              ]}
            />
            <PayloadViewer value={selected.tool_args} />
            <Space style={{ marginTop: 12 }}>
              <Button
                type="primary"
                icon={<CheckOutlined />}
                disabled={selected.status !== 'pending'}
                loading={resolve.isPending}
                onClick={() => resolve.mutate({ id: selected.id, decision: 'approved' })}
              >
                批准
              </Button>
              <Button
                danger
                icon={<CloseOutlined />}
                disabled={selected.status !== 'pending'}
                loading={resolve.isPending}
                onClick={() => resolve.mutate({ id: selected.id, decision: 'rejected' })}
              >
                拒绝
              </Button>
            </Space>
          </>
        )}
      </Drawer>
    </main>
  )
}
