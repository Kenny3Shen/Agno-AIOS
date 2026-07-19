import { describe, expect, it } from 'vitest'
import { getSkillBody, getSkillDetailMetadata } from './utils'

describe('skill content', () => {
  it('returns the body without front matter metadata', () => {
    const body = getSkillBody('---\nname: scanner\ndescription: metadata\nvisibility: private\n---\n# Instructions\nInspect the target.')

    expect(body).toContain('# Instructions')
    expect(body).not.toContain('visibility:')
    expect(body).not.toContain('description:')
  })

  it('summarizes protocol metadata without reading implementation files', () => {
    const metadata = getSkillDetailMetadata({
      name: 'scanner',
      description: '',
      enabled: true,
      has_scripts: true,
      scripts: ['scan.py'],
      attachments: ['assets/prompt.md', 'references/runbook.md'],
      skill_markdown: '---\nname: scanner\nattachments:\n- assets/prompt.md\n---\nBody',
      visibility: 'private',
      owner_user_id: 'u1',
      can_manage: true,
    })

    expect(metadata.script_count).toBe(1)
    expect(metadata.attachment_count).toBe(2)
    expect(metadata.protocol_metadata.attachments).toEqual(['assets/prompt.md'])
  })
})
