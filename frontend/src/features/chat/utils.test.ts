import { describe, expect, it } from 'vitest'
import {
  chatReducer,
  consumeSse,
  defaultReasoningEffort,
  formatSkillLabel,
  formatSkillLabels,
  formatToolLabel,
  humanizeToolId,
  initialChatState,
  normalizeMessages,
  previousPrompt,
  supportedReasoningEfforts,
} from './utils'
import type { Message } from './types'

describe('chat behavior', () => {
  it('keeps stream chunks in arrival order', async () => {
    const encoded = new TextEncoder().encode('data: first\n\ndata: second\n\ndata: [DONE]\n\n')
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoded.slice(0, 17))
        controller.enqueue(encoded.slice(17))
        controller.close()
      },
    })
    const chunks: string[] = []
    await consumeSse(stream, ({ data }) => {
      if (data !== '[DONE]') chunks.push(data)
    })
    expect(chunks).toEqual(['first', 'second'])
  })

  it('preserves a partial answer when a request fails', () => {
    const assistant: Message = { id: 'a', role: 'assistant', content: '', final: false }
    const started = chatReducer(initialChatState, {
      type: 'start',
      user: { id: 'u', role: 'user', content: 'prompt', final: true },
      assistant,
      modelId: 'model',
    })
    const streamed = chatReducer(started, { type: 'event', id: 'a', event: { type: 'content.delta', delta: 'partial' } })
    const failed = chatReducer(streamed, {
      type: 'event',
      id: 'a',
      event: { type: 'run.failed', code: 'NETWORK', message: 'offline', retryable: true },
    })
    expect(failed.messages[failed.messages.length - 1]?.content).toBe('partial')
    expect(failed.messages[failed.messages.length - 1]?.final).toBe(true)
  })

  it('marks a HITL run paused without treating it as an error', () => {
    const assistant: Message = { id: 'a', role: 'assistant', content: '', final: false, status: 'streaming' }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    const paused = chatReducer(started, {
      type: 'event',
      id: 'a',
      event: {
        type: 'run.paused',
        runId: 'run-1',
        sessionId: 's1',
        approvalId: 'approval-1',
        tool: { id: 'simulate_containment', name: 'simulate_containment', status: 'loading' },
      },
    })
    expect(paused.requesting).toBe(false)
    expect(paused.error).toBeNull()
    expect(paused.messages[0]).toMatchObject({ status: 'paused', final: true, approval_id: 'approval-1', run_id: 'run-1' })
  })

  it('finds the prompt that belongs to a retried answer', () => {
    const messages: Message[] = [
      { id: 'u', role: 'user', content: 'inspect', final: true },
      { id: 'a', role: 'assistant', content: 'result', final: true },
    ]
    expect(previousPrompt(messages, 'a')).toBe('inspect')
  })

  it('updates the reasoning effort when changing the model or starting a new chat', () => {
    const selected = chatReducer(initialChatState, { type: 'reasoning-effort', value: 'max' })
    expect(chatReducer(selected, { type: 'model', value: 'model-2', reasoningEffort: 'low' }).reasoningEffort).toBe('low')
    expect(chatReducer(selected, { type: 'reset' }).reasoningEffort).toBeNull()
  })

  it('uses only supported explicit reasoning strengths and selects the configured default', () => {
    const model = {
      id: 'openai',
      name: 'OpenAI',
      model_id: 'gpt',
      provider: 'openai' as const,
      api_protocol: 'responses' as const,
      structured_output_mode: 'native' as const,
      default_reasoning_effort: 'medium' as const,
      base_url: '',
      api_key: '',
      description: '',
      enabled: true,
      builtin: false,
    }
    expect(supportedReasoningEfforts(model)).toEqual(['minimal', 'low', 'medium', 'high'])
    expect(defaultReasoningEffort(model)).toBe('medium')
    expect(defaultReasoningEffort({ ...model, provider: 'openai-compatible' })).toBeNull()
  })

  it('keeps protocol metadata separate from markdown content', () => {
    const assistant: Message = { id: 'a', role: 'assistant', content: '', final: false, status: 'streaming' }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    const withTool = chatReducer(started, {
      type: 'event',
      id: 'a',
      event: { type: 'tool.update', tool: { id: 'lookup', name: 'CVE lookup', status: 'loading' } },
    })
    const completed = chatReducer(withTool, {
      type: 'event',
      id: 'a',
      event: { type: 'run.completed', runId: 'run-1', metrics: { total_tokens: 10 }, followups: ['Assess impact'] },
    })
    expect(completed.messages[0]).toMatchObject({
      content: '',
      run_id: 'run-1',
      status: 'completed',
      tool_steps: [{ id: 'lookup', name: 'CVE lookup', status: 'loading' }],
      followups: ['Assess impact'],
    })
  })

  it('maps Agno PAUSED history status onto chat paused state', () => {
    const messages = normalizeMessages([
      { id: 'a', role: 'assistant', content: '等待管理员审批', status: 'PAUSED', approval_id: 'approval-1' },
      { id: 'b', role: 'assistant', content: 'done', status: 'COMPLETED' },
    ])
    expect(messages[0]).toMatchObject({ status: 'paused', approval_id: 'approval-1' })
    expect(messages[1]).toMatchObject({ status: 'completed' })
  })

  it('clears partial content when the model provider retries', () => {
    const assistant: Message = { id: 'a', role: 'assistant', content: '', final: false, status: 'streaming' }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    const partial = chatReducer(started, { type: 'event', id: 'a', event: { type: 'content.delta', delta: 'partial' } })
    const retrying = chatReducer(partial, {
      type: 'event',
      id: 'a',
      event: { type: 'run.retrying', attempt: 1, maxAttempts: 4, delaySeconds: 2, message: '503' },
    })
    const resumed = chatReducer(retrying, { type: 'event', id: 'a', event: { type: 'content.delta', delta: 'final answer' } })
    expect(retrying.messages[0]).toMatchObject({
      content: '',
      status: 'retrying',
      retry: { attempt: 1, maxAttempts: 4, delaySeconds: 2 },
    })
    expect(resumed.messages[0]).toMatchObject({ content: 'final answer', status: 'streaming', retry: null })
  })

  it('records effective searchKnowledge on run.started', () => {
    const started = chatReducer(initialChatState, {
      type: 'start',
      assistant: { id: 'a', role: 'assistant', content: '', final: false },
      modelId: 'm1',
    })
    const next = chatReducer(started, {
      type: 'event',
      id: 'a',
      event: {
        type: 'run.started',
        runId: 'run-1',
        leanMode: true,
        enableTools: true,
        searchKnowledge: false,
        skillNames: [],
      },
    })
    expect(next.messages[0]).toMatchObject({
      leanMode: true,
      enableTools: true,
      searchKnowledge: false,
      skillNames: [],
    })
  })

  it('sets a soft error without failing messages', () => {
    const next = chatReducer(initialChatState, { type: 'soft-error', message: 'server cancel failed' })
    expect(next.error).toBe('server cancel failed')
    expect(next.messages).toEqual([])
  })

  it('clears a soft error without touching messages', () => {
    const withError = chatReducer(initialChatState, { type: 'soft-error', message: 'server cancel failed' })
    const next = chatReducer(withError, { type: 'clear-error' })
    expect(next.error).toBeNull()
    expect(next.messages).toEqual([])
  })

  it('marks a run cancelled and clears requesting', () => {
    const assistant: Message = { id: 'a', role: 'assistant', content: 'partial', final: false, status: 'streaming' }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    expect(started.requesting).toBe(true)
    const cancelled = chatReducer(started, {
      type: 'event',
      id: 'a',
      event: { type: 'run.cancelled', runId: 'run-1', reason: 'Generation stopped' },
    })
    expect(cancelled.requesting).toBe(false)
    expect(cancelled.messages[0]).toMatchObject({ status: 'cancelled', final: true })
  })

  it('stores leanMode from run.started', () => {
    const assistant: Message = { id: 'a', role: 'assistant', content: '', final: false, status: 'streaming' }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    const next = chatReducer(started, {
      type: 'event',
      id: 'a',
      event: {
        type: 'run.started',
        runId: 'run-lean',
        leanMode: true,
        skillNames: [],
        enableTools: true,
      },
    })
    expect(next.messages[0]).toMatchObject({
      run_id: 'run-lean',
      leanMode: true,
      enableTools: true,
      skillNames: [],
      status: 'streaming',
    })
  })
  it('stores skillNames from run.started', () => {
    const assistant: Message = { id: 'a', role: 'assistant', content: '', final: false, status: 'streaming' }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    const next = chatReducer(started, {
      type: 'event',
      id: 'a',
      event: {
        type: 'run.started',
        runId: 'run-skills',
        leanMode: false,
        skillNames: ['cve-intel-skill', 'playbook-skill'],
        enableTools: true,
      },
    })
    expect(next.messages[0]).toMatchObject({
      run_id: 'run-skills',
      leanMode: false,
      skillNames: ['cve-intel-skill', 'playbook-skill'],
      status: 'streaming',
    })
  })

  it('stores null skillNames for all-enabled skills', () => {
    const assistant: Message = { id: 'a', role: 'assistant', content: '', final: false, status: 'streaming' }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    const next = chatReducer(started, {
      type: 'event',
      id: 'a',
      event: {
        type: 'run.started',
        runId: 'run-all',
        leanMode: false,
        skillNames: null,
        enableTools: true,
      },
    })
    expect(next.messages[0]).toMatchObject({
      run_id: 'run-all',
      leanMode: false,
      skillNames: null,
    })
  })

  it('normalizeMessages projects lean_mode, enable_tools and skill_names from history', () => {
    const messages = normalizeMessages([
      {
        id: 'run-1',
        role: 'assistant',
        content: 'pong',
        status: 'completed',
        lean_mode: true,
        enable_tools: true,
        search_knowledge: false,
        skill_names: [],
      },
      {
        id: 'run-2',
        role: 'assistant',
        content: 'ok',
        status: 'completed',
        lean_mode: false,
        enable_tools: true,
        search_knowledge: true,
        skill_names: ['cve-intel-skill'],
      },
      {
        id: 'run-3',
        role: 'assistant',
        content: 'full',
        status: 'completed',
        lean_mode: false,
        enable_tools: true,
        search_knowledge: true,
        skill_names: null,
      },
      {
        id: 'run-4',
        role: 'assistant',
        content: 'hi',
        status: 'completed',
        lean_mode: false,
        enable_tools: false,
        search_knowledge: false,
        skill_names: [],
      },
    ])
    expect(messages[0]).toMatchObject({ leanMode: true, enableTools: true, searchKnowledge: false, skillNames: [] })
    expect(messages[1]).toMatchObject({ leanMode: false, enableTools: true, searchKnowledge: true, skillNames: ['cve-intel-skill'] })
    expect(messages[2]).toMatchObject({ leanMode: false, enableTools: true, searchKnowledge: true, skillNames: null })
    expect(messages[3]).toMatchObject({ leanMode: false, enableTools: false, searchKnowledge: false, skillNames: [] })
  })

})

describe('formatSkillLabel', () => {
  it('strips -skill and title-cases segments', () => {
    expect(formatSkillLabel('cve-intel-skill')).toBe('CVE Intel')
    expect(formatSkillLabel('playbook-skill')).toBe('Playbook')
    expect(formatSkillLabel('hitl-containment-skill')).toBe('HITL Containment')
    expect(formatSkillLabel('intranet-ip-skill')).toBe('Intranet IP')
  })

  it('joins multiple labels', () => {
    expect(formatSkillLabels(['cve-intel-skill', 'playbook-skill'])).toBe('CVE Intel, Playbook')
  })
})

describe('formatToolLabel', () => {
  const t = (key: string) =>
    ({
      'tools.hitl_simulate_containment': '模拟隔离资产',
      'tools.basic_send_feishu_notify': '发送飞书通知',
      'tools.playbook_list_workflows': '列出剧本',
      'tools.get_skill_instructions': '读取 Skill 说明',
    }[key] ?? key)

  it('maps builtin MCP tools via i18n', () => {
    expect(formatToolLabel('hitl_simulate_containment', t)).toBe('模拟隔离资产')
    expect(formatToolLabel('basic_send_feishu_notify', t)).toBe('发送飞书通知')
    expect(formatToolLabel('playbook_list_workflows', t)).toBe('列出剧本')
    expect(formatToolLabel('get_skill_instructions', t)).toBe('读取 Skill 说明')
  })

  it('humanizes unknown tool ids', () => {
    expect(humanizeToolId('external_lookup_asset')).toBe('External Lookup Asset')
    expect(formatToolLabel('hitl_custom_action')).toBe('Custom Action')
  })
})
