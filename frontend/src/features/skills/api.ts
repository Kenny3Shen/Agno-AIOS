import { jsonInit, requestJson } from '@/shared/api/client'
import { normalizePaginatedList } from '@/shared/lib/pagination'
import type { ResourceVisibility } from '@/shared/types/common'
export interface Skill {
  name: string
  description: string
  enabled: boolean
  has_scripts: boolean
  scripts: string[]
  attachments?: string[]
  skill_markdown: string
  visibility: ResourceVisibility
  owner_user_id: string
  can_manage: boolean
  can_delete?: boolean
}

/** The result of submitting a skill archive for administrator review. */
export interface UploadApprovalSubmission {
  success?: boolean
  approval_id?: string
  id?: string
  status?: string
}
export const listSkills = async () => {
  const raw = await requestJson<unknown>('/skills')
  const { data } = normalizePaginatedList(raw, {
    mapItem: (row) => {
      if (!row || typeof row !== 'object') return null
      return row as Skill
    },
  })
  return data
}
export const getSkill = (name: string) =>
  requestJson<Skill>(`/skills/${encodeURIComponent(name)}`)
export const toggleSkill = (name: string, enabled: boolean) =>
  requestJson(`/skills/${encodeURIComponent(name)}/toggle`, jsonInit('PUT', { enabled }))
export const setVisibility = (name: string, visibility: ResourceVisibility) =>
  requestJson(`/skills/${encodeURIComponent(name)}/visibility`, jsonInit('PUT', { visibility }))
export const deleteSkill = (name: string) => requestJson<{ success: boolean }>(`/skills/${encodeURIComponent(name)}`, { method: 'DELETE' })
export const uploadSkill = async (name: string, visibility: ResourceVisibility, file: File): Promise<UploadApprovalSubmission> => {
  const body = new FormData()
  body.append('name', name)
  body.append('visibility', visibility)
  body.append('file', file)
  return requestJson<UploadApprovalSubmission>('/skills/upload', { method: 'POST', body })
}

export type SkillWorkflowReference = {
  workflow_id: string
  name: string
  version: string
}

export const listSkillReferences = async (name: string) => {
  const raw = await requestJson<unknown>(`/skills/${encodeURIComponent(name)}/references`)
  const { data } = normalizePaginatedList(raw, {
    mapItem: (row) => {
      if (!row || typeof row !== 'object') return null
      const r = row as Record<string, unknown>
      const id = typeof r.workflow_id === 'string' ? r.workflow_id : ''
      if (!id) return null
      return {
        workflow_id: id,
        name: typeof r.name === 'string' ? r.name : id,
        version: r.version != null ? String(r.version) : '',
      } satisfies SkillWorkflowReference
    },
  })
  return data
}
