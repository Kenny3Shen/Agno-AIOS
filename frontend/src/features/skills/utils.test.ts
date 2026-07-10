import { describe, expect, it } from 'vitest'
import { getSkillBody } from './utils'

describe('skill content', () => {
  it('returns the body without front matter metadata', () => {
    const body = getSkillBody('---\nname: scanner\ndescription: metadata\nvisibility: private\n---\n# Instructions\nInspect the target.')

    expect(body).toContain('# Instructions')
    expect(body).not.toContain('visibility:')
    expect(body).not.toContain('description:')
  })
})
