import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Button, Card, Input, Tabs } from 'antd'
import XMarkdown from '@ant-design/x-markdown'
import { CloudDownloadOutlined } from '@ant-design/icons'
import { PageHeader } from '@/shared/ui/PageHeader'
import { parseUrl } from './api'

export function CollectPage() {
  const [url, setUrl] = useState('')
  const mutation = useMutation({ mutationFn: () => parseUrl(url) })
  const markdown = Array.isArray(mutation.data?.markdown) ? mutation.data.markdown.join('\n\n') : mutation.data?.markdown ?? ''
  return <main className="page"><PageHeader title="Web Collect" description="将网页内容转换为可审阅的 Markdown 资产" actions={<Button type="primary" icon={<CloudDownloadOutlined />} disabled={!url} loading={mutation.isPending} onClick={() => mutation.mutate()}>采集</Button>} />
    <Card className="workbench-card"><Input value={url} onChange={(event) => setUrl(event.target.value)} onPressEnter={() => mutation.mutate()} placeholder="https://example.com/advisory" />
      <Tabs style={{ marginTop: 12 }} items={[{ key: 'markdown', label: 'Markdown', children: <Input.TextArea value={markdown} onChange={() => undefined} autoSize={{ minRows: 18 }} /> }, { key: 'preview', label: 'Preview', children: <div className="payload-viewer"><XMarkdown content={markdown} openLinksInNewTab escapeRawHtml /></div> }]} />
    </Card>
  </main>
}
