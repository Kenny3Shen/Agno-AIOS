import type { Skill } from './api'

export function getSkillBody(markdown: string) {
  return markdown.replace(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/, '').trim()
}

export function getSkillFrontMatter(markdown: string): Record<string, string | string[]> {
  const match = markdown.match(/^---\r?\n([\s\S]*?)\r?\n---/)
  if (!match) return {}
  const metadata: Record<string, string | string[]> = {}
  let currentKey = ''
  for (const rawLine of match[1]!.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) continue
    if (line.startsWith('- ') && currentKey) {
      const current = metadata[currentKey]
      const next = line.slice(2).trim()
      metadata[currentKey] = Array.isArray(current) ? [...current, next] : [next]
      continue
    }
    const separator = line.indexOf(':')
    if (separator < 0) continue
    currentKey = line.slice(0, separator).trim()
    const value = line.slice(separator + 1).trim()
    metadata[currentKey] = value.replace(/^['"]|['"]$/g, '')
  }
  return metadata
}

export function getSkillDetailMetadata(skill: Skill) {
  const frontMatter = getSkillFrontMatter(skill.skill_markdown)
  const attachments = skill.attachments ?? []
  return {
    script_count: skill.scripts.length,
    scripts: skill.scripts,
    attachment_count: attachments.length,
    attachments,
    protocol_metadata: frontMatter,
  }
}
