import { useState } from 'react'
import { Alert, App, Button, Drawer, Form, Input, Tabs, Upload, type UploadFile } from 'antd'
import { EditOutlined, InboxOutlined, SyncOutlined } from '@ant-design/icons'
import { VisibilitySelect } from '@/shared/ui/VisibilitySelect'
import type { ResourceVisibility } from '@/shared/types/common'
import { replaceDocumentSource, replaceDocumentSourceFile, updateDocument } from '../api'
import type { Document, KnowledgeIngestOptions } from '../types'
import { buildMetadataUpdate, cleanIngestOptions, hasMetadataUpdate, KNOWLEDGE_FILE_ACCEPT, knowledgeFileErrorMessage, normalizeUploadFiles, replacementFileName, selectedUploadFile, validateKnowledgeFile } from '../utils'
import { IngestOptionsFields } from './IngestOptionsFields'

export function UpdateDocumentDrawer({ document, open, onClose, onUpdated }: { document: Document; open: boolean; onClose: () => void; onUpdated: (document: Document) => Promise<void> }) {
  const { message } = App.useApp()
  const [pending, setPending] = useState(false)

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
    <Tabs destroyOnHidden items={[
      { key: 'metadata', label: 'Metadata', children: <Form layout="vertical" initialValues={{ title: document.title, source: document.source, visibility: document.visibility ?? 'private' }} onFinish={(values: { title: string; source: string; visibility: ResourceVisibility }) => {
        const payload = buildMetadataUpdate(document, values)
        if (!hasMetadataUpdate(payload)) {
          message.info('Metadata 没有变化')
          return
        }
        return submit(() => updateDocument(document.id, payload), 'Metadata 已更新')
      }}>
        <Alert className="knowledge-form-note" type="info" showIcon title="只更新 Title、Source 和 Visibility，不会重新生成向量。" />
        <Form.Item name="title" label="Title" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item>
        <Form.Item name="source" label="Source" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item>
        <Form.Item name="visibility" label="Visibility"><VisibilitySelect style={{ width: '100%' }} /></Form.Item>
        <Button loading={pending} type="primary" htmlType="submit" icon={<EditOutlined />}>保存 Metadata</Button>
      </Form> },
      { key: 'upload', label: 'Upload', children: <Form layout="vertical" preserve={false} onFinish={(values: { fileList: UploadFile[]; title?: string; source?: string; visibility?: ResourceVisibility; ingest_options?: KnowledgeIngestOptions }) => {
        const file = selectedUploadFile(values.fileList)
        if (!file) return
        return submit(() => replaceDocumentSourceFile(document.id, {
          file,
          title: values.title,
          source: values.source,
          visibility: values.visibility,
          ingest_options: cleanIngestOptions(values.ingest_options),
        }), '文件已更新并重新向量化')
      }}>
        <Alert className="knowledge-form-note" type="warning" showIcon title="上传文件会替换当前文档源内容；可选覆盖 Metadata，并重新分块、重新向量化。" />
        <Form.Item name="fileList" label="文档" valuePropName="fileList" getValueFromEvent={normalizeUploadFiles} rules={[{ validator: (_, value: UploadFile[]) => selectedUploadFile(value) ? Promise.resolve() : Promise.reject(new Error('请选择文档')) }]}>
          <Upload.Dragger accept={KNOWLEDGE_FILE_ACCEPT} maxCount={1} beforeUpload={(file) => {
            const issue = validateKnowledgeFile(file)
            if (!issue) return false
            message.error(knowledgeFileErrorMessage(issue))
            return Upload.LIST_IGNORE
          }}>
            <p className="knowledge-upload-icon"><InboxOutlined /></p>
            <p>拖拽新文档到此处，或点击选择文件</p>
            <p className="ant-upload-hint">支持 Markdown、文本、代码、CSV、JSON、PDF 和 DOCX，最大 50 MB</p>
          </Upload.Dragger>
        </Form.Item>
        <Form.Item name="title" label="Title" tooltip="留空时保留当前 Title"><Input placeholder={document.title} /></Form.Item>
        <Form.Item name="source" label="Source" tooltip="留空时保留当前 Source"><Input placeholder={document.source} /></Form.Item>
        <Form.Item name="visibility" label="Visibility" tooltip="留空时保留当前 Visibility"><VisibilitySelect allowClear placeholder={document.visibility ?? 'private'} style={{ width: '100%' }} /></Form.Item>
        <IngestOptionsFields />
        <Button loading={pending} type="primary" htmlType="submit" icon={<SyncOutlined />}>上传并重新向量化</Button>
      </Form> },
      { key: 'text', label: 'Text', children: <Form layout="vertical" initialValues={{ file_name: replacementFileName(document), content: '' }} onFinish={(values: { file_name: string; content: string; ingest_options?: KnowledgeIngestOptions }) => submit(() => replaceDocumentSource(document.id, { file_name: values.file_name.trim(), content: values.content, ingest_options: cleanIngestOptions(values.ingest_options) }), '内容已更新并重新向量化')}>
        <Alert className="knowledge-form-note" type="warning" showIcon title="请提供完整的新正文。保存后将重新分块、重新向量化，并替换旧内容。" />
        <Form.Item name="file_name" label="文件名" tooltip="文件后缀决定 Reader 和分块策略" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item>
        <Form.Item name="content" label="新正文" rules={[{ required: true, whitespace: true }]}><Input.TextArea rows={14} /></Form.Item>
        <IngestOptionsFields />
        <Button loading={pending} type="primary" htmlType="submit" icon={<SyncOutlined />}>保存并重新向量化</Button>
      </Form> },
    ]} />
  </Drawer>
}
