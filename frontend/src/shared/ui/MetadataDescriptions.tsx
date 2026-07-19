import { Descriptions, Space, Tag, Typography, type DescriptionsProps } from 'antd'
import { JsonValueCard } from './FormattedContentCard'

interface MetadataEntry {
  key: string
  label: string
  value: unknown
}

const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value)

const metadataLabel = (path: string) =>
  path
    .split(' / ')
    .map((segment) => {
      const words = segment.replaceAll('_', ' ')
      const capitalized = words ? `${words[0]!.toUpperCase()}${words.slice(1)}` : words
      return capitalized.replace(/\bid\b/gi, 'ID')
    })
    .join(' / ')

function flattenMetadata(value: unknown, prefix = ''): MetadataEntry[] {
  if (value === undefined && !prefix) return []
  if (isRecord(value)) {
    const entries = Object.entries(value)
    if (entries.length === 0) return prefix ? [{ key: prefix, label: metadataLabel(prefix), value: null }] : []
    return entries.map(([key, child]) => {
      const path = prefix ? `${prefix} / ${key}` : key
      return { key: path, label: metadataLabel(path), value: child }
    })
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return prefix ? [{ key: prefix, label: metadataLabel(prefix), value: null }] : []
    return [{ key: prefix || 'Value', label: metadataLabel(prefix || 'Value'), value }]
  }
  return [{ key: prefix || 'Value', label: metadataLabel(prefix || 'Value'), value }]
}

export function CopyableValue({ value }: { value?: string | null }) {
  const text = value?.trim() || '-'
  return (
    <Typography.Text className="metadata-copyable" copyable={text === '-' ? false : { text }}>
      {text}
    </Typography.Text>
  )
}

function MetadataValue({ value }: { value: unknown }) {
  if (value === undefined || value === null || value === '') return <>-</>
  if (typeof value === 'boolean') return <Tag color={value ? 'success' : 'default'}>{value ? 'true' : 'false'}</Tag>
  if (Array.isArray(value) && value.every((item) => item == null || ['string', 'number', 'boolean'].includes(typeof item)))
    return (
      <Space wrap>
        {value.map((item, index) => (
          <Tag key={`${String(item)}-${index}`}>{String(item)}</Tag>
        ))}
      </Space>
    )
  if (Array.isArray(value) || isRecord(value)) return <JsonValueCard value={value} />
  return <Typography.Paragraph className="metadata-value">{String(value)}</Typography.Paragraph>
}

export function MetadataDescriptions({
  items = [],
  value,
  prefix,
}: {
  items?: DescriptionsProps['items']
  value?: unknown
  prefix?: string
}) {
  const metadataItems: DescriptionsProps['items'] = flattenMetadata(value, prefix).map((entry) => ({
    key: `metadata-${entry.key}`,
    label: entry.label,
    children: <MetadataValue value={entry.value} />,
  }))
  return <Descriptions className="metadata-descriptions" bordered column={1} size="small" items={[...items, ...metadataItems]} />
}
