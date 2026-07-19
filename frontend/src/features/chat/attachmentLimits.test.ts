import { describe, expect, it } from 'vitest'
import {
  MAX_CHAT_FILES,
  formatAttachmentLimitError,
  validateChatAttachments,
} from './attachmentLimits'

const t = (key: string, opts?: Record<string, unknown>) =>
  opts ? `${key}:${JSON.stringify(opts)}` : key

describe('validateChatAttachments', () => {
  it('accepts a small text file', () => {
    const file = new File(['hello'], 'note.txt', { type: 'text/plain' })
    expect(validateChatAttachments([file])).toBeNull()
  })

  it('rejects too many files', () => {
    const files = Array.from({ length: MAX_CHAT_FILES + 1 }, (_, i) => new File(['x'], `f${i}.txt`))
    expect(validateChatAttachments(files)).toEqual({ code: 'too_many', max: MAX_CHAT_FILES })
  })

  it('rejects oversized file', () => {
    const big = new File([new Uint8Array(20 * 1024 * 1024 + 1)], 'big.bin')
    expect(validateChatAttachments([big])).toMatchObject({ code: 'file_too_large', name: 'big.bin' })
  })

  it('formats errors for toast/i18n', () => {
    expect(formatAttachmentLimitError({ code: 'too_many', max: 8 }, t)).toContain('attachmentsTooMany')
  })
})
