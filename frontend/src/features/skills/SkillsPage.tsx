import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Drawer, Empty, Form, Grid, Input, Space, Splitter, Switch, Table, Tabs, Tag, Upload } from 'antd'
import { InboxOutlined, UploadOutlined } from '@ant-design/icons'
import XMarkdown from '@ant-design/x-markdown'
import { PageHeader } from '@/shared/ui/PageHeader'
import { listSkills, setVisibility, toggleSkill, uploadSkill, type Skill } from './api'
import { getSkillBody, getSkillDetailMetadata } from './utils'
import { VisibilitySelect } from '@/shared/ui/VisibilitySelect'
import { MetadataDescriptions } from '@/shared/ui/MetadataDescriptions'

export function SkillsPage() {
  const { message } = App.useApp()
  const screens = Grid.useBreakpoint()
  const vertical = screens.md === false
  const client = useQueryClient()
  const query = useQuery({ queryKey: ['skills'], queryFn: listSkills })
  const [selected, setSelected] = useState<Skill | null>(null)
  const [uploadOpen, setUploadOpen] = useState(false)
  const refresh = () => client.invalidateQueries({ queryKey: ['skills'] })
  const updateVisibility = async (name: string, visibility: 'private' | 'public') => {
    try {
      await setVisibility(name, visibility)
      await refresh()
      message.success('可见性已更新')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '更新技能可见性失败')
    }
  }
  const toggle = useMutation({
    mutationFn: ({ skill, enabled }: { skill: Skill; enabled: boolean }) => toggleSkill(skill.name, enabled),
    onSuccess: async (_, { enabled }) => {
      message.success(enabled ? '技能已启用' : '技能已停用')
      await refresh()
    },
    onError: (error) => message.error(error instanceof Error ? error.message : '更新技能状态失败'),
  })
  const body = selected ? getSkillBody(selected.skill_markdown) : ''
  const detailMetadata = selected ? getSkillDetailMetadata(selected) : null

  return (
    <main className="page">
      <PageHeader
        title="Skills"
        description="管理 Agent 可调用技能、脚本与资源可见性"
        actions={
          <Button type="primary" icon={<UploadOutlined />} onClick={() => setUploadOpen(true)}>
            上传技能
          </Button>
        }
      />
      <Splitter className="workbench-splitter skills-splitter" orientation={vertical ? 'vertical' : 'horizontal'}>
        <Splitter.Panel defaultSize="70%" min={vertical ? 260 : '45%'}>
          <Card className="workbench-card splitter-panel-card">
            <Table<Skill>
              rowKey="name"
              dataSource={query.data ?? []}
              loading={query.isLoading}
              scroll={{ x: 760 }}
              rowClassName={(row) => (row.name === selected?.name ? 'selected-table-row' : '')}
              onRow={(row) => ({
                tabIndex: 0,
                role: 'button',
                'aria-label': `查看技能 ${row.name}`,
                onClick: () => setSelected(row),
                onKeyDown: (event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    setSelected(row)
                  }
                },
              })}
              columns={[
                {
                  title: 'Skill',
                  dataIndex: 'name',
                  render: (value, row) => (
                    <Space>
                      <strong>{value}</strong>
                      {row.has_scripts && <Tag>scripts</Tag>}
                    </Space>
                  ),
                },
                { title: 'Description', dataIndex: 'description', ellipsis: true },
                {
                  title: 'Visibility',
                  dataIndex: 'visibility',
                  width: 150,
                  render: (value, row) => (
                    <VisibilitySelect
                      value={value}
                      disabled={!row.can_manage}
                      onClick={(event) => event.stopPropagation()}
                      onChange={(visibility) => void updateVisibility(row.name, visibility)}
                    />
                  ),
                },
                {
                  title: 'Enabled',
                  dataIndex: 'enabled',
                  width: 100,
                  render: (value, row) => {
                    const pending = toggle.isPending && toggle.variables?.skill.name === row.name
                    return (
                      <Switch
                        checked={value}
                        disabled={!row.can_manage || pending}
                        loading={pending}
                        onClick={(_, event) => event.stopPropagation()}
                        onChange={(enabled) => toggle.mutate({ skill: row, enabled })}
                      />
                    )
                  },
                },
              ]}
            />
          </Card>
        </Splitter.Panel>
        <Splitter.Panel defaultSize="30%" min={vertical ? 180 : '20%'}>
          <Card className="workbench-card splitter-panel-card" title="Detail">
            {selected ? (
              <Tabs
                destroyOnHidden
                items={[
                  {
                    key: 'content',
                    label: 'SKILL.md',
                    children: body ? (
                      <XMarkdown content={body} openLinksInNewTab escapeRawHtml />
                    ) : (
                      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该技能没有 SKILL.md 内容" />
                    ),
                  },
                  { key: 'metadata', label: 'Metadata', children: <MetadataDescriptions value={detailMetadata} /> },
                ]}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择一个技能查看详情" />
            )}
          </Card>
        </Splitter.Panel>
      </Splitter>
      <Drawer size={480} open={uploadOpen} onClose={() => setUploadOpen(false)} title="上传技能">
        <Form
          layout="vertical"
          initialValues={{ visibility: 'private' }}
          onFinish={async (values: { name: string; visibility: 'private' | 'public'; file: { file: File } }) => {
            await uploadSkill(values.name, values.visibility, values.file.file)
            message.success('技能已上传')
            setUploadOpen(false)
            await refresh()
          }}
        >
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="visibility" label="可见性">
            <VisibilitySelect style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="file" label="ZIP 文件" valuePropName="file">
            <Upload.Dragger maxCount={1} beforeUpload={() => false}>
              <InboxOutlined />
              <p>选择技能包</p>
            </Upload.Dragger>
          </Form.Item>
          <Button htmlType="submit" type="primary">
            上传
          </Button>
        </Form>
      </Drawer>
    </main>
  )
}
