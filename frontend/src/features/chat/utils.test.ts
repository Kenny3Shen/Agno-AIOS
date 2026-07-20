import { describe, expect, it } from 'vitest'
import {
  formatRetryDetail,
  chatReducer,
  consumeSse,
  defaultReasoningEffort,
  formatSkillLabels,
  formatToolLabel,
  initialChatState,
  normalizeMessages,
  previousPrompt,
  supportedReasoningEfforts,
  isKnowledgeToggleActive,
  isLiveSearchToggleActive,
} from './utils'
import type { Message } from './types'

const translateToolLabel = (key: string) =>
  ({
    'tools.hitl_simulate_containment': '模拟隔离资产',
    'tools.basic_send_feishu_notify': '发送飞书通知',
    'tools.get_skill_instructions': '读取 Skill 说明',
  }[key] ?? key)

const translateRetryDetail = (key: string, options?: Record<string, unknown>) => {
  if (key === 'retryingDetailWithDelay') {
    return `retry ${options?.attempt}/${options?.max} in ${options?.seconds}s`
  }
  if (key === 'retryingDetail') {
    return `retry ${options?.attempt}/${options?.max}`
  }
  if (key === 'establishingRun') return 'starting'
  return key
}

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

  it('aborts SSE consumption when signal is aborted', async () => {
    const stream = new ReadableStream<Uint8Array>({
      start() {
        // never enqueues — wait for cancel
      },
      cancel() {
        // ok
      },
    })
    const controller = new AbortController()
    const pending = consumeSse(stream, () => undefined, controller.signal)
    controller.abort()
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
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

  it('updates the reasoning effort when changing the model', () => {
    const selected = chatReducer(initialChatState, { type: 'reasoning-effort', value: 'max' })
    expect(chatReducer(selected, { type: 'model', value: 'model-2', reasoningEffort: 'low' }).reasoningEffort).toBe('low')
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
      // Terminal run finalizes in-flight tool/thought steps (Team beta).
      tool_steps: [{ id: 'lookup', name: 'CVE lookup', status: 'success' }],
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

  it('keeps partial content during provider retry and replaces on resume', () => {
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
      content: 'partial',
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

  it('clears liveSearch when tools are turned off', () => {
    const withLive = chatReducer(
      { ...initialChatState, liveSearch: true, enableTools: true },
      { type: 'enable-tools', value: false },
    )
    expect(withLive.enableTools).toBe(false)
    expect(withLive.liveSearch).toBe(false)
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

  it('session-switch clears requesting and messages for history load', () => {
    const started = chatReducer(initialChatState, {
      type: 'start',
      user: { id: 'u1', role: 'user', content: 'hi', final: true },
      assistant: { id: 'a1', role: 'assistant', content: '', final: false, status: 'streaming' },
      modelId: 'm1',
    })
    expect(started.requesting).toBe(true)
    expect(started.messages).toHaveLength(2)
    const switched = chatReducer(started, { type: 'session-switch' })
    expect(switched.requesting).toBe(false)
    expect(switched.messages).toEqual([])
    expect(switched.error).toBeNull()
    // history can apply after switch
    const withHistory = chatReducer(switched, {
      type: 'history',
      messages: [{ id: 'h1', role: 'user', content: 'prior', final: true }],
    })
    expect(withHistory.messages).toHaveLength(1)
  })

  it('attach-live marks requesting and a streaming assistant bubble', () => {
    const base = chatReducer(initialChatState, {
      type: 'history',
      messages: [
        { id: 'u1', role: 'user', content: 'hi', final: true },
        { id: 'run-1', role: 'assistant', content: '', final: true, status: 'completed' },
      ],
    })
    const attached = chatReducer(base, {
      type: 'attach-live',
      messages: [{ id: 'u1', role: 'user', content: 'hi', final: true }],
      assistantId: 'run-live',
    })
    expect(attached.requesting).toBe(true)
    expect(attached.messages).toHaveLength(2)
    expect(attached.messages[1]).toMatchObject({
      id: 'run-live',
      role: 'assistant',
      status: 'streaming',
      final: false,
    })
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
        skillNames: ['cve-intel-skill', 'hitl-containment-skill'],
        enableTools: true,
      },
    })
    expect(next.messages[0]).toMatchObject({
      run_id: 'run-skills',
      leanMode: false,
      skillNames: ['cve-intel-skill', 'hitl-containment-skill'],
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
        attachments: [{ name: 'evidence.pdf', mime: 'application/pdf', kind: 'document' }],
        sources: [{ title: 'Incident report', url: 'https://example.test/report', snippet: 'summary' }],
        tools: [{ id: 'lookup', name: 'CVE lookup', status: 'completed' }],
        thought_chain: [{ id: 'plan', title: 'Plan', status: 'completed' }],
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
    expect(messages[0]).toMatchObject({
      leanMode: true,
      enableTools: true,
      searchKnowledge: false,
      skillNames: [],
      attachments: [{ name: 'evidence.pdf', mime: 'application/pdf', kind: 'document' }],
      sources: [{ title: 'Incident report', url: 'https://example.test/report', snippet: 'summary' }],
      tool_steps: [{ id: 'lookup', name: 'CVE lookup', status: 'success' }],
      thought_chain: [{ id: 'plan', title: 'Plan', status: 'success' }],
    })
    expect(messages[1]).toMatchObject({ leanMode: false, enableTools: true, searchKnowledge: true, skillNames: ['cve-intel-skill'] })
    expect(messages[2]).toMatchObject({ leanMode: false, enableTools: true, searchKnowledge: true, skillNames: null })
    expect(messages[3]).toMatchObject({ leanMode: false, enableTools: false, searchKnowledge: false, skillNames: [] })
  })

})

describe('formatSkillLabel', () => {
  it('strips -skill and title-cases segments', () => {
    expect(formatSkillLabels(['cve-intel-skill', 'hitl-containment-skill', 'intranet-ip-skill'])).toBe(
      'CVE Intel, HITL Containment, Intranet IP',
    )
  })
})

describe('formatToolLabel', () => {
  it('maps builtin MCP tools via i18n', () => {
    expect(formatToolLabel('hitl_simulate_containment', translateToolLabel)).toBe('模拟隔离资产')
    expect(formatToolLabel('basic_send_feishu_notify', translateToolLabel)).toBe('发送飞书通知')
    expect(formatToolLabel('get_skill_instructions', translateToolLabel)).toBe('读取 Skill 说明')
  })

  it('humanizes unknown tool ids', () => {
    expect(formatToolLabel('external_lookup_asset')).toBe('External Lookup Asset')
    expect(formatToolLabel('hitl_custom_action')).toBe('Custom Action')
  })
})

describe('toggle helpers', () => {
  it('activates knowledge/live search from explicit preferences when tools are on', () => {
    expect(isKnowledgeToggleActive(true, true)).toBe(true)
    expect(isKnowledgeToggleActive(true, false)).toBe(false)
    expect(isLiveSearchToggleActive(true, true, true)).toBe(true)
    expect(isLiveSearchToggleActive(true, true, false)).toBe(false)
    expect(isLiveSearchToggleActive(true, false, true)).toBe(false)
  })
})

describe('formatRetryDetail', () => {
  it('includes delay when provided', () => {
    expect(
      formatRetryDetail({ attempt: 1, maxAttempts: 4, delaySeconds: 2.4, message: '503' }, translateRetryDetail),
    ).toBe('retry 1/4 in 2s (503)')
  })

  it('omits delay when missing', () => {
    expect(formatRetryDetail({ attempt: 2, maxAttempts: 4 }, translateRetryDetail)).toBe('retry 2/4')
  })
})

  it('clears retry metadata when cancelled during backoff', () => {
    const assistant: Message = { id: 'a', role: 'assistant', content: '', final: false, status: 'streaming' }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    const retrying = chatReducer(started, {
      type: 'event',
      id: 'a',
      event: { type: 'run.retrying', attempt: 1, maxAttempts: 4, delaySeconds: 2, message: '503' },
    })
    const cancelled = chatReducer(retrying, {
      type: 'event',
      id: 'a',
      event: { type: 'run.cancelled', runId: 'run-1', reason: 'stopped' },
    })
    expect(cancelled.messages[0]).toMatchObject({ status: 'cancelled', retry: null })
    expect(cancelled.requesting).toBe(false)
  })

  it('network-error clears retry metadata', () => {
    const assistant: Message = { id: 'a', role: 'assistant', content: '', final: false, status: 'streaming' }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    const retrying = chatReducer(started, {
      type: 'event',
      id: 'a',
      event: { type: 'run.retrying', attempt: 1, maxAttempts: 4, delaySeconds: 1 },
    })
    const failed = chatReducer(retrying, { type: 'network-error', id: 'a', message: 'offline' })
    expect(failed.messages[0]).toMatchObject({ status: 'failed', retry: null })
    expect(failed.requesting).toBe(false)
  })

  it('paused clears retry metadata', () => {
    const assistant: Message = { id: 'a', role: 'assistant', content: '', final: false, status: 'streaming' }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    const retrying = chatReducer(started, {
      type: 'event',
      id: 'a',
      event: { type: 'run.retrying', attempt: 1, maxAttempts: 3, delaySeconds: 1 },
    })
    const paused = chatReducer(retrying, {
      type: 'event',
      id: 'a',
      event: {
        type: 'run.paused',
        runId: 'run-1',
        sessionId: 'sess-1',
        approvalId: 'appr-1',
      },
    })
    expect(paused.messages[0]).toMatchObject({
      status: 'paused',
      retry: null,
      approval_id: 'appr-1',
      session_id: 'sess-1',
    })
    expect(paused.requesting).toBe(false)
  })

  it('clears retry when tool updates resume after provider retry', () => {
    const assistant: Message = { id: 'a', role: 'assistant', content: '', final: false, status: 'streaming' }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    const retrying = chatReducer(started, {
      type: 'event',
      id: 'a',
      event: { type: 'run.retrying', attempt: 1, maxAttempts: 3, delaySeconds: 1 },
    })
    const withTool = chatReducer(retrying, {
      type: 'event',
      id: 'a',
      event: {
        type: 'tool.update',
        tool: { id: 't1', name: 'lookup', status: 'loading' },
      },
    })
    expect(withTool.messages[0]).toMatchObject({ status: 'streaming', retry: null })
    expect(withTool.messages[0]?.tool_steps?.[0]?.id).toBe('t1')
  })

  it('ignores late content after cancel', () => {
    const assistant: Message = { id: 'a', role: 'assistant', content: 'partial', final: false, status: 'streaming' }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    const cancelled = chatReducer(started, {
      type: 'event',
      id: 'a',
      event: { type: 'run.cancelled', runId: 'run-1', reason: 'stopped' },
    })
    const late = chatReducer(cancelled, {
      type: 'event',
      id: 'a',
      event: { type: 'content.delta', delta: ' should not append' },
    })
    expect(late.messages[0]).toMatchObject({ status: 'cancelled', content: 'partial' })
  })


  it('replaces thought chain when thought.update resumes after provider retry', () => {
    const assistant: Message = {
      id: 'a',
      role: 'assistant',
      content: 'partial',
      final: false,
      status: 'streaming',
      thought_chain: [{ id: 'old', title: 'old', status: 'success' }],
    }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    const retrying = chatReducer(started, {
      type: 'event',
      id: 'a',
      event: { type: 'run.retrying', attempt: 1, maxAttempts: 3, delaySeconds: 1 },
    })
    const withThought = chatReducer(retrying, {
      type: 'event',
      id: 'a',
      event: {
        type: 'thought.update',
        thought: { id: 'new', title: 'new', status: 'loading' },
      },
    })
    expect(withThought.messages[0]).toMatchObject({
      status: 'streaming',
      retry: null,
      content: '',
    })
    expect(withThought.messages[0]?.thought_chain?.map((t) => t.id)).toEqual(['new'])
  })

  it('clears approval_id when a paused run continues', () => {
    const assistant: Message = {
      id: 'a',
      role: 'assistant',
      content: 'waiting',
      final: true,
      status: 'paused',
      approval_id: 'appr-1',
      run_id: 'run-1',
    }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    // force paused message into state via history so we start from pause
    const paused = { ...started, messages: [assistant], requesting: false }
    const continued = chatReducer(paused, {
      type: 'event',
      id: 'a',
      event: { type: 'run.continued', runId: 'run-1', sessionId: 'sess-1' },
    })
    expect(continued.messages[0]).toMatchObject({
      status: 'streaming',
      final: false,
      approval_id: null,
      run_id: 'run-1',
    })
    const completed = chatReducer(continued, {
      type: 'event',
      id: 'a',
      event: { type: 'run.completed', runId: 'run-1', sessionId: 'sess-1' },
    })
    expect(completed.messages[0]).toMatchObject({ status: 'completed', approval_id: null })
  })

  it('replaces sources when sources event resumes after provider retry', () => {
    const assistant: Message = {
      id: 'a',
      role: 'assistant',
      content: 'partial',
      final: false,
      status: 'streaming',
      sources: [{ id: 's0', title: 'old' }],
    }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    const retrying = chatReducer(started, {
      type: 'event',
      id: 'a',
      event: { type: 'run.retrying', attempt: 1, maxAttempts: 3, delaySeconds: 1 },
    })
    const withSources = chatReducer(retrying, {
      type: 'event',
      id: 'a',
      event: {
        type: 'sources',
        items: [{ id: 's1', title: 'fresh' }],
      },
    })
    expect(withSources.messages[0]).toMatchObject({
      status: 'streaming',
      retry: null,
      content: '',
    })
    expect(withSources.messages[0]?.sources).toEqual([{ id: 's1', title: 'fresh' }])
  })

  it('finalizes loading thoughts and tools on run.completed', () => {
    const assistant: Message = {
      id: 'a',
      role: 'assistant',
      content: 'hello',
      final: false,
      status: 'streaming',
      thought_chain: [
        { id: 'member:deep-research', title: '成员 · 深度研究', status: 'loading', summary: 'draft' },
        { id: 'reasoning', title: '模型推理', status: 'success', summary: 'ok' },
      ],
      tool_steps: [
        { id: 't1', name: 'calc', status: 'loading' },
        { id: 't2', name: 'done', status: 'success' },
      ],
    }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    const completed = chatReducer(started, {
      type: 'event',
      id: 'a',
      event: { type: 'run.completed', runId: 'run-1', content: 'hello world' },
    })
    const msg = completed.messages[0]
    expect(msg?.status).toBe('completed')
    expect(msg?.content).toBe('hello world')
    expect(msg?.thought_chain?.find((t) => t.id === 'member:deep-research')?.status).toBe('success')
    expect(msg?.tool_steps?.find((t) => t.id === 't1')?.status).toBe('success')
    expect(msg?.tool_steps?.find((t) => t.id === 't2')?.status).toBe('success')
  })

  it('merges cumulative content.delta snapshots without duplicating', () => {
    const assistant: Message = { id: 'a', role: 'assistant', content: '', final: false, status: 'streaming' }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    const first = chatReducer(started, {
      type: 'event',
      id: 'a',
      event: { type: 'content.delta', delta: 'Hello' },
    })
    const second = chatReducer(first, {
      type: 'event',
      id: 'a',
      event: { type: 'content.delta', delta: 'Hello world' },
    })
    expect(second.messages[0]?.content).toBe('Hello world')
  })

  it('merges sources from multiple team members', () => {
    const assistant: Message = { id: 'a', role: 'assistant', content: '', final: false, status: 'streaming' }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    const first = chatReducer(started, {
      type: 'event',
      id: 'a',
      event: { type: 'sources', items: [{ id: '1', title: '[深度研究] A', url: 'https://a.example' }] },
    })
    const second = chatReducer(first, {
      type: 'event',
      id: 'a',
      event: { type: 'sources', items: [{ id: '2', title: '[数据分析] B', url: 'https://b.example' }] },
    })
    expect(second.messages[0]?.sources).toEqual([
      { id: '1', title: '[深度研究] A', url: 'https://a.example' },
      { id: '2', title: '[数据分析] B', url: 'https://b.example' },
    ])
  })

describe('Team task snapshots', () => {
  const taskState = {
    tasks: [
      { id: 'research', title: 'Collect evidence', status: 'in_progress' as const, assignee: 'Deep Research' },
      { id: 'analysis', title: 'Analyze evidence', status: 'pending' as const, dependencies: ['research'] },
    ],
    taskSummary: 'Split the investigation',
  }

  const startedWithTasks = () => {
    const assistant: Message = { id: 'a', role: 'assistant', content: '', final: false, status: 'streaming' }
    const started = chatReducer(initialChatState, { type: 'start', assistant, modelId: 'model' })
    return chatReducer(started, {
      type: 'event',
      id: 'a',
      event: { type: 'team.tasks', state: taskState },
    })
  }

  it('uses the latest Team task snapshot rather than merging stale tasks', () => {
    const first = startedWithTasks()
    const next = chatReducer(first, {
      type: 'event',
      id: 'a',
      event: {
        type: 'team.tasks',
        state: {
          tasks: [{ id: 'synthesis', title: 'Synthesize answer', status: 'completed' }],
          goalComplete: true,
        },
      },
    })

    expect(next.messages[0]?.team_tasks).toEqual({
      tasks: [{ id: 'synthesis', title: 'Synthesize answer', status: 'completed' }],
      goalComplete: true,
    })
  })

  it('clears the prior Team task panel when a retry starts streaming again', () => {
    const retrying = chatReducer(startedWithTasks(), {
      type: 'event',
      id: 'a',
      event: { type: 'run.retrying', attempt: 1, maxAttempts: 3 },
    })
    const resumed = chatReducer(retrying, {
      type: 'event',
      id: 'a',
      event: { type: 'content.delta', delta: 'A fresh answer' },
    })

    expect(resumed.messages[0]).toMatchObject({ status: 'streaming', team_tasks: null })
  })

  it('settles unfinished Team tasks when the run is cancelled or fails', () => {
    const cancelled = chatReducer(startedWithTasks(), {
      type: 'event',
      id: 'a',
      event: { type: 'run.cancelled', reason: 'Stopped' },
    })
    const failed = chatReducer(startedWithTasks(), {
      type: 'event',
      id: 'a',
      event: { type: 'run.failed', message: 'Provider failed' },
    })

    expect(cancelled.messages[0]?.team_tasks?.tasks.map((task) => task.status)).toEqual(['cancelled', 'cancelled'])
    expect(failed.messages[0]?.team_tasks?.tasks.map((task) => task.status)).toEqual(['failed', 'failed'])
  })

  it('settles unfinished Team tasks on a transport failure', () => {
    const failed = chatReducer(startedWithTasks(), {
      type: 'network-error',
      id: 'a',
      message: 'offline',
    })

    expect(failed.messages[0]?.team_tasks?.tasks.map((task) => task.status)).toEqual(['failed', 'failed'])
  })
})
