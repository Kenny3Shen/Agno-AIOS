import { useState } from 'react'
import { Alert, App, Button, Drawer, Form, Input, Tabs, Upload, type UploadFile } from 'antd'
import { FileAddOutlined, InboxOutlined } from '@ant-design/icons'
import { VisibilitySelect } from '@/shared/ui/VisibilitySelect'
import type { ResourceVisibility } from '@/shared/types/common'
import { addText, uploadDocument } from '../api'
import type { Document, KnowledgeIngestOptions } from '../types'
import type { KnowledgeIngestDefaults } from '../utils'
import {
  cleanIngestOptions,
  KNOWLEDGE_FILE_ACCEPT,
  knowledgeFileErrorMessage,
  normalizeUploadFiles,
  selectedUploadFile,
  validateKnowledgeFile,
} from '../utils'
import { IngestOptionsFields } from './IngestOptionsFields'

export function DocumentDrawer({
  open,
  onClose,
  onCreated,
  ingestDefaults,
}: {
  open: boolean
  onClose: () => void
  onCreated: (document: Document) => Promise<void>
  ingestDefaults?: KnowledgeIngestDefaults
}) {
  const { message } = App.useApp()
  const [pending, setPending] = useState(false)

  const submit = async (create: () => Promise<Document>) => {
    setPending(true)
    try {
      const document = await create()
      await onCreated(document)
      message.success('文档已添加')
      onClose()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '文档添加失败')
    } finally {
      setPending(false)
    }
  }

  return (
    <Drawer size={560} open={open} onClose={onClose} destroyOnHidden title="添加知识文档">
      <Tabs
        destroyOnHidden
        items={[
          {
            key: 'upload',
            label: 'Upload',
            children: (
              <Form
                layout="vertical"
                preserve={false}
                initialValues={{ visibility: 'private' }}
                onFinish={(values: {
                  fileList: UploadFile[]
                  title?: string
                  source?: string
                  visibility: ResourceVisibility
                  ingest_options?: KnowledgeIngestOptions
                }) => {
                  const file = selectedUploadFile(values.fileList)
                  if (!file) return
                  return submit(() =>
                    uploadDocument({
                      file,
                      title: values.title,
                      source: values.source,
                      visibility: values.visibility,
                      ingest_options: cleanIngestOptions(values.ingest_options),
                    })
                  )
                }}
              >
                <Alert className="knowledge-form-note" type="info" showIcon title="文件将上传到受控存储，并在入库后生成向量索引。" />
                <Form.Item
                  name="fileList"
                  label="文档"
                  valuePropName="fileList"
                  getValueFromEvent={normalizeUploadFiles}
                  rules={[
                    {
                      validator: (_, value: UploadFile[]) =>
                        selectedUploadFile(value) ? Promise.resolve() : Promise.reject(new Error('请选择文档')),
                    },
                  ]}
                >
                  <Upload.Dragger
                    accept={KNOWLEDGE_FILE_ACCEPT}
                    maxCount={1}
                    beforeUpload={(file) => {
                      const issue = validateKnowledgeFile(file)
                      if (!issue) return false
                      message.error(knowledgeFileErrorMessage(issue))
                      return Upload.LIST_IGNORE
                    }}
                  >
                    <p className="knowledge-upload-icon">
                      <InboxOutlined />
                    </p>
                    <p>拖拽文档到此处，或点击选择文件</p>
                    <p className="ant-upload-hint">支持 Markdown、文本、代码、CSV、JSON、PDF 和 DOCX，最大 50 MB</p>
                  </Upload.Dragger>
                </Form.Item>
                <Form.Item name="title" label="标题">
                  <Input placeholder="默认使用文件名" />
                </Form.Item>
                <Form.Item name="source" label="来源">
                  <Input placeholder="例如 Papers、Runbook" />
                </Form.Item>
                <Form.Item name="visibility" label="可见性">
                  <VisibilitySelect style={{ width: '100%' }} />
                </Form.Item>
                <IngestOptionsFields defaults={ingestDefaults} />
                <Button loading={pending} type="primary" htmlType="submit" icon={<FileAddOutlined />}>
                  上传并入库
                </Button>
              </Form>
            ),
          },
          {
            key: 'text',
            label: 'Text',
            children: (
              <Form
                layout="vertical"
                preserve={false}
                initialValues={{ visibility: 'private' }}
                onFinish={(values: {
                  title: string
                  source?: string
                  content: string
                  visibility: ResourceVisibility
                  ingest_options?: KnowledgeIngestOptions
                }) => submit(() => addText({ ...values, ingest_options: cleanIngestOptions(values.ingest_options) }))}
              >
                <Form.Item name="title" label="标题" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
                <Form.Item name="source" label="来源">
                  <Input />
                </Form.Item>
                <Form.Item name="content" label="内容" rules={[{ required: true }]}>
                  <Input.TextArea rows={12} />
                </Form.Item>
                <Form.Item name="visibility" label="可见性">
                  <VisibilitySelect style={{ width: '100%' }} />
                </Form.Item>
                <IngestOptionsFields defaults={ingestDefaults} />
                <Button loading={pending} type="primary" htmlType="submit">
                  入库
                </Button>
              </Form>
            ),
          },
        ]}
      />
    </Drawer>
  )
}
