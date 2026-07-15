import { Button, Empty, Space } from 'antd'
import { CopyOutlined } from '@ant-design/icons'
import { Markdown } from '@/shared/ui/Markdown'
import { copyToClipboard } from '@/shared/lib/clipboard'

export function PayloadViewer({ value, markdown = false }: { value: unknown; markdown?: boolean }) {
  const text = typeof value === 'string' ? value : value == null ? '' : JSON.stringify(value, null, 2)
  if (!text) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
  return (
    <div className="payload-viewer">
      <Space className="payload-actions">
        <Button type="text" icon={<CopyOutlined />} onClick={() => void copyToClipboard(text)} />
      </Space>
      {markdown ? <Markdown content={text} openLinksInNewTab escapeRawHtml /> : <pre>{text}</pre>}
    </div>
  )
}
