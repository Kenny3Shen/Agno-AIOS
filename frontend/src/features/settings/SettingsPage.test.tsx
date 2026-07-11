import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import userEvent from '@testing-library/user-event'
import { screen } from '@testing-library/react'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
import { SettingsPage } from './SettingsPage'

const models = {
  active_model_id: 'first',
  models: [
    {
      id: 'first', name: 'First model', model_id: 'deepseek-v4-flash', provider: 'deepseek',
      api_protocol: 'chat-completions', structured_output_mode: 'json', default_reasoning_effort: 'max',
      base_url: 'https://api.deepseek.com', api_key: 'masked', description: '', enabled: true, builtin: true, configured: true,
    },
    {
      id: 'second', name: 'Second model', model_id: 'gpt-5-mini', provider: 'openai',
      api_protocol: 'responses', structured_output_mode: 'native', default_reasoning_effort: 'high',
      base_url: '', api_key: 'masked', description: '', enabled: true, builtin: false, configured: true,
    },
  ],
}

describe('model settings editor', () => {
  it('loads the selected model after cancelling a previous edit', async () => {
    const user = userEvent.setup()
    server.use(http.get('/api/models', () => HttpResponse.json(models)))
    renderWithQuery(<SettingsPage />)

    await user.click(await screen.findByLabelText('编辑 First model'))
    expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe('First model')
    await user.click(screen.getByRole('button', { name: /取\s*消/ }))

    await user.click(screen.getByLabelText('编辑 Second model'))
    expect((await screen.findByLabelText('Name') as HTMLInputElement).value).toBe('Second model')
  })
})
