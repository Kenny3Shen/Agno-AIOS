import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Drawer, Empty, Form, Input, Popconfirm, Space, Switch, Table, Tabs, Tag, Typography, Upload } from 'antd'
import { DeleteOutlined, InboxOutlined, UploadOutlined } from '@ant-design/icons'
import { Markdown } from '@/shared/ui/Markdown'
import { PageHeader } from '@/shared/ui/PageHeader'
import { deleteSkill, getSkill, listSkillReferences, listSkills, setVisibility, toggleSkill, uploadSkill, type Skill } from './api'
import { getSkillBody, getSkillDetailMetadata } from './utils'
import { VisibilitySelect } from '@/shared/ui/VisibilitySelect'
import { MetadataDescriptions } from '@/shared/ui/MetadataDescriptions'
import { useTranslation } from 'react-i18next'

export function SkillsPage() {
  const { t } = useTranslation('skills')
  const { message } = App.useApp()
  const client = useQueryClient()
  const query = useQuery({ queryKey: ['skills'], queryFn: listSkills })
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [uploadOpen, setUploadOpen] = useState(false)
  const detailQuery = useQuery({
    queryKey: ['skills', 'detail', selectedName],
    queryFn: () => getSkill(selectedName!),
    enabled: Boolean(selectedName),
  })
  const referencesQuery = useQuery({
    queryKey: ['skills', 'references', selectedName],
    queryFn: () => listSkillReferences(selectedName!),
    enabled: Boolean(selectedName),
  })
  const selected = detailQuery.data ?? query.data?.find((skill) => skill.name === selectedName) ?? null
  const refresh = () => client.invalidateQueries({ queryKey: ['skills'] })
  const updateVisibility = async (name: string, visibility: 'private' | 'public') => {
    try {
      await setVisibility(name, visibility)
      await refresh()
      message.success(t('visibilityUpdated'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('visibilityFailed'))
    }
  }
  const removeSkill = async (skill: Skill) => {
    try {
      await deleteSkill(skill.name)
      if (selectedName === skill.name) setSelectedName(null)
      message.success(t('deleted'))
      await refresh()
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('deleteFailed'))
    }
  }
  const toggle = useMutation({
    mutationFn: ({ skill, enabled }: { skill: Skill; enabled: boolean }) => toggleSkill(skill.name, enabled),
    onSuccess: async (_, { enabled }) => {
      message.success(enabled ? t('enabled') : t('disabled'))
      await refresh()
    },
    onError: (error) => message.error(error instanceof Error ? error.message : t('statusFailed')),
  })
  const body = selected ? getSkillBody(selected.skill_markdown) : ''
  const detailMetadata = selected ? getSkillDetailMetadata(selected) : null

  return (
    <main className="page">
      <PageHeader
        title={t('title')}
        description={t('description')}
        actions={
          <Button type="primary" icon={<UploadOutlined />} onClick={() => setUploadOpen(true)}>
            {t('uploadSkill')}
          </Button>
        }
      />
      <Card className="workbench-card">
        <Table<Skill>
          rowKey="name"
          dataSource={query.data ?? []}
          loading={query.isLoading}
          scroll={{ x: 760 }}
          rowClassName={(row) => (row.name === selectedName ? 'selected-table-row' : '')}
          onRow={(row) => ({
            tabIndex: 0,
            role: 'button',
            'aria-label': t('viewSkill', { name: row.name }),
            onClick: () => setSelectedName(row.name),
            onKeyDown: (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                setSelectedName(row.name)
              }
            },
          })}
          columns={[
            {
              title: t('colSkill'),
              dataIndex: 'name',
              render: (value, row) => (
                <Space>
                  <strong>{value}</strong>
                  {row.has_scripts && <Tag>scripts</Tag>}
                </Space>
              ),
            },
            { title: t('colDescription'), dataIndex: 'description', ellipsis: true },
            {
              title: t('colVisibility'),
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
              title: t('colEnabled'),
              dataIndex: 'enabled',
              width: 100,
              render: (value, row) => {
                const pending = toggle.isPending && toggle.variables?.skill.name === row.name
                return (
                  <Switch
                    checked={value}
                    loading={pending}
                    disabled={!row.can_manage}
                    onClick={(_, event) => event?.stopPropagation()}
                    onChange={(enabled) => toggle.mutate({ skill: row, enabled })}
                  />
                )
              },
            },
            {
              title: t('colActions'),
              key: 'actions',
              width: 88,
              render: (_, row) =>
                row.can_delete ? (
                  <Popconfirm
                    title={t('deleteConfirm')}
                    onConfirm={(event) => {
                      event?.stopPropagation()
                      void removeSkill(row)
                    }}
                  >
                    <Button
                      aria-label={t('deleteNamed', { name: row.name })}
                      danger
                      type="text"
                      size="small"
                      icon={<DeleteOutlined />}
                      onClick={(event) => event.stopPropagation()}
                    />
                  </Popconfirm>
                ) : null,
            },
          ]}
        />
      </Card>
      <Drawer
        size={560}
        open={Boolean(selectedName)}
        onClose={() => setSelectedName(null)}
        title={selected?.name ?? selectedName ?? 'Skill'}
        destroyOnHidden
      >
        {detailQuery.isLoading && !selected?.skill_markdown ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common:loading')} />
        ) : selected ? (
          <Tabs
            destroyOnHidden
            items={[
              {
                key: 'content',
                label: 'SKILL.md',
                children: body ? (
                  <Markdown content={body} openLinksInNewTab escapeRawHtml />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('noSkillMd')} />
                ),
              },
              {
                key: 'metadata',
                label: 'Metadata',
                children: <MetadataDescriptions value={detailMetadata} />,
              },
              {
                key: 'references',
                label: t('referencesTab'),
                children: referencesQuery.isLoading ? (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common:loading')} />
                ) : referencesQuery.data?.data.length ? (
                  <>
                  {referencesQuery.data.truncated ? (
                    <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
                      {t('referencesTruncated')}
                    </Typography.Text>
                  ) : null}
                  <Table
                    size="small"
                    rowKey="workflow_id"
                    pagination={false}
                    dataSource={referencesQuery.data.data}
                    columns={[
                      {
                        title: t('referencedWorkflow'),
                        dataIndex: 'name',
                        ellipsis: true,
                      },
                      {
                        title: t('version'),
                        dataIndex: 'version',
                        width: 88,
                        render: (value: string) => (value ? `v${value}` : '—'),
                      },
                      {
                        title: t('common:actions'),
                        key: 'open',
                        width: 100,
                        render: (_, row) => (
                          <Button
                            type="link"
                            size="small"
                            style={{ paddingInline: 0 }}
                            href={`#/workflow?workflow_id=${encodeURIComponent(row.workflow_id)}`}
                          >
                            {t('openWorkflow')}
                          </Button>
                        ),
                      },
                    ]}
                  />
                  </>
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('referencesEmpty')} />
                ),
              },
            ]}
          />
        ) : null}
      </Drawer>
      <Drawer size={480} open={uploadOpen} onClose={() => setUploadOpen(false)} title={t('uploadSkill')}>
        <Form
          layout="vertical"
          initialValues={{ visibility: 'private' }}
          onFinish={async (values: { name: string; visibility: 'private' | 'public'; file: { file: File } }) => {
            try {
              const result = await uploadSkill(values.name, values.visibility, values.file.file)
              if (result.status === 'pending') {
                message.success(t('pendingApproval'))
              } else {
                message.success(t('uploaded'))
                await refresh()
              }
              setUploadOpen(false)
            } catch (error) {
              message.error(error instanceof Error ? error.message : t('uploadFailed'))
            }
          }}
        >
          <Form.Item name="name" label={t('common:name')} extra={t('namePlaceholderEmpty')}>
            <Input placeholder={t('namePlaceholder')} />
          </Form.Item>
          <Form.Item name="visibility" label={t('common:visibility')}>
            <VisibilitySelect style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="file" label={t('zipFile')} valuePropName="file">
            <Upload.Dragger maxCount={1} beforeUpload={() => false}>
              <InboxOutlined />
              <p>{t('selectPackage')}</p>
            </Upload.Dragger>
          </Form.Item>
          <Button htmlType="submit" type="primary">
            {t('upload')}
          </Button>
        </Form>
      </Drawer>
    </main>
  )
}
