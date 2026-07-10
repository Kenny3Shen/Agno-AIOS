import { describe, expect, it } from 'vitest'
import { parseMemoryInput } from './utils'

describe('memory metadata', () => {
  it('extracts additional context without exposing its JSON wrapper', () => {
    expect(parseMemoryInput('Focus on alerts\n<additional context>\n{"channel":"security"}\n</additional context>')).toEqual({
      text: 'Focus on alerts',
      context: { channel: 'security' },
    })
  })
})
