export interface MemoryInputParts {
  text: string
  context: Record<string, unknown>
}

export function parseMemoryInput(value?: string): MemoryInputParts {
  const input = value?.trim() ?? ''
  const match = input.match(/<additional context>\s*([\s\S]*?)\s*<\/additional context>/i)
  if (!match) return { text: input, context: {} }
  const text = input.replace(match[0], '').trim()
  try {
    const parsed = JSON.parse(match[1] ?? '')
    return { text, context: parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {} }
  } catch {
    return { text: input, context: {} }
  }
}
