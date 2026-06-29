import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const componentSource = readFileSync(
  new URL('./security-platform.tsx', import.meta.url),
  'utf8',
)
const stylesSource = readFileSync(
  new URL('../styles.css', import.meta.url),
  'utf8',
)

describe('security platform workspace contracts', () => {
  it('uses streaming-safe markdown rendering for workspace markdown', () => {
    expect(componentSource).toContain("from 'streamdown'")
    expect(componentSource).toContain('<Streamdown')
    expect(componentSource).not.toContain('dangerouslySetInnerHTML')
  })

  it('keeps the agent input resizable', () => {
    expect(componentSource).toContain('resize-y')
  })

  it('removes the destructive clear-knowledge entry from the RAG panel', () => {
    expect(componentSource).not.toContain('clearKnowledgeDocuments')
    expect(componentSource).not.toContain('清空知识库')
  })

  it('defines dark-mode aware scrollbar styling', () => {
    expect(stylesSource).toContain('scrollbar-color')
    expect(stylesSource).toContain('.dark *::-webkit-scrollbar-thumb')
  })
})
