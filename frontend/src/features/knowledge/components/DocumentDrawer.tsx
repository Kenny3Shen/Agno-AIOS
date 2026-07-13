import { useState } from 'react'
import { Alert, App, Button, Drawer, Form, Input, Tabs, Upload, type UploadFile } from 'antd'
import { FileAddOutlined, InboxOutlined } from '@ant-design/icons'
import { VisibilitySelect } from '@/shared/ui/VisibilitySelect'
import type { ResourceVisibility } from '@/shared/types/common'
import { addText, uploadDocument } from '../api'
import type { Document, KnowledgeIngestOptions, KnowledgeProgressEvent } from '../types'
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
import { useTranslation } from 'react-i18next'
import {
  applyProgressEvent,
  createInitialProgress,
  type ProgressStageState,
  UpdateProgress,
} from './UpdateProgress'

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
  const [progressStages, setProgressStages] = useState<ProgressStageState[] | null>(null)
  const [progressIncludesUpload, setProgressIncludesUpload] = useState(true)

  const trackProgress = (includeUpload: boolean) => {
    setProgressIncludesUpload(includeUpload)
    setProgressStages(createInitialProgress(includeUpload))
    return (event: KnowledgeProgressEvent) => {
      setProgressStages((current) => applyProgressEvent(current ?? createInitialProgress(includeUpload), event))
    }
  }

  const submit = async (create: () => Promise<Document>) => {
    setPending(true)
    try {
      const document = await create()
      await onCreated(document)
      message.success(t('added'))
      setProgressStages(null)
      onClose()
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
        setProgressStages(null)
        onClose()
      }}
      destroyOnHidden
      title={t('addDocument')}
      maskClosable={!pending}
      keyboard={!pending}
    >
      {progressStages ? <UpdateProgress stages={progressStages} includeUpload={progressIncludesUpload} /> : null}
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
                  const onProgress = trackProgress(true)
                  return submit(() =>
                    uploadDocument(
                      {
                        file,
                        title: values.title,
                        source: values.source,
                        visibility: values.visibility,
                        ingest_options: cleanIngestOptions(values.ingest_options),
                      },
                      { stream: true, onProgress }
                    )
                  )
                }}
              >
                <Alert className="knowledge-form-note" type="info" showIcon title="{t('uploadHint')}" />
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
                      message.error(knowledgeFileErrorMessage(issue))
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
            label: 'Text',
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
                  const onProgress = trackProgress(false)
                  return submit(() =>
                    addText(
                      { ...values, ingest_options: cleanIngestOptions(values.ingest_options) },
                      { stream: true, onProgress }
                    )
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
