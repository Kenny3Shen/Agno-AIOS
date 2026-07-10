import { describe, expect, it } from 'vitest'
import { getSkillBody, getSkillDetailMetadata, getSkillFrontMatter } from './utils'

describe('skill content', () => {
  it('returns the body without front matter metadata', () => {
    const body = getSkillBody('---\nname: scanner\ndescription: metadata\nvisibility: private\n---\n# Instructions\nInspect the target.')

    expect(body).toContain('# Instructions')
    expect(body).not.toContain('visibility:')
    expect(body).not.toContain('description:')
  })

  it('summarizes protocol metadata without reading implementation files', () => {
    const frontMatter = getSkillFrontMatter('---\nname: scanner\nattachments:\n- assets/prompt.md\n---\nBody')
    expect(frontMatter.attachments).toEqual(['assets/prompt.md'])

    const metadata = getSkillDetailMetadata({
      name: 'scanner',
      description: '',
      enabled: true,
      has_scripts: true,
      scripts: ['scan.py'],
      attachments: ['assets/prompt.md', 'references/runbook.md'],
      skill_markdown: '---\nname: scanner\n---\nBody',
      visibility: 'private',
      owner_user_id: 'u1',
      can_manage: true,
    })

    expect(metadata.script_count).toBe(1)
    expect(metadata.attachment_count).toBe(2)
  })
})
