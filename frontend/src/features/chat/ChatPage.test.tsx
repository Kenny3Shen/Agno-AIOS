import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithQuery } from '@/test/render'
import { ChatPage } from './ChatPage'

const longModelName = 'enterprise-security-analysis-model-with-an-intentionally-long-display-name'

const chat = {
  state: { messages: [], input: '', requesting: false, error: null, selectedModelId: 'long', reasoningEffort: null },
  sessionId: null,
  sessions: { data: [] },
  history: { data: [] },
  models: {
    isLoading: false,
    data: {
      active_model_id: 'long',
      models: [
        { id: 'short', name: 'GPT Mini', model_id: 'gpt-mini', provider: 'openai', api_protocol: 'responses', structured_output_mode: 'native', base_url: '', api_key: '', description: '', enabled: true, builtin: false, configured: true },
        { id: 'long', name: longModelName, model_id: 'security-model', provider: 'openai', api_protocol: 'responses', structured_output_mode: 'native', base_url: '', api_key: '', description: '', enabled: true, builtin: false, configured: true },
      ],
    },
  },
  selectedModel: { id: 'long', name: longModelName, model_id: 'security-model', provider: 'openai', api_protocol: 'responses', structured_output_mode: 'native', base_url: '', api_key: '', description: '', enabled: true, builtin: false, configured: true },
  dispatch: vi.fn(), setSession: vi.fn(), setModel: vi.fn(), setReasoningEffort: vi.fn(), submit: vi.fn(), retry: vi.fn(), newChat: vi.fn(), cancel: vi.fn(),
}

vi.mock('@tanstack/react-router', async (importOriginal) => ({
  ...await importOriginal<typeof import('@tanstack/react-router')>(),
  useRouter: () => ({ history: { push: vi.fn() } }),
}))
vi.mock('./useChat', () => ({ useChat: () => chat }))

describe('chat model selector', () => {
  beforeEach(() => {
    HTMLElement.prototype.scrollTo = vi.fn()
  })

  it('keeps the full selected model name available while preserving model selection', async () => {
    const user = userEvent.setup()
    renderWithQuery(<ChatPage />)

    expect(document.querySelector('.model-select-value')?.getAttribute('title')).toBe(longModelName)
    await user.click(screen.getByRole('combobox', { name: '模型' }))
    expect(await screen.findByRole('option', { name: 'GPT Mini' })).toBeTruthy()
  })

})
