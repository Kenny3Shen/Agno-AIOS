import type { ChatAction, ChatState, Message, ParsedMessage } from './types'

export const initialChatState: ChatState = { messages: [], input: '', requesting: false, error: null, selectedModelId: localStorage.getItem('agno-aios-chat-model-id') }

export const chatReducer = (state: ChatState, action: ChatAction): ChatState => {
  switch (action.type) {
    case 'history': return state.requesting ? state : { ...state, messages: action.messages }
    case 'input': return { ...state, input: action.value }
    case 'model': return { ...state, selectedModelId: action.value }
    case 'start': return { ...state, input: '', requesting: true, error: null, selectedModelId: action.modelId, messages: [...state.messages, ...(action.user ? [action.user] : []), action.assistant] }
    case 'chunk': return { ...state, messages: state.messages.map((message) => message.id === action.id ? { ...message, content: message.content + action.chunk } : message) }
    case 'finish': return { ...state, requesting: false, messages: state.messages.map((message) => message.id === action.id ? { ...message, final: true } : message) }
    case 'error': return { ...state, requesting: false, error: action.message, messages: action.id ? state.messages.map((message) => message.id === action.id ? { ...message, final: true } : message) : state.messages }
    case 'reset': return { ...state, messages: [], input: '', requesting: false, error: null }
  }
}

export const parseMessage = (content: string): ParsedMessage => {
  let thinking = ''
  const sources: string[] = []
  const tools: string[] = []
  let body = content.replace(/<think>([\s\S]*?)(?:<\/think>|$)/gi, (_match, value: string) => { thinking = value.trim(); return '' })
  body = body.split('\n').filter((raw) => {
    const line = raw.trim()
    if (/^(来源|Source|Sources|References|引用)\s*[:：]/i.test(line)) { sources.push(line.replace(/^.*?[:：]\s*/, '')); return false }
    if (/^(tool|工具调用|MCP|function call)\b/i.test(line)) { tools.push(line); return false }
    return true
  }).join('\n').trim()
  return { body, thinking, sources, tools: tools.slice(0, 8) }
}

export const normalizeMessages = (value: unknown): Message[] => Array.isArray(value) ? value.map((item, index) => {
  const source = item && typeof item === 'object' ? item as Record<string, unknown> : {}
  return {
    ...source,
    id: String(source.run_id ?? `${source.role ?? 'message'}-${index}`),
    role: source.role === 'user' || source.role === 'system' ? source.role : 'assistant',
    content: typeof source.content === 'string' ? source.content : JSON.stringify(source.content ?? ''),
    final: true,
  } as Message
}) : []

export interface SseEvent { event: string; data: string }
export const consumeSse = async (stream: ReadableStream<Uint8Array>, onEvent: (event: SseEvent) => void) => {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  const flush = (block: string) => {
    const lines = block.replace(/\r/g, '').split('\n')
    const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim() ?? 'message'
    const data = lines.filter((line) => line.startsWith('data:')).map((line) => line.slice(5).replace(/^ /, '')).join('\n')
    if (data) onEvent({ event, data })
  }
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const blocks = buffer.split(/\n\n|\r\n\r\n/)
    buffer = blocks.pop() ?? ''
    blocks.forEach(flush)
    if (done) break
  }
  if (buffer.trim()) flush(buffer)
}

export const previousPrompt = (messages: Message[], assistantId: string) => {
  const index = messages.findIndex((message) => message.id === assistantId)
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) if (messages[cursor]?.role === 'user') return messages[cursor]?.content ?? ''
  return ''
}
