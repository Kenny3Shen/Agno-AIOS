import type { ChatSession } from './types'

export const chatSessionFixture = (
  { session_id, ...overrides }: Partial<ChatSession> & { session_id: string },
): ChatSession => ({
  session_id,
  user_id: null,
  session_type: 'agent',
  workflow_id: null,
  agent_id: null,
  team_id: null,
  preview: 'run',
  title: null,
  created_at: 1,
  updated_at: 2,
  archived: false,
  ...overrides,
})
