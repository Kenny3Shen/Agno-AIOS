import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
import { SettingsPage } from './SettingsPage'

const admin = { id: 'admin-1', email: 'admin@example.com', role: 'admin', scopes: [], is_active: true }
const chatSettings = {
  show_raw_reasoning: true,
  show_raw_tool_io: true,
  show_thought_chain: true,
  memory_enabled: true,
}
const models = {
  active_model_id: 'first',
  models: [
    {
      id: 'first',
      name: 'First model',
      model_id: 'deepseek-v4-flash',
      provider: 'deepseek',
      api_protocol: 'chat-completions',
      structured_output_mode: 'json',
      default_reasoning_effort: 'max',
      base_url: 'https://api.deepseek.com',
      api_key: 'masked',
      description: '',
      enabled: true,
      builtin: true,
      configured: true,
    },
    {
      id: 'second',
      name: 'Second model',
      model_id: 'gpt-5-mini',
      provider: 'openai',
      api_protocol: 'responses',
      structured_output_mode: 'native',
      default_reasoning_effort: 'high',
      base_url: '',
      api_key: 'masked',
      description: '',
      enabled: true,
      builtin: false,
      configured: true,
    },
  ],
}

const mockSettings = () =>
  server.use(
    http.get('/api/auth/users/me', () => HttpResponse.json(admin)),
    http.get('/api/models', () => HttpResponse.json(models)),
    http.get('/api/settings/chat', () => HttpResponse.json(chatSettings))
  )

describe('model settings editor', () => {
  it('separates model and chat operations into tabs', async () => {
    mockSettings()
    renderWithQuery(<SettingsPage />)

    const modelsTab = (await screen.findByText('模型连接')).closest('[role="tab"]')
    expect(modelsTab?.getAttribute('aria-selected')).toBe('true')
    expect(await screen.findByText('添加模型')).toBeTruthy()
    expect(screen.queryByText('安全执行时间线')).toBeNull()

    const chatTab = (await screen.findByText('Chat 设置')).closest('[role="tab"]')
    expect(chatTab).toBeTruthy()
    fireEvent.click(chatTab!)

    await waitFor(() => expect(chatTab?.getAttribute('aria-selected')).toBe('true'))
    expect(await screen.findByText('安全执行时间线')).toBeTruthy()
    expect(screen.queryByText('添加模型')).toBeNull()
  })

  it('loads the selected model after cancelling a previous edit', async () => {
    mockSettings()
    renderWithQuery(<SettingsPage />)

    fireEvent.click(await screen.findByLabelText('编辑 First model'))
    expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe('First model')
    const cancelButton = document.querySelector<HTMLButtonElement>('.ant-modal-footer .ant-btn-default')
    expect(cancelButton).toBeTruthy()
    fireEvent.click(cancelButton!)

    fireEvent.click(screen.getByLabelText('编辑 Second model'))
    expect(((await screen.findByLabelText('Name')) as HTMLInputElement).value).toBe('Second model')
  })
})
