const fallbackModelId = () => `model-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`

export const createModelId = (randomUUID: (() => string) | null = globalThis.crypto?.randomUUID?.bind(globalThis.crypto) ?? null) => {
  try {
    return randomUUID?.() ?? fallbackModelId()
  } catch {
    return fallbackModelId()
  }
}
