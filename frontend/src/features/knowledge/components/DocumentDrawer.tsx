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
  knowledgeFileErrorKey,
  normalizeUploadFiles,
  selectedUploadFile,
  validateKnowledgeFile,
} from '../utils'
import { IngestOptionsFields } from './IngestOptionsFields'
import { useTranslation } from 'react-i18next'

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
  const { t } = useTranslation('knowledge')
  const { message } = App.useApp()
  const [pending, setPending] = useState(false)

  const submit = async (create: () => Promise<Document>) => {
    setPending(true)
    try {
      const document = await create()
      // Close drawer immediately; parse/vectorize continues in a backend task.
      onClose()
      await onCreated(document)
      message.success(t('ingestQueued'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('addFailed'))
    } finally {
      setPending(false)
    }
  }

  return (
    <Drawer
      size={560}
      open={open}
      onClose={() => {
        if (pending) return
        onClose()
      }}
      destroyOnHidden
      title={t('addDocument')}
      maskClosable={!pending}
      keyboard={!pending}
    >
      <Tabs
        destroyOnHidden
        items={[
          {
            key: 'upload',
            label: t('uploadTab'),
            children: (
              <Form
                layout="vertical"
                preserve={false}
                disabled={pending}
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
                    }),
                  )
                }}
              >
                <Alert className="knowledge-form-note" type="info" showIcon title={t('uploadHint')} />
                <Form.Item
                  name="fileList"
                  label={t('document')}
                  valuePropName="fileList"
                  getValueFromEvent={normalizeUploadFiles}
                  rules={[
                    {
                      validator: (_, value: UploadFile[]) =>
                        selectedUploadFile(value) ? Promise.resolve() : Promise.reject(new Error(t('selectDocument'))),
                    },
                  ]}
                >
                  <Upload.Dragger
                    accept={KNOWLEDGE_FILE_ACCEPT}
                    maxCount={1}
                    disabled={pending}
                    beforeUpload={(file) => {
                      const issue = validateKnowledgeFile(file)
                      if (!issue) return false
                      message.error(t(knowledgeFileErrorKey(issue)))
                      return Upload.LIST_IGNORE
                    }}
                  >
                    <p className="knowledge-upload-icon">
                      <InboxOutlined />
                    </p>
                    <p>{t('dragUpload')}</p>
                    <p className="ant-upload-hint">{t('uploadSupport')}</p>
                  </Upload.Dragger>
                </Form.Item>
                <Form.Item name="title" label={t('titleField')}>
                  <Input placeholder={t('titlePlaceholder')} />
                </Form.Item>
                <Form.Item name="source" label={t('sourceField')}>
                  <Input placeholder={t('sourcePlaceholder')} />
                </Form.Item>
                <Form.Item name="visibility" label={t('common:visibility')}>
                  <VisibilitySelect style={{ width: '100%' }} />
                </Form.Item>
                <IngestOptionsFields defaults={ingestDefaults} />
                <Button loading={pending} type="primary" htmlType="submit" icon={<FileAddOutlined />}>
                  {t('uploadIngest')}
                </Button>
              </Form>
            ),
          },
          {
            key: 'text',
            label: t('textTab'),
            children: (
              <Form
                layout="vertical"
                preserve={false}
                disabled={pending}
                initialValues={{ visibility: 'private' }}
                onFinish={(values: {
                  title: string
                  source?: string
                  content: string
                  visibility: ResourceVisibility
                  ingest_options?: KnowledgeIngestOptions
                }) => {
                  return submit(() =>
                    addText({
                      ...values,
                      ingest_options: cleanIngestOptions(values.ingest_options),
                    }),
                  )
                }}
              >
                <Form.Item name="title" label={t('titleField')} rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
                <Form.Item name="source" label={t('sourceField')}>
                  <Input />
                </Form.Item>
                <Form.Item name="content" label={t('common:content')} rules={[{ required: true }]}>
                  <Input.TextArea rows={12} />
                </Form.Item>
                <Form.Item name="visibility" label={t('common:visibility')}>
                  <VisibilitySelect style={{ width: '100%' }} />
                </Form.Item>
                <IngestOptionsFields defaults={ingestDefaults} />
                <Button loading={pending} type="primary" htmlType="submit">
                  {t('ingestAction')}
                </Button>
              </Form>
            ),
          },
        ]}
      />
    </Drawer>
  )
}
