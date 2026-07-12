import { describe, expect, it } from 'vitest'
import { formatContent } from './FormattedContentCard'

describe('formatted content', () => {
  it('keeps wrapped JSON as one formatted card value', () => {
    expect(formatContent({ format: 'json', text: '{"severity":"high"}', data: null })).toEqual({
      kind: 'json',
      value: { severity: 'high' },
      format: 'json',
    })
  })

  it('detects markdown output', () => {
    expect(formatContent({ format: 'markdown', text: '## Result\n- passed' })).toEqual({
      kind: 'markdown',
      value: '## Result\n- passed',
      format: 'markdown',
    })
  })
})
