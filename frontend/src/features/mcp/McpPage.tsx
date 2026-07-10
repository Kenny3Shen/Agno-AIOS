import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Descriptions, Empty, Form, Input, InputNumber, Modal, Space, Switch, Table, Tabs, Tag, message } from 'antd'
import { KeyOutlined, PlusOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { VisibilitySelect } from '@/shared/ui/VisibilitySelect'
import { copyToClipboard } from '@/shared/lib/clipboard'
import { deleteToken, getConfig, issueToken, listTokens, setServerVisibility, updateConfig, uploadServer, type McpServer, type McpToken } from './api'
import { getAvailableMcpServices, type AvailableMcpService } from './utils'

export function McpPage() {
  const client = useQueryClient()
  const config = useQuery({ queryKey: ['mcp', 'config'], queryFn: getConfig })
  const tokens = useQuery({ queryKey: ['mcp', 'tokens'], queryFn: listTokens })
  const [issueOpen, setIssueOpen] = useState(false)
  const [serverOpen, setServerOpen] = useState(false)
  const availableServices = useMemo(() => getAvailableMcpServices(config.data), [config.data])
  const refresh = () => client.invalidateQueries({ queryKey: ['mcp'] })
  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => updateConfig(id, enabled),
    onSuccess: refresh,
  })

  return <main className="page">
    <PageHeader title="MCP Control" description="管理 FastMCP 服务、服务器清单和访问令牌" actions={<>
      <Button icon={<PlusOutlined />} onClick={() => setServerOpen(true)}>上传 Server</Button>
      <Button type="primary" icon={<KeyOutlined />} onClick={() => setIssueOpen(true)}>签发令牌</Button>
    </>} />
    <Tabs items={[
      {
        key: 'services',
        label: 'MCP 服务',
        children: <div className="workbench-grid">
          <Card><Descriptions size="small" column={2} items={[
            { key: 'url', label: 'MCP URL', children: config.data?.mcp_url ?? '-' },
            { key: 'version', label: 'FastMCP', children: config.data?.fastmcp ?? '-' },
          ]} /></Card>
          <Card title="当前可用 MCP" extra={<Tag color="success">{availableServices.length} available</Tag>}>
            <Table<AvailableMcpService>
              rowKey="key"
              size="small"
              pagination={false}
              dataSource={availableServices}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前没有启用的 MCP 服务" /> }}
              columns={[
                { title: 'Service', dataIndex: 'name', render: (name) => <strong>{name}</strong> },
                { title: 'Source', dataIndex: 'source' },
                { title: 'Kind', dataIndex: 'kind', width: 120, render: (kind) => <Tag color={kind === 'built-in' ? 'blue' : 'purple'}>{kind}</Tag> },
              ]}
            />
          </Card>
          <Card title="内置 MCP 服务"><Space wrap>
            {Object.entries(config.data?.services ?? {}).map(([id, enabled]) => <Card size="small" key={id}><Space><strong>{id}</strong><Switch checked={enabled} loading={toggle.isPending} onChange={(value) => toggle.mutate({ id, enabled: value })} /></Space></Card>)}
          </Space></Card>
          <Card title="外部 MCP Servers"><Table<McpServer>
            rowKey="name"
            dataSource={config.data?.mcp_servers ?? []}
            pagination={false}
            columns={[
              { title: 'Name', dataIndex: 'name' },
              { title: 'Kind', dataIndex: 'kind', render: (kind) => <Tag>{kind}</Tag> },
              { title: 'Enabled', dataIndex: 'enabled', render: (enabled) => <Switch checked={enabled} disabled /> },
              { title: 'Visibility', dataIndex: 'visibility', width: 150, render: (visibility, row) => <VisibilitySelect value={visibility} disabled={!row.can_manage} onChange={(value) => void setServerVisibility(row.name, value).then(refresh)} /> },
            ]}
          /></Card>
        </div>,
      },
      {
        key: 'tokens',
        label: '访问令牌',
        children: <Card><Table<McpToken> rowKey="id" dataSource={tokens.data ?? []} columns={[
          { title: 'Name', dataIndex: 'name' },
          { title: 'Token', dataIndex: 'token', ellipsis: true, render: (token) => <Button type="link" onClick={() => void copyToClipboard(token)}>复制</Button> },
          { title: 'Actions', render: (_, row) => <Button danger onClick={async () => { await deleteToken(row.id); await refresh() }}>删除</Button> },
        ]} /></Card>,
      },
    ]} />
    <Modal open={issueOpen} footer={null} onCancel={() => setIssueOpen(false)} title="签发 MCP Token">
      <Form layout="vertical" initialValues={{ expires_in: 86400 }} onFinish={async (values: { name: string; expires_in: number }) => { const result = await issueToken(values.name, values.expires_in); await copyToClipboard(result.token); message.success('令牌已签发并复制'); setIssueOpen(false); await refresh() }}>
        <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="expires_in" label="有效期（秒）"><InputNumber min={60} style={{ width: '100%' }} /></Form.Item>
        <Button type="primary" htmlType="submit">签发</Button>
      </Form>
    </Modal>
    <Modal open={serverOpen} footer={null} onCancel={() => setServerOpen(false)} title="上传 MCP Server">
      <Form layout="vertical" initialValues={{ visibility: 'private', manifest: '{}' }} onFinish={async (values) => { await uploadServer(values); message.success('Server 已上传'); setServerOpen(false); await refresh() }}>
        <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="description" label="描述"><Input /></Form.Item>
        <Form.Item name="manifest" label="Manifest JSON"><Input.TextArea rows={8} /></Form.Item>
        <Form.Item name="visibility" label="可见性"><VisibilitySelect style={{ width: '100%' }} /></Form.Item>
        <Button type="primary" htmlType="submit">上传</Button>
      </Form>
    </Modal>
  </main>
}
