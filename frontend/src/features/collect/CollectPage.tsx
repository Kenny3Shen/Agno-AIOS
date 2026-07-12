import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Button, Card, Input, Space, Splitter } from 'antd'
import XMarkdown from '@ant-design/x-markdown'
import { CloudDownloadOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { parseUrl } from './api'

export function CollectPage() {
  const [url, setUrl] = useState('')
  const mutation = useMutation({ mutationFn: () => parseUrl(url) })
  const markdown = Array.isArray(mutation.data?.markdown) ? mutation.data.markdown.join('\n\n') : (mutation.data?.markdown ?? '')
  return (
    <main className="page">
      <PageHeader title="Web Collect" description="将网页内容转换为可审阅的 Markdown 资产" />
      <Card className="workbench-card collect-card">
        <Space.Compact className="collect-toolbar">
          <Input
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            onPressEnter={() => mutation.mutate()}
            placeholder="https://example.com/advisory"
          />
          <Button
            type="primary"
            icon={<CloudDownloadOutlined />}
            disabled={!url}
            loading={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            采集
          </Button>
        </Space.Compact>
        <Splitter className="workbench-splitter collect-splitter" orientation="horizontal">
          <Splitter.Panel defaultSize="50%" min="30%">
            <Card className="workbench-card splitter-panel-card" size="small" title="Markdown">
              <Input.TextArea className="collect-markdown-editor" value={markdown} onChange={() => undefined} />
            </Card>
          </Splitter.Panel>
          <Splitter.Panel defaultSize="50%" min="30%">
            <Card className="workbench-card splitter-panel-card" size="small" title="Preview">
              <div className="payload-viewer collect-preview">
                <XMarkdown content={markdown} openLinksInNewTab escapeRawHtml />
              </div>
            </Card>
          </Splitter.Panel>
        </Splitter>
      </Card>
    </main>
  )
}
