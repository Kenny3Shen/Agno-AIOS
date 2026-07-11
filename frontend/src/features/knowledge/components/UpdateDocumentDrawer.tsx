import { useMemo, useState } from 'react'
import { Alert, App, Button, Drawer, Form, Input, Tabs, Upload, type FormInstance, type UploadFile } from 'antd'
import { InboxOutlined, SaveOutlined } from '@ant-design/icons'
import { VisibilitySelect } from '@/shared/ui/VisibilitySelect'
import type { ResourceVisibility } from '@/shared/types/common'
import { updateDocumentAction, updateDocumentUpload } from '../api'
import type { Document, KnowledgeIngestOptions } from '../types'
import { buildMetadataUpdate, cleanIngestOptions, decideKnowledgeUpdate, hasMetadataUpdate, ingestOptionsFromMetadata, knowledgeIngestOptionsEqual, KNOWLEDGE_FILE_ACCEPT, knowledgeFileErrorMessage, normalizeUploadFiles, replacementFileName, selectedUploadFile, validateKnowledgeFile } from '../utils'
import { IngestOptionsFields } from './IngestOptionsFields'

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

export function UpdateDocumentDrawer({ document, open, onClose, onUpdated }: { document: Document; open: boolean; onClose: () => void; onUpdated: (document: Document) => Promise<void> }) {
  const { message } = App.useApp()
  const [pending, setPending] = useState(false)
  const [activeTab, setActiveTab] = useState<KnowledgeUpdateTabKey>('update')
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

  const submit = async (update: () => Promise<Document>, success: string) => {
    setPending(true)
    try {
      const updated = await update()
      await onUpdated(updated)
      message.success(success)
      onClose()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '文档更新失败')
    } finally {
      setPending(false)
    }
  }

  return <Drawer size={560} open={open} onClose={onClose} destroyOnHidden title="更新文档">
    <Tabs
      activeKey={activeTab}
      destroyOnHidden
      onChange={(key) => setActiveTab(key as KnowledgeUpdateTabKey)}
      tabBarExtraContent={{ right: <Button loading={pending} type="primary" icon={<SaveOutlined />} onClick={submitActiveTab}>保存</Button> }}
      items={[
      { key: 'update', label: 'Update', children: <UpdateTab
        form={updateForm}
        document={document}
        fileName={fileName}
        onNoop={() => message.info('没有变化')}
        onSubmit={(update, success) => submit(update, success)}
      /> },
      { key: 'text', label: 'Text', children: <TextTab
        form={textForm}
        document={document}
        onSubmit={(update, success) => submit(update, success)}
      /> },
    ]} />
  </Drawer>
}

function UpdateTab({
  form,
  document,
  fileName,
  onNoop,
  onSubmit,
}: {
  form: FormInstance<UpdateTabValues>
  document: Document
  fileName: string
  onNoop: () => void
  onSubmit: (update: () => Promise<Document>, success: string) => void
}) {
  const { message } = App.useApp()
  const initialIngestOptions = useMemo(() => ingestOptionsFromMetadata(document.metadata), [document.metadata])

  return <Form
    form={form}
    layout="vertical"
    preserve={false}
    initialValues={{
      title: document.title,
      source: document.source,
      visibility: document.visibility ?? 'private',
      file_name: fileName,
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
        return onSubmit(() => updateDocumentUpload(document.id, {
          file,
          title: decision.metadata?.title,
          source: decision.metadata?.source,
          visibility: decision.metadata?.visibility,
          ingest_options: decision.ingest_options,
        }), '已保存并重新向量化')
      }
      if (decision.kind === 'rebuild') {
        return onSubmit(() => updateDocumentAction(document.id, {
          mode: 'rebuild',
          metadata: decision.metadata,
          ingest_options: decision.ingest_options,
        }), '已保存并重新向量化')
      }
      return onSubmit(() => updateDocumentAction(document.id, {
        mode: 'metadata',
        metadata: decision.metadata,
      }), '已保存')
    }}
  >
    <Alert className="knowledge-form-note" type="info" showIcon title="保存 Metadata、上传替换文件或修改高级分块参数；需要重新生成向量索引时会自动处理。" />
    <Form.Item name="title" label="Title" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item>
    <Form.Item name="source" label="Source" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item>
    <Form.Item name="visibility" label="Visibility"><VisibilitySelect style={{ width: '100%' }} /></Form.Item>
    <Form.Item name="file_name" label="Current source file"><Input disabled /></Form.Item>
    <Form.Item name="fileList" label="替换文件" valuePropName="fileList" getValueFromEvent={normalizeUploadFiles}>
      <Upload.Dragger accept={KNOWLEDGE_FILE_ACCEPT} maxCount={1} beforeUpload={(file) => {
        const issue = validateKnowledgeFile(file)
        if (!issue) return false
        message.error(knowledgeFileErrorMessage(issue))
        return Upload.LIST_IGNORE
      }}>
        <p className="knowledge-upload-icon"><InboxOutlined /></p>
        <p>拖拽新文档到此处，或点击选择文件</p>
        <p className="ant-upload-hint">未选择文件时不会使用上传表单；支持 Markdown、文本、代码、CSV、JSON、PDF 和 DOCX。</p>
      </Upload.Dragger>
    </Form.Item>
    <IngestOptionsFields />
  </Form>
}

function TextTab({
  form,
  document,
  onSubmit,
}: {
  form: FormInstance<TextTabValues>
  document: Document
  onSubmit: (update: () => Promise<Document>, success: string) => void
}) {
  return <Form
    form={form}
    layout="vertical"
    initialValues={{ title: document.title, source: document.source, visibility: document.visibility ?? 'private', file_name: replacementFileName(document), content: '' }}
    onFinish={(values) => {
      const metadata = buildMetadataUpdate(document, values)
      return onSubmit(() => updateDocumentAction(document.id, {
        mode: 'replace_text',
        metadata: hasMetadataUpdate(metadata) ? metadata : undefined,
        file_name: values.file_name.trim(),
        content: values.content,
        ingest_options: cleanIngestOptions(values.ingest_options),
      }), '已保存并重新向量化')
    }}
  >
    <Alert className="knowledge-form-note" type="warning" showIcon title="请提供完整的新正文。保存后将重新分块、重新向量化，并替换旧内容。" />
    <Form.Item name="title" label="Title" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item>
    <Form.Item name="source" label="Source" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item>
    <Form.Item name="visibility" label="Visibility"><VisibilitySelect style={{ width: '100%' }} /></Form.Item>
    <Form.Item name="file_name" label="文件名" tooltip="文件后缀决定 Reader 和分块策略" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item>
    <Form.Item name="content" label="新正文" rules={[{ required: true, whitespace: true }]}><Input.TextArea rows={14} /></Form.Item>
    <IngestOptionsFields />
  </Form>
}
