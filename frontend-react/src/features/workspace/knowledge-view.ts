export type KnowledgeMetadataBadge = {
  key: string
  value: string
  title: string
}

function compactMetadataValue(value: string, maxLength = 62) {
  if (value.length <= maxLength) return value
  return `${value.slice(0, maxLength - 3)}...`
}

export function formatKnowledgeMetadataBadges(
  metadata: Record<string, string> | undefined,
): KnowledgeMetadataBadge[] {
  return Object.entries(metadata ?? {}).map(([key, value]) => {
    const normalizedValue = String(value)
    return {
      key,
      value: compactMetadataValue(normalizedValue),
      title: `${key}: ${normalizedValue}`,
    }
  })
}
