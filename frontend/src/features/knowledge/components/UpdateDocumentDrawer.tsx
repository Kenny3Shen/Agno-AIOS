import { useMemo, useState } from 'react'
import { Alert, App, Button, Drawer, Form, Input, Tabs, Upload, type FormInstance, type UploadFile } from 'antd'
import { InboxOutlined, SaveOutlined } from '@ant-design/icons'
import { VisibilitySelect } from '@/shared/ui/VisibilitySelect'
import type { ResourceVisibility } from '@/shared/types/common'
import { updateDocumentAction, updateDocumentUpload } from '../api'
import type { Document, KnowledgeIngestOptions, KnowledgeProgressEvent } from '../types'
import type { KnowledgeIngestDefaults } from '../utils'
import {
  buildMetadataUpdate,
  cleanIngestOptions,
  decideKnowledgeUpdate,
  hasMetadataUpdate,
  ingestOptionsFromMetadata,
  knowledgeIngestOptionsEqual,
  KNOWLEDGE_FILE_ACCEPT,
  knowledgeFileErrorMessage,
  normalizeUploadFiles,
  replacementFileName,
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

type KnowledgeUpdateTabKey = 'update' | 'text'

interface UpdateTabValues {
  title: string
  source: string
  visibility: ResourceVisibility
  fileList?: UploadFile[]
  ingest_options?: KnowledgeIngestOptions
}

interface TextTabValues {
  title: string
  source: string
  visibility: ResourceVisibility
  file_name: string
  content: string
  ingest_options?: KnowledgeIngestOptions
}

export function UpdateDocumentDrawer({
  document,
  open,
  onClose,
  onUpdated,
  ingestDefaults,
}: {
  document: Document
  open: boolean
  onClose: () => void
  onUpdated: (document: Document) => Promise<void>
  ingestDefaults?: KnowledgeIngestDefaults
}) {
  const { t } = useTranslation('knowledge')
  const { message } = App.useApp()
  const [pending, setPending] = useState(false)
  const [activeTab, setActiveTab] = useState<KnowledgeUpdateTabKey>('update')
  const [progressStages, setProgressStages] = useState<ProgressStageState[] | null>(null)
  const [progressIncludesUpload, setProgressIncludesUpload] = useState(false)
  const [updateForm] = Form.useForm<UpdateTabValues>()
  const [textForm] = Form.useForm<TextTabValues>()
  const fileName = document.metadata?.file_name?.trim() || document.title

  const submitActiveTab = () => {
    if (activeTab === 'text') {
      textForm.submit()
      return
    }
    updateForm.submit()
  }

  const trackProgress = (includeUpload: boolean) => {
    setProgressIncludesUpload(includeUpload)
    setProgressStages(createInitialProgress(includeUpload))
    return (event: KnowledgeProgressEvent) => {
      setProgressStages((current) => applyProgressEvent(current ?? createInitialProgress(includeUpload), event))
    }
  }

  const submit = async (update: () => Promise<Document>, success: string) => {
    setPending(true)
    try {
      const updated = await update()
      await onUpdated(updated)
      message.success(success)
      setProgressStages(null)
      onClose()
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('updateFailed'))
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
      title={t('updateDocument')}
      maskClosable={!pending}
      keyboard={!pending}
    >
      {progressStages ? (
        <UpdateProgress stages={progressStages} includeUpload={progressIncludesUpload} />
      ) : null}
      <Tabs
        activeKey={activeTab}
        destroyOnHidden
        onChange={(key) => {
          if (pending) return
          setActiveTab(key as KnowledgeUpdateTabKey)
        }}
        tabBarExtraContent={{
          right: (
            <Button loading={pending} type="primary" icon={<SaveOutlined />} onClick={submitActiveTab}>
              {t('common:save')}
            </Button>
          ),
        }}
        items={[
          {
            key: 'update',
            label: 'Update',
            children: (
              <UpdateTab
                form={updateForm}
                document={document}
                fileName={fileName}
                ingestDefaults={ingestDefaults}
                disabled={pending}
                onNoop={() => message.info(t('noChanges'))}
                onSubmit={(update, success) => submit(update, success)}
                onTrackProgress={trackProgress}
              />
            ),
          },
          {
            key: 'text',
            label: 'Text',
            children: (
              <TextTab
                form={textForm}
                document={document}
                ingestDefaults={ingestDefaults}
                disabled={pending}
                onSubmit={(update, success) => submit(update, success)}
                onTrackProgress={trackProgress}
              />
            ),
          },
        ]}
      />
    </Drawer>
  )
}

function UpdateTab({
  form,
  document,
  fileName,
  ingestDefaults,
  disabled,
  onNoop,
  onSubmit,
  onTrackProgress,
}: {
  form: FormInstance<UpdateTabValues>
  document: Document
  fileName: string
  ingestDefaults?: KnowledgeIngestDefaults
  disabled?: boolean
  onNoop: () => void
  onSubmit: (update: () => Promise<Document>, success: string) => void
  onTrackProgress: (includeUpload: boolean) => (event: KnowledgeProgressEvent) => void
}) {
  const { t } = useTranslation('knowledge')
  const { message } = App.useApp()
  const initialIngestOptions = useMemo(() => ingestOptionsFromMetadata(document.metadata), [document.metadata])
  return (
    <Form
      form={form}
      layout="vertical"
      disabled={disabled}
      initialValues={{
        title: document.title,
        source: document.source,
        visibility: document.visibility ?? 'private',
        file_name: fileName,
        fileList: [],
        ingest_options: initialIngestOptions,
      }}
      onFinish={(values) => {
        const file = selectedUploadFile(values.fileList)
        const metadata = buildMetadataUpdate(document, values)
        const cleanedIngestOptions = cleanIngestOptions(values.ingest_options)
        const decision = decideKnowledgeUpdate({
          metadata,
          ingest_options: cleanedIngestOptions,
          ingestOptionsChanged: !knowledgeIngestOptionsEqual(cleanedIngestOptions, initialIngestOptions),
          hasFile: Boolean(file),
        })
        if (decision.kind === 'noop') {
          onNoop()
          return
        }
        if (decision.kind === 'upload') {
          if (!file) return
          const onProgress = onTrackProgress(true)
          return onSubmit(
            () =>
              updateDocumentUpload(
                document.id,
                {
                  file,
                  title: decision.metadata?.title,
                  source: decision.metadata?.source,
                  visibility: decision.metadata?.visibility,
                  ingest_options: decision.ingest_options,
                },
                { stream: true, onProgress }
              ),
            t('savedRevectorized')
          )
        }
        if (decision.kind === 'rebuild') {
          const onProgress = onTrackProgress(false)
          return onSubmit(
            () =>
              updateDocumentAction(
                document.id,
                {
                  mode: 'rebuild',
                  metadata: decision.metadata,
                  ingest_options: decision.ingest_options,
                },
                { stream: true, onProgress }
              ),
            t('savedRevectorized')
          )
        }
        return onSubmit(
          () =>
            updateDocumentAction(document.id, {
              mode: 'metadata',
              metadata: decision.metadata,
            }),
          t('saved')
        )
      }}
    >
      <Alert
        className="knowledge-form-note"
        type="info"
        showIcon
        title="{t('updateHint')}"
      />
      <Form.Item name="title" label="Title" rules={[{ required: true, whitespace: true }]}>
        <Input />
      </Form.Item>
      <Form.Item name="source" label="Source" rules={[{ required: true, whitespace: true }]}>
        <Input />
      </Form.Item>
      <Form.Item name="visibility" label="Visibility">
        <VisibilitySelect style={{ width: '100%' }} />
      </Form.Item>
      <Form.Item name="file_name" label="Current source file">
        <Input disabled />
      </Form.Item>
      <Form.Item name="fileList" label="{t('replaceFile')}" valuePropName="fileList" getValueFromEvent={normalizeUploadFiles}>
        <Upload.Dragger
          accept={KNOWLEDGE_FILE_ACCEPT}
          maxCount={1}
          disabled={disabled}
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
          <p>{t('dragReplace')}</p>
          <p className="ant-upload-hint">{t('replaceSupport')}</p>
        </Upload.Dragger>
      </Form.Item>
      <IngestOptionsFields defaults={ingestDefaults} />
    </Form>
  )
}

function TextTab({
  form,
  document,
  ingestDefaults,
  disabled,
  onSubmit,
  onTrackProgress,
}: {
  form: FormInstance<TextTabValues>
  document: Document
  ingestDefaults?: KnowledgeIngestDefaults
  disabled?: boolean
  onSubmit: (update: () => Promise<Document>, success: string) => void
  onTrackProgress: (includeUpload: boolean) => (event: KnowledgeProgressEvent) => void
}) {
  const { t } = useTranslation('knowledge')
  return (
    <Form
      form={form}
      layout="vertical"
      disabled={disabled}
      initialValues={{
        title: document.title,
        source: document.source,
        visibility: document.visibility ?? 'private',
        file_name: replacementFileName(document),
        content: '',
      }}
      onFinish={(values) => {
        const metadata = buildMetadataUpdate(document, values)
        const onProgress = onTrackProgress(false)
        return onSubmit(
          () =>
            updateDocumentAction(
              document.id,
              {
                mode: 'replace_text',
                metadata: hasMetadataUpdate(metadata) ? metadata : undefined,
                file_name: values.file_name.trim(),
                content: values.content,
                ingest_options: cleanIngestOptions(values.ingest_options),
              },
              { stream: true, onProgress }
            ),
          t('savedRevectorized')
        )
      }}
    >
      <Alert
        className="knowledge-form-note"
        type="warning"
        showIcon
        title="{t('replaceTextHint')}"
      />
      <Form.Item name="title" label="Title" rules={[{ required: true, whitespace: true }]}>
        <Input />
      </Form.Item>
      <Form.Item name="source" label="Source" rules={[{ required: true, whitespace: true }]}>
        <Input />
      </Form.Item>
      <Form.Item name="visibility" label="Visibility">
        <VisibilitySelect style={{ width: '100%' }} />
      </Form.Item>
      <Form.Item name="file_name" label={t('fileName')} tooltip="{t('fileNameHint')}" rules={[{ required: true, whitespace: true }]}>
        <Input />
      </Form.Item>
      <Form.Item name="content" label={t('newBody')} rules={[{ required: true, whitespace: true }]}>
        <Input.TextArea rows={14} />
      </Form.Item>
      <IngestOptionsFields defaults={ingestDefaults} />
    </Form>
  )
}
