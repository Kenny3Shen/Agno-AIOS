import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Empty, Form, Grid, Input, InputNumber, Modal, Popconfirm, Space, Splitter, Switch, Table, Tabs, Tag, Typography } from 'antd'
import { KeyOutlined, PlusOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { VisibilitySelect } from '@/shared/ui/VisibilitySelect'
import { copyToClipboard } from '@/shared/lib/clipboard'
import { FormattedContentCard } from '@/shared/ui/FormattedContentCard'
import { MetadataDescriptions } from '@/shared/ui/MetadataDescriptions'
import type { JsonRecord, ResourceVisibility } from '@/shared/types/common'
import {
  callTool,
  deleteToken,
  getConfig,
  issueToken,
  listComponents,
  listTokens,
  setComponentEnabled,
  setServerEnabled,
  setServerVisibility,
  testServer,
  updateConfig,
  uploadServer,
  type McpComponent,
  type McpServer,
  type McpToken,
} from './api'

const tokenTime = (value: number) => value ? new Date(value * 1000).toLocaleString() : '永不过期'

export function McpPage() {
  const { message } = App.useApp()
  const screens = Grid.useBreakpoint()
  const client = useQueryClient()
  const [namespace, setNamespace] = useState<string>()
  const [component, setComponent] = useState<McpComponent>()
  const [issueOpen, setIssueOpen] = useState(false)
  const [serverOpen, setServerOpen] = useState(false)
  const [callOpen, setCallOpen] = useState(false)
  const [callArgs, setCallArgs] = useState('{}')
  const [callResult, setCallResult] = useState<unknown>()
  const [serverForm] = Form.useForm()

  const config = useQuery({ queryKey: ['mcp', 'config'], queryFn: getConfig })
  const components = useQuery({ queryKey: ['mcp', 'components', namespace], queryFn: () => listComponents(namespace) })
  const tokens = useQuery({ queryKey: ['mcp', 'tokens'], queryFn: listTokens })
  const refresh = () => client.invalidateQueries({ queryKey: ['mcp'] })

  const toggleServer = useMutation({
    mutationFn: ({ server, enabled }: { server: McpServer; enabled: boolean }) => server.server_type === 'builtin' ? updateConfig(server.name, enabled) : setServerEnabled(server.id, enabled),
    onSuccess: async (_, { enabled }) => { message.success(enabled ? 'Server 已启用' : 'Server 已停用'); await refresh() },
    onError: (error) => message.error(error.message),
  })
  const toggleComponent = useMutation({
    mutationFn: ({ item, enabled }: { item: McpComponent; enabled: boolean }) => setComponentEnabled(item, enabled),
    onSuccess: async (_, { enabled }) => { message.success(enabled ? '组件已启用' : '组件已停用'); await refresh() },
    onError: (error) => message.error(error.message),
  })

  const servers = config.data?.mcp_servers ?? []
  const selectedServer = servers.find((server) => server.namespace === namespace)
  const riskTags = (item: McpComponent) => {
    const annotations = item.annotations ?? {}
    return <Space wrap>
      {annotations.readOnlyHint === true && <Tag color="blue">只读</Tag>}
      {annotations.destructiveHint === true && <Tag color="red">破坏性</Tag>}
      {annotations.openWorldHint === true && <Tag color="orange">外部系统</Tag>}
    </Space>
  }

  const executeTool = async () => {
    if (!component) return
    try {
      const args = JSON.parse(callArgs) as JsonRecord
      const result = await callTool(component.name, args)
      setCallResult(result)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '参数必须是 JSON 对象')
    }
  }

  const runTool = () => {
    if (component?.annotations?.destructiveHint === true) {
      Modal.confirm({
        title: '确认调用破坏性工具',
        content: component.name,
        okText: '确认调用',
        okButtonProps: { danger: true },
        onOk: executeTool,
      })
      return
    }
    void executeTool()
  }

  return <main className="page mcp-page">
    <PageHeader title="MCP" description="管理 PostgreSQL 中的 MCP Server，并查看 FastMCP 暴露的真实组件" actions={<>
      <Button icon={<PlusOutlined />} onClick={() => setServerOpen(true)}>添加 Server</Button>
      <Button type="primary" icon={<KeyOutlined />} onClick={() => setIssueOpen(true)}>签发令牌</Button>
    </>} />
    <Tabs items={[
      { key: 'components', label: 'Servers & Components', children:
        <Splitter className="workbench-splitter mcp-splitter" orientation={screens.md === false ? 'vertical' : 'horizontal'}>
          <Splitter.Panel defaultSize="68%" min={screens.md === false ? 320 : '48%'}>
            <Card className="workbench-card splitter-panel-card">
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Table<McpServer>
                  rowKey="id" size="small" loading={config.isLoading} dataSource={servers} pagination={false}
                  rowClassName={(row) => row.namespace === namespace ? 'ant-table-row-selected' : ''}
                  onRow={(row) => ({ onClick: () => { setNamespace(row.namespace); setComponent(undefined) } })}
                  columns={[
                    { title: 'Server / Namespace', render: (_, row) => <Space><strong>{row.name}</strong><Typography.Text type="secondary">{row.namespace}</Typography.Text></Space> },
                    { title: 'Transport', dataIndex: 'transport', width: 150, render: (value) => <Tag>{value}</Tag> },
                    { title: 'Enabled', width: 90, render: (_, row) => { const pending = toggleServer.isPending && toggleServer.variables?.server.id === row.id; return <Switch checked={row.enabled} loading={pending} disabled={!row.can_manage || pending} onClick={(_, event) => event.stopPropagation()} onChange={(enabled) => toggleServer.mutate({ server: row, enabled })} /> } },
                    { title: 'Visibility', width: 140, render: (_, row) => <VisibilitySelect value={row.visibility} disabled={!row.can_manage} onClick={(event) => event.stopPropagation()} onChange={(value) => void setServerVisibility(row.name, value).then(refresh)} /> },
                  ]}
                />
                <Table<McpComponent>
                  rowKey="key" size="small" loading={components.isLoading} dataSource={components.data ?? []} pagination={false}
                  locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={namespace ? '该 namespace 没有可见组件' : '选择一个 Server 查看组件'} /> }}
                  onRow={(row) => ({ onClick: () => setComponent(row) })}
                  columns={[
                    { title: 'Component', render: (_, row) => <Space direction="vertical" size={0}><strong>{row.title || row.name}</strong><Typography.Text code>{row.name}</Typography.Text></Space> },
                    { title: 'Type', dataIndex: 'type', width: 100, render: (value) => <Tag color={value === 'tool' ? 'blue' : 'purple'}>{value}</Tag> },
                    { title: 'Tags', dataIndex: 'tags', render: (tags: string[]) => <Space wrap>{tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</Space> },
                    { title: 'Risk', width: 190, render: (_, row) => riskTags(row) },
                    { title: 'Enabled', width: 90, render: (_, row) => { const pending = toggleComponent.isPending && toggleComponent.variables?.item.key === row.key; return <Switch checked={row.enabled} disabled={!row.server_id || pending} loading={pending} onClick={(_, event) => event.stopPropagation()} onChange={(enabled) => toggleComponent.mutate({ item: row, enabled })} /> } },
                  ]}
                />
              </Space>
            </Card>
          </Splitter.Panel>
          <Splitter.Panel defaultSize="32%" min={screens.md === false ? 260 : '24%'}>
            <Card className="workbench-card splitter-panel-card" title="Detail" extra={component?.type === 'tool' && <Button icon={<PlayCircleOutlined />} onClick={() => { setCallResult(undefined); setCallOpen(true) }}>试调用</Button>}>
              {!component && selectedServer && <MetadataDescriptions items={[
                { key: 'name', label: 'Name', children: selectedServer.name },
                { key: 'namespace', label: 'Namespace', children: selectedServer.namespace },
                { key: 'transport', label: 'Transport', children: selectedServer.transport },
                { key: 'store', label: 'Config store', children: config.data?.config_store },
              ]} value={selectedServer.manifest} prefix="Manifest" />}
              {!component && !selectedServer && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择 Server 或 Component 查看详情" />}
              {component && <Tabs destroyOnHidden items={[
                { key: 'overview', label: 'Overview', children: <MetadataDescriptions items={[
                  { key: 'name', label: 'Name', children: component.name },
                  { key: 'title', label: 'Title', children: component.title || '-' },
                  { key: 'namespace', label: 'Namespace', children: component.namespace || '-' },
                  { key: 'description', label: 'Description', children: component.description || '-' },
                ]} value={{ tags: component.tags, annotations: component.annotations }} /> },
                { key: 'schemas', label: 'Schemas', children: <Splitter orientation="vertical" style={{ height: 'calc(100vh - 360px)', minHeight: 420 }}>
                  <Splitter.Panel defaultSize="50%" min={160}><FormattedContentCard title="Input schema" value={component.input_schema} /></Splitter.Panel>
                  <Splitter.Panel defaultSize="50%" min={160}><FormattedContentCard title="Output schema" value={component.output_schema} /></Splitter.Panel>
                </Splitter> },
                { key: 'metadata', label: 'Metadata', children: <MetadataDescriptions value={component.meta} /> },
              ]} />}
            </Card>
          </Splitter.Panel>
        </Splitter>
      },
      { key: 'tokens', label: 'Tokens', children: <Card className="workbench-card"><Table<McpToken>
        rowKey="id" loading={tokens.isLoading} dataSource={tokens.data ?? []}
        columns={[
          { title: 'Name', dataIndex: 'name' },
          { title: 'Created', dataIndex: 'created_at', render: tokenTime },
          { title: 'Expires', dataIndex: 'expires_at', render: tokenTime },
          { title: 'Actions', width: 120, render: (_, row) => <Popconfirm title="删除此令牌？" onConfirm={async () => { await deleteToken(row.id); await refresh() }}><Button danger>删除</Button></Popconfirm> },
        ]}
      /></Card> },
    ]} />

    <Modal open={issueOpen} footer={null} onCancel={() => setIssueOpen(false)} title="签发 MCP Token">
      <Form layout="vertical" initialValues={{ expires_in: 86400 }} onFinish={async (values: { name: string; expires_in: number }) => { const result = await issueToken(values.name, values.expires_in); await copyToClipboard(result.token); message.success('令牌已签发并复制，此后不再显示明文'); setIssueOpen(false); await refresh() }}>
        <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="expires_in" label="有效期（秒，0 表示永久）"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item>
        <Button type="primary" htmlType="submit">签发</Button>
      </Form>
    </Modal>

    <Modal open={serverOpen} footer={null} onCancel={() => setServerOpen(false)} title="添加 MCP Server">
      <Form form={serverForm} layout="vertical" initialValues={{ visibility: 'private', manifest: '{\n  "mcpServers": {}\n}' }} onFinish={async (values: { name: string; description: string; manifest: string; visibility: ResourceVisibility }) => { await uploadServer(values); message.success('Server 已保存，重启后加载'); setServerOpen(false); await refresh() }}>
        <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="description" label="描述"><Input /></Form.Item>
        <Form.Item name="manifest" label="MCPConfig JSON" rules={[{ required: true }]}><Input.TextArea rows={10} /></Form.Item>
        <Form.Item name="visibility" label="可见性"><VisibilitySelect style={{ width: '100%' }} /></Form.Item>
        <Space><Button type="primary" htmlType="submit">保存</Button><Button onClick={async () => { const values = await serverForm.validateFields(); const result = await testServer(values); message.success(`连接成功，发现 ${result.tools.length} 个 Tools`) }}>连接测试</Button></Space>
      </Form>
    </Modal>

    <Modal open={callOpen} onCancel={() => setCallOpen(false)} title={`试调用 ${component?.name ?? ''}`} onOk={runTool} okText="调用">
      <Typography.Paragraph type="secondary">参数必须是 JSON 对象。调用会访问真实工具。</Typography.Paragraph>
      <Input.TextArea rows={8} value={callArgs} onChange={(event) => setCallArgs(event.target.value)} />
      {callResult !== undefined && <FormattedContentCard title="Result" value={callResult} />}
    </Modal>
  </main>
}
