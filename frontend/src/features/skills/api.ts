import { apiFetch, jsonInit, requestJson } from '@/shared/api/client'
import type { ResourceVisibility } from '@/shared/types/common'
export interface Skill { name: string; description: string; enabled: boolean; has_scripts: boolean; scripts: string[]; skill_markdown: string; visibility: ResourceVisibility; owner_user_id: string; can_manage: boolean }
export const listSkills = async () => (await requestJson<{ skills: Skill[] }>('/skills')).skills
export const toggleSkill = (name: string, enabled: boolean) => requestJson(`/skills/${encodeURIComponent(name)}/toggle`, jsonInit('PUT', { enabled }))
export const setVisibility = (name: string, visibility: ResourceVisibility) => requestJson(`/skills/${encodeURIComponent(name)}/visibility`, jsonInit('PUT', { visibility }))
export const uploadSkill = async (name: string, visibility: ResourceVisibility, file: File) => { const body = new FormData(); body.append('name', name); body.append('visibility', visibility); body.append('file', file); const response = await apiFetch('/skills/upload', { method: 'POST', body }); if (!response.ok) throw new Error('Upload failed'); return response.json() }
