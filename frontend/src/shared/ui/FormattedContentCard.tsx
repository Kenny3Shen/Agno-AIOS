import { Button, Card, Empty, Tag, Typography } from 'antd'
import { CopyOutlined } from '@ant-design/icons'
import XMarkdown from '@ant-design/x-markdown'
import { copyToClipboard } from '@/shared/lib/clipboard'

type ContentKind = 'empty' | 'json' | 'markdown' | 'text'

export interface FormattedContent {
  kind: ContentKind
  value: unknown
  format: string
}

const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value)

const parseJsonText = (value: string): unknown => {
  const text = value.trim()
  if (!(text.startsWith('{') || text.startsWith('['))) return undefined
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

const looksLikeMarkdown = (value: string) => /(^|\n)#{1,6}\s|```|\*\*[^*]+\*\*|(^|\n)\s*[-*]\s+/m.test(value)

export function formatContent(value: unknown): FormattedContent {
  let format = ''
  let content = value
  if (isRecord(value) && ('format' in value || 'text' in value || 'data' in value)) {
    format = String(value.format ?? '').toLowerCase()
    content = value.data ?? value.text
  }
  if (content === undefined || content === null || content === '') return { kind: 'empty', value: null, format: format || 'empty' }
  if (typeof content !== 'string') return { kind: 'json', value: content, format: format || 'json' }
  const parsed = parseJsonText(content)
  if (parsed !== undefined) return { kind: 'json', value: parsed, format: format || 'json' }
  if (format.includes('markdown') || looksLikeMarkdown(content)) return { kind: 'markdown', value: content, format: format || 'markdown' }
  return { kind: 'text', value: content, format: format || 'text' }
}

export function JsonValueCard({ value, title = 'JSON' }: { value: unknown; title?: string }) {
  const text = JSON.stringify(value, null, 2)
  return <Card className="formatted-content-card json-value-card" size="small" title={title} extra={<Button type="text" size="small" aria-label={`Copy ${title}`} icon={<CopyOutlined />} onClick={() => void copyToClipboard(text)} />}>
    <pre>{text}</pre>
  </Card>
}

export function FormattedContentCard({ value, title }: { value: unknown; title: string }) {
  const content = formatContent(value)
  if (content.kind === 'empty') return <Card className="formatted-content-card" size="small" title={title}><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={false} /></Card>
  if (content.kind === 'json') return <JsonValueCard value={content.value} title={title} />
  return <Card className="formatted-content-card" size="small" title={title} extra={<Tag>{content.format}</Tag>}>
    {content.kind === 'markdown'
      ? <XMarkdown content={String(content.value)} openLinksInNewTab escapeRawHtml />
      : <Typography.Paragraph className="formatted-text">{String(content.value)}</Typography.Paragraph>}
  </Card>
}
