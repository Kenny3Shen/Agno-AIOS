import { jsonInit, requestJson } from '@/shared/api/client'
export interface Cve { id: number; cve_id: string; github_url: string; description: string; source: string; create_time: string }
export const searchCves = (payload: { query: string; source?: string; page: number; size: number }) => requestJson<{ items: Cve[]; total: number }>('/cve/search', jsonInit('POST', payload))
export const updateCves = () => requestJson<Record<string, unknown>>('/cve/update', { method: 'POST' })
