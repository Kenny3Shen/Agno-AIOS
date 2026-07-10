import { jsonInit, requestJson } from '@/shared/api/client'
export const parseUrl = (url: string) => requestJson<{ markdown?: string | string[] }>('/url2md/parse', jsonInit('POST', { url }))
