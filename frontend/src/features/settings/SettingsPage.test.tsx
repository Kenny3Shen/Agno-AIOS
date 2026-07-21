import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { renderWithQuery } from '@/test/render'
import { server } from '@/test/server'
import { SettingsPage } from './SettingsPage'
import type { ModelConfigResponse } from '@/shared/types/common'
import type { ModelConfigUpdatePayload } from './api'

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
      parallel_tool_calls: null,
      live_search_enabled: false,
      retries: 4,
      delay_between_retries: 1,
      exponential_backoff: true,
      http_max_retries: null,
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
      parallel_tool_calls: false,
      live_search_enabled: false,
      retries: 4,
      delay_between_retries: 1,
      exponential_backoff: true,
      http_max_retries: null,
      base_url: '',
      api_key: 'masked',
      description: '',
      enabled: true,
      builtin: false,
      configured: true,
    },
  ],
} satisfies ModelConfigResponse

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
    // Grouped collapse panels (privacy + memory open by default).
    expect(await screen.findByText('展示与隐私')).toBeTruthy()
    expect(await screen.findByText('长期记忆')).toBeTruthy()
    expect(await screen.findByText('上下文与输出')).toBeTruthy()
    expect(await screen.findByText('工具调用')).toBeTruthy()
    expect(await screen.findByText('安全执行时间线')).toBeTruthy()
    expect(screen.queryByText('添加模型')).toBeNull()
  })

  it('loads the selected model after cancelling a previous edit', async () => {
    mockSettings()
    renderWithQuery(<SettingsPage />)

    fireEvent.click(await screen.findByLabelText('编辑 First model'))
    expect((screen.getByLabelText('显示名称') as HTMLInputElement).value).toBe('First model')
    const cancelButton = document.querySelector<HTMLButtonElement>('.ant-modal-footer .ant-btn-default')
    expect(cancelButton).toBeTruthy()
    fireEvent.click(cancelButton!)

    fireEvent.click(screen.getByLabelText('编辑 Second model'))
    expect(((await screen.findByLabelText('显示名称')) as HTMLInputElement).value).toBe('Second model')
  })

  it('submits connection fields without hardcoding provider runtime defaults', async () => {
    let saved: ModelConfigUpdatePayload | undefined
    mockSettings()
    server.use(
      http.put('/api/models', async ({ request }) => {
        saved = (await request.json()) as ModelConfigUpdatePayload
        return HttpResponse.json(models)
      })
    )
    renderWithQuery(<SettingsPage />)

    fireEvent.click(await screen.findByText('添加模型'))
    expect(await screen.findByLabelText('显示名称')).toBeTruthy()
    expect(await screen.findByLabelText('Model ID')).toBeTruthy()
    expect(await screen.findByLabelText('API Key')).toBeTruthy()
    expect(screen.queryByText('并行工具调用')).toBeNull()
    expect(screen.queryByText('请求重试次数')).toBeNull()
    expect(screen.queryByText('API protocol')).toBeNull()
    expect(await screen.findByText(/按供应商最优默认自动配置/)).toBeTruthy()

    fireEvent.change(screen.getByLabelText('显示名称'), { target: { value: 'Gateway model' } })
    fireEvent.change(screen.getByLabelText('Model ID'), { target: { value: 'gateway-model' } })
    fireEvent.change(screen.getByLabelText('API Key'), { target: { value: 'gateway-key' } })
    fireEvent.change(screen.getByLabelText('Base URL'), { target: { value: 'https://api.example.com/v1' } })
    fireEvent.click(screen.getByRole('button', { name: '保存模型' }))

    await waitFor(() => expect(saved).toBeTruthy())
    const created = saved!.models.find((model) => model.name === 'Gateway model')
    expect(created).toMatchObject({
      model_id: 'gateway-model',
      provider: 'openai-compatible',
      base_url: 'https://api.example.com/v1',
      api_key: 'gateway-key',
      enabled: true,
      builtin: false,
    })
    ;[
      'api_protocol',
      'structured_output_mode',
      'default_reasoning_effort',
      'parallel_tool_calls',
      'live_search_enabled',
      'retries',
      'delay_between_retries',
      'exponential_backoff',
      'http_max_retries',
      'description',
    ].forEach((field) => expect(created).not.toHaveProperty(field))
  })

  it('deletes a custom model and keeps the active model valid', async () => {
    let saved: ModelConfigResponse | undefined
    mockSettings()
    server.use(
      http.put('/api/models', async ({ request }) => {
        saved = (await request.json()) as ModelConfigResponse
        return HttpResponse.json(saved)
      })
    )
    renderWithQuery(<SettingsPage />)

    fireEvent.click(await screen.findByLabelText('删除 Second model'))
    const ok = await screen.findByRole('button', { name: '删除模型' })
    fireEvent.click(ok)

    await waitFor(() => {
      expect(saved).toBeTruthy()
      expect(saved!.models.map((m) => m.id)).toEqual(['first'])
      expect(saved!.active_model_id).toBe('first')
    })
  })

  it('does not allow deleting built-in models', async () => {
    mockSettings()
    renderWithQuery(<SettingsPage />)
    const btn = await screen.findByLabelText('删除 First model')
    expect(btn.hasAttribute('disabled') || btn.getAttribute('disabled') === '').toBe(true)
  })
})
