/** Client-side chat attachment limits (aligned with api/services/chat_media.py). */

export const MAX_CHAT_FILES = 8
export const MAX_CHAT_FILE_BYTES = 20 * 1024 * 1024
export const MAX_CHAT_TOTAL_BYTES = 40 * 1024 * 1024

export type AttachmentLimitError =
  | { code: 'too_many'; max: number }
  | { code: 'file_too_large'; name: string; maxMb: number }
  | { code: 'total_too_large'; maxMb: number }
  | { code: 'empty_file'; name: string }

export function validateChatAttachments(files: File[]): AttachmentLimitError | null {
  if (files.length > MAX_CHAT_FILES) {
    return { code: 'too_many', max: MAX_CHAT_FILES }
  }
  let total = 0
  for (const file of files) {
    if (file.size <= 0) {
      return { code: 'empty_file', name: file.name || 'file' }
    }
    if (file.size > MAX_CHAT_FILE_BYTES) {
      return { code: 'file_too_large', name: file.name || 'file', maxMb: MAX_CHAT_FILE_BYTES / (1024 * 1024) }
    }
    total += file.size
    if (total > MAX_CHAT_TOTAL_BYTES) {
      return { code: 'total_too_large', maxMb: MAX_CHAT_TOTAL_BYTES / (1024 * 1024) }
    }
  }
  return null
}

export function formatAttachmentLimitError(
  error: AttachmentLimitError,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  switch (error.code) {
    case 'too_many':
      return t('attachmentsTooMany', { max: error.max })
    case 'file_too_large':
      return t('attachmentsFileTooLarge', { name: error.name, maxMb: error.maxMb })
    case 'total_too_large':
      return t('attachmentsTotalTooLarge', { maxMb: error.maxMb })
    case 'empty_file':
      return t('attachmentsEmptyFile', { name: error.name })
    default:
      return t('attachmentsInvalid')
  }
}
