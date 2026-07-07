import { useI18n } from 'vue-i18n'

export type ApiFallbackKey =
  | 'cveSearchFailed'
  | 'cveUpdateFailed'
  | 'chatHttpFailed'
  | 'chatSendFailed'
  | 'osControlLoadFailed'
  | 'chatSessionsLoadFailed'
  | 'chatHistoryLoadFailed'
  | 'chatArchiveFailed'
  | 'urlParseFailed'
  | 'settingsLoadFailed'
  | 'settingsUpdateFailed'
  | 'modelsLoadFailed'
  | 'modelsSaveFailed'
  | 'modelsTestFailed'
  | 'tracesLoadFailed'
  | 'traceDetailLoadFailed'
  | 'skillsLoadFailed'
  | 'skillToggleFailed'
  | 'knowledgeRequestFailed'
  | 'knowledgeLoadFailed'
  | 'knowledgeWriteFailed'
  | 'knowledgeImportFailed'
  | 'knowledgeDeleteFailed'
  | 'knowledgeClearFailed'
  | 'knowledgeSearchFailed'
  | 'mcpRequestFailed'
  | 'mcpConfigLoadFailed'
  | 'mcpConfigUpdateFailed'
  | 'mcpTokenLoadFailed'
  | 'mcpTokenIssueFailed'
  | 'mcpTokenDeleteFailed'
  | 'agentEvalsRequestFailed'

export const useApiMessage = () => {
  const { t } = useI18n()
  return (key: ApiFallbackKey, params?: Record<string, string | number>) => {
    return params ? t(`api.errors.${key}`, params) : t(`api.errors.${key}`)
  }
}

export const messageFromUnknown = (err: unknown, fallback: string) => {
  if (err instanceof Error && err.message) return err.message
  return fallback
}

export const messageFromResponse = (data: unknown, fallback: string) => {
  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>
    const detail = record.detail
    const message = record.message
    if (typeof detail === 'string' && detail) return detail
    if (typeof message === 'string' && message) return message
    if (detail && typeof detail === 'object') {
      const detailRecord = detail as Record<string, unknown>
      const detailError = detailRecord.error
      const detailMessage = detailRecord.message
      if (typeof detailError === 'string' && detailError) return detailError
      if (typeof detailMessage === 'string' && detailMessage) return detailMessage
    }
  }
  return fallback
}

export const cleanParam = (value: string | null | undefined) => {
  return (value ?? '').trim()
}
