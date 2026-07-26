/**
 * Create a UUID-shaped identifier in browsers that do not implement
 * `crypto.randomUUID()` (for example, older browsers or non-secure origins).
 * These IDs are used for client-side correlation/UI state, not credentials.
 */
type RandomUuid = () => string

let fallbackCounter = 0

const browserCrypto = (): Crypto | undefined => {
  try {
    return globalThis.crypto
  } catch {
    return undefined
  }
}

const fallbackUuid = (): string => {
  const bytes = new Uint8Array(16)
  const crypto = browserCrypto()
  try {
    if (typeof crypto?.getRandomValues === 'function') {
      crypto.getRandomValues(bytes)
    } else {
      for (let index = 0; index < bytes.length; index += 1) {
        bytes[index] = Math.floor(Math.random() * 256)
      }
    }
  } catch {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256)
    }
  }

  // RFC 4122 version 4 and variant bits.
  bytes[6] = (bytes[6]! & 0x0f) | 0x40
  bytes[8] = (bytes[8]! & 0x3f) | 0x80
  fallbackCounter = (fallbackCounter + 1) >>> 0
  bytes[12] = bytes[12]! ^ (fallbackCounter >>> 24)
  bytes[13] = bytes[13]! ^ (fallbackCounter >>> 16)
  bytes[14] = bytes[14]! ^ (fallbackCounter >>> 8)
  bytes[15] = bytes[15]! ^ fallbackCounter

  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

const nativeRandomUuid = (): RandomUuid | null => {
  const crypto = browserCrypto()
  return typeof crypto?.randomUUID === 'function' ? crypto.randomUUID.bind(crypto) : null
}

export const createClientId = (randomUuid: RandomUuid | null = nativeRandomUuid()): string => {
  try {
    const value = randomUuid?.()
    if (typeof value === 'string' && value) return value
  } catch {
    // Some browsers expose the property but reject it outside a secure context.
  }
  return fallbackUuid()
}
