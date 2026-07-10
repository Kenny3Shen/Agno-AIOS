import { jsonInit, requestJson } from '@/shared/api/client'
import { asArray, asRecord } from '@/shared/lib/format'
import type { Schedule, ScheduleRun } from './types'
const rows = (value: unknown) => asArray(asRecord(value).data ?? value)
export const listSchedules = async () => rows(await requestJson<unknown>('/schedules?limit=100&page=1')) as unknown as Schedule[]
export const createSchedule = (payload: { name: string; cron_expr: string; endpoint: string; description?: string; timezone: string; payload: Record<string, unknown> }) => requestJson<Schedule>('/schedules', jsonInit('POST', { ...payload, method: 'POST' }))
export const setEnabled = (id: string, enabled: boolean) => requestJson(`/schedules/${encodeURIComponent(id)}/${enabled ? 'enable' : 'disable'}`, { method: 'POST' })
export const trigger = (id: string) => requestJson<ScheduleRun>(`/schedules/${encodeURIComponent(id)}/trigger`, { method: 'POST' })
export const remove = (id: string) => requestJson(`/schedules/${encodeURIComponent(id)}`, { method: 'DELETE' })
export const listRuns = async (id: string) => rows(await requestJson<unknown>(`/schedules/${encodeURIComponent(id)}/runs?limit=100&page=1`)) as unknown as ScheduleRun[]
